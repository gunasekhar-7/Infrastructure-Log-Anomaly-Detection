"""Log Query and Retrieval API Endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import LogEventResponse, PaginatedLogEventsResponse
from src.database.connection import get_db_session
from src.database.repository import DatabaseRepository

router = APIRouter(prefix="/logs", tags=["Logs"])


@router.get("", response_model=PaginatedLogEventsResponse)
async def query_logs(
    service: str | None = Query(None, description="Filter by service name"),
    host: str | None = Query(None, description="Filter by host identifier"),
    severity: str | None = Query(None, description="Filter by log severity (INFO, WARN, ERROR, etc.)"),
    template_id: str | None = Query(None, description="Filter by Drain3 template ID"),
    limit: int = Query(50, ge=1, le=1000, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedLogEventsResponse:
    """Query ingested and parsed log events with multi-attribute filtering."""
    repo = DatabaseRepository(session)
    logs, total = await repo.query_logs(
        service=service,
        host=host,
        severity=severity,
        template_id=template_id,
        limit=limit,
        offset=offset,
    )

    items = [
        LogEventResponse(
            id=log.id,
            timestamp=log.timestamp,
            host=log.host,
            service=log.service,
            component=log.component,
            severity=log.severity,
            template_id=log.template_id,
            message=log.message,
            raw_log=log.raw_log,
            parameters=log.parameters_json or [],
            attributes=log.attributes_json or {},
        )
        for log in logs
    ]

    return PaginatedLogEventsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )

