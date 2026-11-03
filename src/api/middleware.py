"""API Middleware for Request Correlation, Observability, Security Headers, and Rate Limiting."""

import time
import uuid
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from config.logging import get_logger
from config.settings import settings
from src.api.telemetry import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL

logger = get_logger("api_middleware")


class CorrelationAndTimingMiddleware(BaseHTTPMiddleware):
    """Middleware attaching X-Correlation-ID and X-Response-Time-Ms headers and Prometheus metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_sec = time.perf_counter() - start_time
        duration_ms = duration_sec * 1000.0

        # Attach headers
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

        # Record Prometheus Telemetry
        endpoint = request.url.path
        if endpoint not in ("/metrics", "/healthz"):
            HTTP_REQUESTS_TOTAL.labels(
                method=request.method,
                endpoint=endpoint,
                status=str(response.status_code),
            ).inc()
            HTTP_REQUEST_DURATION_SECONDS.labels(endpoint=endpoint).observe(duration_sec)

            logger.info(
                "%s %s -> status=%d (%.2f ms) [CorrID: %s]",
                request.method,
                endpoint,
                response.status_code,
                duration_ms,
                correlation_id,
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing OWASP Recommended HTTP Security Headers."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        if settings.SECURITY_HEADERS_ENABLED:
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none';"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        return response


class RateLimitingMiddleware(BaseHTTPMiddleware):
    """Sliding-window IP-based Rate Limiter to guard against volumetric denial-of-service."""

    def __init__(self, app, requests_per_minute: int | None = None) -> None:
        super().__init__(app)
        self.rpm = requests_per_minute or settings.RATE_LIMIT_PER_MINUTE
        self.window_sec = 60.0
        self.clients: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Bypass for internal metrics and health probes
        if request.url.path in ("/metrics", "/healthz", "/"):
            return await call_next(request)

        # Identify client (Forwarded-For or client.host)
        forwarded = request.headers.get("X-Forwarded-For")
        client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")

        # Bypass if special bypass header set (for testing or internal agents)
        if request.headers.get("X-Bypass-Rate-Limit") == "test-bypass":
            return await call_next(request)

        now = time.time()
        timestamps = self.clients[client_ip]

        # Prune timestamps older than window
        self.clients[client_ip] = [ts for ts in timestamps if now - ts < self.window_sec]

        if len(self.clients[client_ip]) >= self.rpm:
            retry_after = int(self.window_sec - (now - self.clients[client_ip][0])) + 1
            logger.warning("Rate limit exceeded for IP %s (Max: %d/min)", client_ip, self.rpm)
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "detail": f"Rate limit of {self.rpm} requests per minute exceeded.",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        self.clients[client_ip].append(now)
        return await call_next(request)
