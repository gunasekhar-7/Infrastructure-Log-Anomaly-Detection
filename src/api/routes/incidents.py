"""Incident Management and Correlation API Endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import IncidentActionRequest, IncidentResponse, PaginatedIncidentsResponse
from src.database.connection import get_db_session
from src.database.repository import DatabaseRepository

router = APIRouter(prefix="/incidents", tags=["Incidents"])


def _to_incident_response(inc) -> IncidentResponse:
    alert_ids = inc.alert_ids_json or []
    return IncidentResponse(
        incident_id=inc.incident_id,
        title=inc.title,
        severity=inc.severity,
        status=inc.status,
        primary_service=inc.primary_service,
        affected_hosts=inc.affected_hosts_json or [],
        related_templates=inc.related_templates_json or [],
        started_at=inc.started_at,
        last_seen_at=inc.last_seen_at,
        alert_count=len(alert_ids),
        summary=inc.summary or "",
    )


@router.get("", response_model=PaginatedIncidentsResponse)
async def query_incidents(
    status_filter: str | None = Query(None, alias="status", description="Filter by status (OPEN, INVESTIGATING, RESOLVED, etc.)"),
    limit: int = Query(50, ge=1, le=1000, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedIncidentsResponse:
    """Retrieve correlated multi-alert operational incidents."""
    repo = DatabaseRepository(session)
    incidents, total = await repo.get_incidents(
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    items = [_to_incident_response(inc) for inc in incidents]
    return PaginatedIncidentsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> IncidentResponse:
    """Retrieve incident details by incident ID."""
    repo = DatabaseRepository(session)
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )
    return _to_incident_response(inc)


@router.post("/{incident_id}/action", response_model=IncidentResponse)
async def handle_incident_action(
    incident_id: str,
    payload: IncidentActionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> IncidentResponse:
    """Perform operational actions on an incident (Investigate, Mitigate, Resolve)."""
    repo = DatabaseRepository(session)
    inc = await repo.get_incident(incident_id)
    if not inc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with ID '{incident_id}' not found.",
        )

    action_norm = payload.action.upper()
    if action_norm in ("INVESTIGATE", "INVESTIGATING"):
        inc.status = "INVESTIGATING"
    elif action_norm in ("MITIGATE", "MITIGATED"):
        inc.status = "MITIGATED"
    elif action_norm in ("RESOLVE", "RESOLVED"):
        inc.status = "RESOLVED"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action '{payload.action}'. Supported: INVESTIGATE, MITIGATE, RESOLVE.",
        )

    if payload.summary_findings:
        inc.summary = f"{inc.summary} | [{action_norm} by {payload.actor}]: {payload.summary_findings}".strip(" |")

    updated_inc = await repo.save_incident(inc)

    # Record audit log
    await repo.create_audit_entry(
        entity_type="INCIDENT",
        entity_id=incident_id,
        action=action_norm,
        actor=payload.actor,
        details={"summary_findings": payload.summary_findings, "new_status": updated_inc.status},
    )

    return _to_incident_response(updated_inc)

