"""Anomaly Query and Detail API Endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import (
    AnomalyDetailResponse,
    AnomalyEvidenceResponse,
    AnomalyResponse,
    PaginatedAnomaliesResponse,
)
from src.database.connection import get_db_session
from src.database.repository import DatabaseRepository

router = APIRouter(prefix="/anomalies", tags=["Anomalies"])


@router.get("", response_model=PaginatedAnomaliesResponse)
async def query_anomalies(
    severity: str | None = Query(None, description="Filter by severity (INFO, LOW, MEDIUM, HIGH, CRITICAL)"),
    service: str | None = Query(None, description="Filter by service name"),
    limit: int = Query(50, ge=1, le=1000, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedAnomaliesResponse:
    """Retrieve paginated list of detected anomalies."""
    repo = DatabaseRepository(session)
    anomalies, total = await repo.get_anomalies(
        severity=severity,
        service=service,
        limit=limit,
        offset=offset,
    )

    items = [
        AnomalyResponse(
            id=a.id,
            timestamp=a.timestamp,
            host=a.host,
            service=a.service,
            anomaly_score=a.anomaly_score,
            severity=a.severity,
            category=a.category,
            algorithm=a.algorithm,
            explanation=a.explanation,
            related_templates=a.related_templates_json or [],
            investigation_status=a.investigation_status,
        )
        for a in anomalies
    ]

    return PaginatedAnomaliesResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{anomaly_id}", response_model=AnomalyDetailResponse)
async def get_anomaly_detail(
    anomaly_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AnomalyDetailResponse:
    """Retrieve full anomaly detail including supporting evidence logs."""
    repo = DatabaseRepository(session)
    anomaly, evidence = await repo.get_anomaly_detail(anomaly_id)
    if not anomaly:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anomaly with ID '{anomaly_id}' not found.",
        )

    evidence_items = [
        AnomalyEvidenceResponse(
            id=ev.id,
            event_id=ev.event_id,
            timestamp=ev.timestamp,
            template_id=ev.template_id,
            raw_message=ev.raw_message,
            severity=ev.severity,
            is_trigger=ev.is_trigger,
            reason=ev.reason,
        )
        for ev in evidence
    ]

    return AnomalyDetailResponse(
        id=anomaly.id,
        timestamp=anomaly.timestamp,
        host=anomaly.host,
        service=anomaly.service,
        anomaly_score=anomaly.anomaly_score,
        severity=anomaly.severity,
        category=anomaly.category,
        algorithm=anomaly.algorithm,
        explanation=anomaly.explanation,
        related_templates=anomaly.related_templates_json or [],
        investigation_status=anomaly.investigation_status,
        supporting_evidence=evidence_items,
        context_metadata=anomaly.context_metadata_json or {},
    )

