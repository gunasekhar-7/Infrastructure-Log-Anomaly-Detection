"""FastAPI Main Application Entrypoint for LogPulse AnomalyGuard."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from config.logging import get_logger
from config.settings import settings
from src.api.middleware import CorrelationAndTimingMiddleware
from src.api.routes import (
    alerts_router,
    anomalies_router,
    incidents_router,
    ingest_router,
    logs_router,
    models_router,
    templates_router,
)
from src.api.schemas import HealthResponse
from src.database.connection import close_db, get_engine, init_db

logger = get_logger("api_main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager ensuring database lifecycle handling."""
    logger.info("Starting up %s v%s...", settings.APP_NAME, settings.APP_VERSION)
    await init_db()
    yield
    logger.info("Shutting down %s...", settings.APP_NAME)
    await close_db()


app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Log Anomaly Detection & Incident Monitoring Platform",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# 1. CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Observability & Timing Middleware
app.add_middleware(CorrelationAndTimingMiddleware)

# 3. Mount Routers under API_PREFIX (/api/v1)
api_prefix = settings.API_PREFIX
app.include_router(ingest_router, prefix=api_prefix)
app.include_router(logs_router, prefix=api_prefix)
app.include_router(templates_router, prefix=api_prefix)
app.include_router(anomalies_router, prefix=api_prefix)
app.include_router(alerts_router, prefix=api_prefix)
app.include_router(incidents_router, prefix=api_prefix)
app.include_router(models_router, prefix=api_prefix)


# 4. Observability Endpoints
@app.get("/healthz", response_model=HealthResponse, tags=["Observability"])
async def health_check() -> HealthResponse:
    """Service health, readiness, and database probe."""
    db_status = "HEALTHY"
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Health check failed database ping: %s", exc)
        db_status = f"UNHEALTHY: {exc}"

    return HealthResponse(
        status="UP" if "HEALTHY" in db_status else "DEGRADED",
        version=settings.APP_VERSION,
        database=db_status,
        timestamp=datetime.now(timezone.utc),
    )


@app.get("/metrics", tags=["Observability"])
def prometheus_metrics() -> Response:
    """Prometheus telemetry scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/", tags=["Root"])
def root_info() -> dict:
    """Root platform metadata and navigational links."""
    return {
        "platform": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "documentation": "/docs",
        "health": "/healthz",
        "metrics": "/metrics",
        "api_v1": {
            "ingest": f"{api_prefix}/ingest",
            "logs": f"{api_prefix}/logs",
            "templates": f"{api_prefix}/templates",
            "anomalies": f"{api_prefix}/anomalies",
            "alerts": f"{api_prefix}/alerts",
            "incidents": f"{api_prefix}/incidents",
            "models": f"{api_prefix}/models",
        },
    }

