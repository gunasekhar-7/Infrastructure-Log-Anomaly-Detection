"""Asynchronous Database Repository Abstractions."""

import asyncio
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    AlertORM,
    AnomalyEvidenceORM,
    AnomalyORM,
    AuditLogORM,
    IncidentORM,
    IngestionJobORM,
    LogEventORM,
    LogTemplateORM,
)


class DatabaseRepository:
    """Unified repository coordinating async persistence and querying."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # =========================================================================
    # INGESTION JOBS
    # =========================================================================
    async def create_job(self, source_name: str, total_records: int = 0) -> IngestionJobORM:
        """Create new ingestion job."""
        job = IngestionJobORM(
            source_name=source_name,
            status="RUNNING",
            total_records=total_records,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def update_job(
        self,
        job_id: str,
        status: str,
        valid_records: int,
        failed_records: int,
        duration_ms: float,
        throughput_eps: float,
        error_message: str | None = None,
    ) -> IngestionJobORM | None:
        """Update job statistics upon completion."""
        job = await self.session.get(IngestionJobORM, job_id)
        if job:
            job.status = status
            job.valid_records = valid_records
            job.failed_records = failed_records
            job.duration_ms = duration_ms
            job.throughput_eps = throughput_eps
            job.error_message = error_message
            job.completed_at = datetime.now()
            await self.session.commit()
            await self.session.refresh(job)
        return job

    async def get_job(self, job_id: str) -> IngestionJobORM | None:
        """Retrieve ingestion job by ID."""
        return await self.session.get(IngestionJobORM, job_id)

    # =========================================================================
    # LOG TEMPLATES
    # =========================================================================
    async def upsert_template(
        self,
        template_id: str,
        template_pattern: str,
        sample_params: list | None = None,
        count: int = 1,
    ) -> LogTemplateORM:
        """Insert or increment template occurrence count safely under concurrency."""
        for attempt in range(5):
            try:
                tmpl = await self.session.get(LogTemplateORM, template_id)
                if tmpl:
                    tmpl.occurrence_count += count
                    tmpl.template_pattern = template_pattern
                    tmpl.last_seen = datetime.now()
                    if sample_params:
                        tmpl.sample_parameters_json = sample_params[:5]
                else:
                    tmpl = LogTemplateORM(
                        template_id=template_id,
                        template_pattern=template_pattern,
                        occurrence_count=count,
                        sample_parameters_json=sample_params[:5] if sample_params else [],
                    )
                    self.session.add(tmpl)
                await self.session.commit()
                return tmpl
            except IntegrityError:
                await self.session.rollback()
                if attempt == 4:
                    existing = await self.session.get(LogTemplateORM, template_id)
                    if existing:
                        return existing
                    raise
                await asyncio.sleep(0.02 * (attempt + 1))
            except OperationalError:
                await self.session.rollback()
                if attempt == 4:
                    raise
                await asyncio.sleep(0.05 * (attempt + 1))

        existing = await self.session.get(LogTemplateORM, template_id)
        if existing:
            return existing
        raise RuntimeError(f"Failed to upsert template {template_id} after retries")

    async def get_templates(self, limit: int = 100, offset: int = 0) -> tuple[list[LogTemplateORM], int]:
        """List templates ordered by occurrence frequency."""
        count_stmt = select(func.count(LogTemplateORM.template_id))
        total_res = await self.session.execute(count_stmt)
        total = int(total_res.scalar() or 0)

        stmt = select(LogTemplateORM).order_by(desc(LogTemplateORM.occurrence_count)).limit(limit).offset(offset)
        res = await self.session.execute(stmt)
        return list(res.scalars().all()), total

    # =========================================================================
    # LOG EVENTS
    # =========================================================================
    async def create_log_events(self, events: list[LogEventORM]) -> int:
        """Batch insert parsed log events."""
        if not events:
            return 0
        self.session.add_all(events)
        await self.session.commit()
        return len(events)

    async def query_logs(
        self,
        service: str | None = None,
        host: str | None = None,
        severity: str | None = None,
        template_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[LogEventORM], int]:
        """Paginated search across parsed log events with multi-criteria filtering."""
        stmt = select(LogEventORM)
        count_stmt = select(func.count(LogEventORM.id))

        if service:
            stmt = stmt.where(LogEventORM.service == service)
            count_stmt = count_stmt.where(LogEventORM.service == service)
        if host:
            stmt = stmt.where(LogEventORM.host == host)
            count_stmt = count_stmt.where(LogEventORM.host == host)
        if severity:
            stmt = stmt.where(LogEventORM.severity == severity.upper())
            count_stmt = count_stmt.where(LogEventORM.severity == severity.upper())
        if template_id:
            stmt = stmt.where(LogEventORM.template_id == template_id)
            count_stmt = count_stmt.where(LogEventORM.template_id == template_id)

        stmt = stmt.order_by(desc(LogEventORM.timestamp)).limit(limit).offset(offset)

        total_res = await self.session.execute(count_stmt)
        total = int(total_res.scalar() or 0)

        logs_res = await self.session.execute(stmt)
        logs = list(logs_res.scalars().all())

        return logs, total

    # =========================================================================
    # ANOMALIES & EVIDENCE
    # =========================================================================
    async def save_anomaly(self, anomaly: AnomalyORM, evidence: list[AnomalyEvidenceORM] | None = None) -> AnomalyORM:
        """Persist detected anomaly and related evidence records."""
        self.session.add(anomaly)
        if evidence:
            self.session.add_all(evidence)
        await self.session.commit()
        await self.session.refresh(anomaly)
        return anomaly

    async def get_anomalies(
        self,
        severity: str | None = None,
        service: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AnomalyORM], int]:
        """Query anomalies with pagination and filtering."""
        stmt = select(AnomalyORM)
        count_stmt = select(func.count(AnomalyORM.id))

        if severity:
            stmt = stmt.where(AnomalyORM.severity == severity.upper())
            count_stmt = count_stmt.where(AnomalyORM.severity == severity.upper())
        if service:
            stmt = stmt.where(AnomalyORM.service == service)
            count_stmt = count_stmt.where(AnomalyORM.service == service)

        stmt = stmt.order_by(desc(AnomalyORM.timestamp)).limit(limit).offset(offset)

        total_res = await self.session.execute(count_stmt)
        total = int(total_res.scalar() or 0)

        anom_res = await self.session.execute(stmt)
        anomalies = list(anom_res.scalars().all())

        return anomalies, total

    async def get_anomaly_detail(self, anomaly_id: str) -> tuple[AnomalyORM | None, list[AnomalyEvidenceORM]]:
        """Retrieve anomaly by ID with its supporting evidence items."""
        anom = await self.session.get(AnomalyORM, anomaly_id)
        if not anom:
            return None, []

        ev_stmt = select(AnomalyEvidenceORM).where(AnomalyEvidenceORM.anomaly_id == anomaly_id)
        ev_res = await self.session.execute(ev_stmt)
        evidence = list(ev_res.scalars().all())
        return anom, evidence

    # =========================================================================
    # ALERTS
    # =========================================================================
    async def save_alert(self, alert: AlertORM) -> AlertORM:
        """Create or update alert record."""
        merged = await self.session.merge(alert)
        await self.session.commit()
        return merged

    async def get_alerts(
        self,
        status: str | None = None,
        severity: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AlertORM], int]:
        """Query alerts with pagination and status/severity filters."""
        stmt = select(AlertORM)
        count_stmt = select(func.count(AlertORM.alert_id))

        if status:
            stmt = stmt.where(AlertORM.status == status.upper())
            count_stmt = count_stmt.where(AlertORM.status == status.upper())
        if severity:
            stmt = stmt.where(AlertORM.severity == severity.upper())
            count_stmt = count_stmt.where(AlertORM.severity == severity.upper())

        stmt = stmt.order_by(desc(AlertORM.triggered_at)).limit(limit).offset(offset)

        total_res = await self.session.execute(count_stmt)
        total = int(total_res.scalar() or 0)

        alert_res = await self.session.execute(stmt)
        alerts = list(alert_res.scalars().all())
        return alerts, total

    async def get_alert(self, alert_id: str) -> AlertORM | None:
        """Retrieve alert by ID."""
        return await self.session.get(AlertORM, alert_id)

    # =========================================================================
    # INCIDENTS
    # =========================================================================
    async def save_incident(self, incident: IncidentORM) -> IncidentORM:
        """Create or update incident record."""
        merged = await self.session.merge(incident)
        await self.session.commit()
        return merged

    async def get_incidents(
        self,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[IncidentORM], int]:
        """Query incidents with pagination."""
        stmt = select(IncidentORM)
        count_stmt = select(func.count(IncidentORM.incident_id))

        if status:
            stmt = stmt.where(IncidentORM.status == status.upper())
            count_stmt = count_stmt.where(IncidentORM.status == status.upper())

        stmt = stmt.order_by(desc(IncidentORM.started_at)).limit(limit).offset(offset)

        total_res = await self.session.execute(count_stmt)
        total = int(total_res.scalar() or 0)

        inc_res = await self.session.execute(stmt)
        incidents = list(inc_res.scalars().all())
        return incidents, total

    async def get_incident(self, incident_id: str) -> IncidentORM | None:
        """Retrieve incident by ID."""
        return await self.session.get(IncidentORM, incident_id)

    # =========================================================================
    # AUDIT LOGS
    # =========================================================================
    async def create_audit_entry(
        self,
        entity_type: str,
        entity_id: str,
        action: str,
        actor: str = "SYSTEM",
        details: dict | None = None,
    ) -> AuditLogORM:
        """Persist an immutable audit log entry."""
        entry = AuditLogORM(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor=actor,
            details_json=details or {},
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry
