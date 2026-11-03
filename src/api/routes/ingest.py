"""Log Ingestion API Endpoints."""

import shutil
from tempfile import NamedTemporaryFile
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import IngestJobResponse, IngestStreamRequest
from src.database.connection import get_db_session
from src.database.models import (
    AlertORM,
    AnomalyEvidenceORM,
    AnomalyORM,
    IncidentORM,
    IngestionJobORM,
    LogEventORM,
)
from src.database.repository import DatabaseRepository
from src.ingestion.engine import LogIngestionEngine
from src.intelligence import AlertManager, AnomalyAssessor, IncidentCorrelator
from src.models import IsolationForestDetector
from src.parsing.drain_engine import DrainParser

router = APIRouter(prefix="/ingest", tags=["Ingestion"])

# Global shared processing singletons
_ingestion_engine = LogIngestionEngine()
_drain_parser = DrainParser()
_assessor = AnomalyAssessor()
_alert_manager = AlertManager()
_correlator = IncidentCorrelator()


async def process_log_events_pipeline(events, repo: DatabaseRepository, job_id: str):
    """Core asynchronous pipeline: Parse -> Store -> Detect Anomalies -> Alert -> Correlate."""
    parsed_events = _drain_parser.parse_batch(events)

    # 1. Store templates and events
    orm_events = []
    for pe in parsed_events:
        await repo.upsert_template(pe.template_id, pe.template_text, pe.parameters)
        orm_events.append(
            LogEventORM(
                job_id=job_id,
                timestamp=pe.timestamp,
                host=pe.host,
                service=pe.service,
                component=pe.component,
                severity=pe.severity.value,
                template_id=pe.template_id,
                message=pe.message,
                raw_log=pe.raw_log,
                parameters_json=pe.parameters,
                attributes_json=pe.attributes,
            )
        )
    await repo.create_log_events(orm_events)

    # 2. Check for unseen templates or error spikes to trigger anomalies
    for pe in parsed_events:
        if pe.is_unseen_template or pe.severity.value in ("ERROR", "FATAL"):
            score = 0.85 if pe.severity.value in ("ERROR", "FATAL") else 0.65
            anomaly = _assessor.assess_unseen_template(pe, anomaly_score=score)

            # Persist anomaly
            anom_orm = AnomalyORM(
                id=anomaly.anomaly_id,
                timestamp=anomaly.timestamp,
                host=anomaly.host,
                service=anomaly.service,
                anomaly_score=anomaly.anomaly_score,
                severity=anomaly.severity.value,
                category=anomaly.anomaly_category.value,
                algorithm=anomaly.algorithm,
                explanation=anomaly.explanation,
                related_templates_json=anomaly.related_templates,
                investigation_status=anomaly.investigation_status.value,
                context_metadata_json=anomaly.context_metadata,
            )
            evidence_orm = [
                AnomalyEvidenceORM(
                    anomaly_id=anomaly.anomaly_id,
                    event_id=ev.event_id,
                    timestamp=ev.timestamp,
                    template_id=ev.template_id,
                    raw_message=ev.raw_message,
                    severity=ev.severity,
                    is_trigger=ev.is_trigger,
                    reason=ev.reason,
                )
                for ev in anomaly.supporting_evidence
            ]
            await repo.save_anomaly(anom_orm, evidence_orm)

            # Route to alert manager and incident correlator
            alert = _alert_manager.process_anomaly(anomaly)
            if alert:
                alert_orm = AlertORM(
                    alert_id=alert.alert_id,
                    anomaly_id=alert.anomaly_id,
                    title=alert.title,
                    severity=alert.severity.value,
                    status=alert.status.value,
                    host=alert.host,
                    service=alert.service,
                    triggered_at=alert.triggered_at,
                    deduplication_key=alert.deduplication_key,
                    repeat_count=alert.repeat_count,
                )
                await repo.save_alert(alert_orm)

                # Correlate into incident
                inc = _correlator.correlate_alert(alert, anomaly)
                if inc:
                    inc_orm = IncidentORM(
                        incident_id=inc.incident_id,
                        title=inc.title,
                        severity=inc.severity.value,
                        status=inc.status.value,
                        primary_service=inc.primary_service,
                        affected_hosts_json=list(inc.affected_hosts),
                        related_templates_json=list(inc.related_templates),
                        started_at=inc.started_at,
                        last_seen_at=inc.last_seen_at,
                        alert_ids_json=list(inc.alert_ids),
                        anomaly_ids_json=list(inc.anomaly_ids),
                        summary=inc.summary,
                    )
                    await repo.save_incident(inc_orm)
                    alert_orm.incident_id = inc.incident_id
                    await repo.save_alert(alert_orm)


