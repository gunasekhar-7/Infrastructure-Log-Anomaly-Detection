"""Log Template Catalog API Endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.schemas import LogTemplateResponse, PaginatedTemplatesResponse
from src.database.connection import get_db_session
from src.database.repository import DatabaseRepository

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get("", response_model=PaginatedTemplatesResponse)
async def list_templates(
    limit: int = Query(100, ge=1, le=1000, description="Page limit"),
    offset: int = Query(0, ge=0, description="Page offset"),
    session: AsyncSession = Depends(get_db_session),
) -> PaginatedTemplatesResponse:
    """Retrieve catalog of mined Drain3 log templates ordered by frequency."""
    repo = DatabaseRepository(session)
    templates, total = await repo.get_templates(limit=limit, offset=offset)

    items = [
        LogTemplateResponse(
            template_id=tmpl.template_id,
            template_pattern=tmpl.template_pattern,
            occurrence_count=tmpl.occurrence_count,
            sample_parameters=[str(p) for p in (tmpl.sample_parameters_json or [])],
            first_seen=tmpl.first_seen,
            last_seen=tmpl.last_seen,
        )
        for tmpl in templates
    ]

    return PaginatedTemplatesResponse(
        items=items,
        total=total,
    )

