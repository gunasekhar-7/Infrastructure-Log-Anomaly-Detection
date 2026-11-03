"""Prometheus Telemetry & Instrumentation for LogPulse AnomalyGuard."""

from prometheus_client import REGISTRY, Counter, Gauge, Histogram


def _get_or_create_metric(cls, name: str, doc: str, *args, **kwargs):
    """Retrieve existing metric or create a new one to avoid double-registration errors."""
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return cls(name, doc, *args, **kwargs)


# 1. HTTP Request Metrics
HTTP_REQUESTS_TOTAL = _get_or_create_metric(
    Counter,
    "logpulse_http_requests_total",
    "Total HTTP requests received by API",
    ["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = _get_or_create_metric(
    Histogram,
    "logpulse_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

# 2. Pipeline Ingestion & Parsing Metrics
LOG_EVENTS_INGESTED_TOTAL = _get_or_create_metric(
    Counter,
    "logpulse_log_events_ingested_total",
    "Total parsed infrastructure log events ingested",
    ["service", "severity"],
)

DRAIN3_TEMPLATES_GAUGE = _get_or_create_metric(
    Gauge,
    "logpulse_drain3_templates_count",
    "Number of active mined Drain3 log templates in catalog",
)

# 3. Anomaly Detection & AI Metrics
ANOMALIES_DETECTED_TOTAL = _get_or_create_metric(
    Counter,
    "logpulse_anomalies_detected_total",
    "Total detected infrastructure anomalies",
    ["algorithm", "severity", "category"],
)

# 4. Alert & Incident Operational Metrics
ALERTS_TRIGGERED_TOTAL = _get_or_create_metric(
    Counter,
    "logpulse_alerts_triggered_total",
    "Total operational alerts created",
    ["severity", "service"],
)

INCIDENTS_ACTIVE_GAUGE = _get_or_create_metric(
    Gauge,
    "logpulse_incidents_active_count",
    "Count of currently active correlated incidents",
    ["severity"],
)