@router.post("/stream", response_model=IngestJobResponse, status_code=status.HTTP_200_OK)
async def ingest_stream(
    payload: IngestStreamRequest,
    session: AsyncSession = Depends(get_db_session),
) -> IngestJobResponse:
    """Ingest a batch of raw log lines directly via HTTP request."""
    repo = DatabaseRepository(session)
    job = await repo.create_job(source_name=payload.source_id, total_records=len(payload.lines))

    events, stats = _ingestion_engine.ingest_stream(payload.lines, source_id=payload.source_id)

    # Process pipeline
    await process_log_events_pipeline(events, repo, job.id)

    # Update job
    updated_job = await repo.update_job(
        job_id=job.id,
        status="COMPLETED",
        valid_records=stats.valid_records,
        failed_records=stats.invalid_records,
        duration_ms=stats.duration_ms,
        throughput_eps=stats.throughput_eps,
    )

    return IngestJobResponse(
        job_id=updated_job.id,
        source_name=updated_job.source_name,
        status=updated_job.status,
        total_records=updated_job.total_records,
        valid_records=updated_job.valid_records,
        failed_records=updated_job.failed_records,
        duration_ms=updated_job.duration_ms,
        throughput_eps=updated_job.throughput_eps,
        started_at=updated_job.started_at,
        completed_at=updated_job.completed_at,
    )


@router.post("/upload", response_model=IngestJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_log_file(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> IngestJobResponse:
    """Upload a raw log file (.log, .txt, .json) for ingestion."""
    repo = DatabaseRepository(session)
    job = await repo.create_job(source_name=file.filename or "upload")

    with NamedTemporaryFile(delete=False, suffix=".log") as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    events, stats = _ingestion_engine.ingest_file(tmp_path, source_id=file.filename or "upload")
    await process_log_events_pipeline(events, repo, job.id)

    updated_job = await repo.update_job(
        job_id=job.id,
        status="COMPLETED",
        valid_records=stats.valid_records,
        failed_records=stats.invalid_records,
        duration_ms=stats.duration_ms,
        throughput_eps=stats.throughput_eps,
    )

    return IngestJobResponse(
        job_id=updated_job.id,
        source_name=updated_job.source_name,
        status=updated_job.status,
        total_records=updated_job.total_records,
        valid_records=updated_job.valid_records,
        failed_records=updated_job.failed_records,
        duration_ms=updated_job.duration_ms,
        throughput_eps=updated_job.throughput_eps,
        started_at=updated_job.started_at,
        completed_at=updated_job.completed_at,
    )


@router.get("/jobs/{job_id}", response_model=IngestJobResponse)
async def get_job_status(
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> IngestJobResponse:
    """Retrieve progress and completion telemetry for an ingestion job."""
    repo = DatabaseRepository(session)
    job = await repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Ingestion job '{job_id}' not found.")

    return IngestJobResponse(
        job_id=job.id,
        source_name=job.source_name,
        status=job.status,
        total_records=job.total_records,
        valid_records=job.valid_records,
        failed_records=job.failed_records,
        duration_ms=job.duration_ms,
        throughput_eps=job.throughput_eps,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )
