"""API Middleware for Request Correlation, Timing, and Observability."""

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from config.logging import get_logger

logger = get_logger("api_middleware")


class CorrelationAndTimingMiddleware(BaseHTTPMiddleware):
    """Middleware attaching X-Correlation-ID and X-Response-Time-Ms headers to every HTTP request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Attach response headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

        # Exclude prometheus /metrics and /healthz from high-frequency access logs
        if request.url.path not in ("/metrics", "/healthz"):
            logger.info(
                "%s %s -> status=%d (%.2f ms) [CorrID: %s]",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                correlation_id,
            )

        return response

