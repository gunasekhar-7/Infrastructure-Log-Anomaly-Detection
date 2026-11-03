"""API Route Modules."""

from src.api.routes.alerts import router as alerts_router
from src.api.routes.anomalies import router as anomalies_router
from src.api.routes.incidents import router as incidents_router
from src.api.routes.ingest import router as ingest_router
from src.api.routes.logs import router as logs_router
from src.api.routes.models import router as models_router
from src.api.routes.templates import router as templates_router

__all__ = [
    "alerts_router",
    "anomalies_router",
    "incidents_router",
    "ingest_router",
    "logs_router",
    "models_router",
    "templates_router",
]

