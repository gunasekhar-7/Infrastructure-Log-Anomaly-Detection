"""Alert Management and Operations API Endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import AlertActionRequest, AlertResponse, PaginatedAlertsResponse
from src.database.connection import get_db_session
from src.database.repository import DatabaseRepository

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _to_alert_response(alert) -> AlertResponse:
    return AlertResponse(
        alert_id=alert.alert_id,
        anomaly_id=alert.anomaly_id,
        incident_id=alert.incident_id,
        title=alert.title,
        severity=alert.severity,
        status=alert.status,
        host=alert.host,
        service=alert.service,
        triggered_at=alert.triggered_at,
        repeat_count=alert.repeat_count,
        resolved_by=alert.resolved_by,
        resolution_note=alert.resolution_note,
    )


@router.get("", response_model=PaginatedAlertsResponse)
async def query_alerts(
    status_filter: str | None = Query(None, alias="status", description="Filter by status (NEW, ACKNOWLEDGED, RESOLVED, etc.)"),
    severity: str | None = Query(None, description="Filter by alert severity"),
    limit: int = Query(50, ge=1, le=1000, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedAlertsResponse:
    """Retrieve operational alerts with status and severity filters."""
    repo = DatabaseRepository(session)
    alerts, total = await repo.get_alerts(
        status=status_filter,
        severity=severity,
        limit=limit,
        offset=offset,
    )

    items = [_to_alert_response(a) for a in alerts]
    return PaginatedAlertsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{alert_id}", response_model=AlertResponse)
async def get_alert(
    alert_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> AlertResponse:
    """Retrieve alert details by alert ID."""
    repo = DatabaseRepository(session)
    alert = await repo.get_alert(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with ID '{alert_id}' not found.",
        )
    return _to_alert_response(alert)


@router.post("/{alert_id}/action", response_model=AlertResponse)
async def handle_alert_action(
    alert_id: str,
    payload: AlertActionRequest,
    session: AsyncSession = Depends(get_db_session),
) -> AlertResponse:
    """Perform operational triage actions on an alert (Acknowledge, Investigate, Resolve, False Positive)."""
    repo = DatabaseRepository(session)
    alert = await repo.get_alert(alert_id)
    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with ID '{alert_id}' not found.",
        )

    action_norm = payload.action.upper()
    now_utc = datetime.now(timezone.utc)

    if action_norm in ("ACKNOWLEDGE", "ACKNOWLEDGED"):
        alert.status = "ACKNOWLEDGED"
        alert.acknowledged_at = now_utc
    elif action_norm in ("INVESTIGATE", "INVESTIGATING"):
        alert.status = "INVESTIGATING"
    elif action_norm in ("RESOLVE", "RESOLVED"):
        alert.status = "RESOLVED"
        alert.resolved_at = now_utc
        alert.resolved_by = payload.actor
        alert.resolution_note = payload.note or "Resolved by operator"
    elif action_norm in ("FALSE_POSITIVE", "FP"):
        alert.status = "FALSE_POSITIVE"
        alert.resolved_at = now_utc
        alert.resolved_by = payload.actor
        alert.resolution_note = payload.note or "Classified as false positive"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action '{payload.action}'. Supported: ACKNOWLEDGE, INVESTIGATE, RESOLVE, FALSE_POSITIVE.",
        )

    updated_alert = await repo.save_alert(alert)

    # Record audit log entry
    await repo.create_audit_entry(
        entity_type="ALERT",
        entity_id=alert_id,
        action=action_norm,
        actor=payload.actor,
        details={"note": payload.note, "new_status": updated_alert.status},
    )

    return _to_alert_response(updated_alert)

