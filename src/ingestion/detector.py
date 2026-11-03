"""Automatic Log Format Detection and Line Parsing."""

from enum import Enum
import json
import re
from typing import Any
from src.ingestion.models import LogSeverity
from src.ingestion.normalizer import normalize_severity, normalize_timestamp

# Standard regexes for format identification
RE_HDFS = re.compile(
    r"^(?P<date>\d{6})\s+(?P<time>\d{6})\s+(?P<pid>\d+)\s+(?P<level>\w+)\s+(?P<component>[^:]+):\s+(?P<message>.*)$"
)
RE_BGL = re.compile(
    r"^(?P<label>\S+)\s+(?P<epoch>\d+)\s+(?P<date>\S+)\s+(?P<node>\S+)\s+(?P<timestamp>\S+)\s+(?P<node2>\S+)\s+(?P<subsys>\S+)\s+(?P<component>\S+)\s+(?P<level>\w+)\s+(?P<message>.*)$"
)
RE_APP_LOG = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+\[(?P<level>\w+)\]\s+(?:\[(?P<service>[^\]]+)\]\s+)?(?P<message>.*)$"
)
RE_SYSLOG = re.compile(
    r"^(?P<timestamp>[A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<service>[^:\[\s]+)(?:\[(?P<pid>\d+)\])?:\s+(?P<message>.*)$"
)


class LogFormat(str, Enum):
    """Recognized log stream formats."""
    JSON = "JSON"
    HDFS = "HDFS"
    BGL = "BGL"
    APP_LOG = "APP_LOG"
    SYSLOG = "SYSLOG"
    RAW = "RAW"


def detect_line_format(line: str) -> LogFormat:
    """Detect format of an individual log line."""
    stripped = line.strip()
    if not stripped:
        return LogFormat.RAW

    # Check for JSON
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict) and any(k in parsed for k in ("message", "msg", "log", "timestamp")):
                return LogFormat.JSON
        except json.JSONDecodeError:
            pass

    # Check HDFS
    if RE_HDFS.match(stripped):
        return LogFormat.HDFS

    # Check BGL
    if RE_BGL.match(stripped):
        return LogFormat.BGL

    # Check Standard App Log
    if RE_APP_LOG.match(stripped):
        return LogFormat.APP_LOG

    # Check Syslog
    if RE_SYSLOG.match(stripped):
        return LogFormat.SYSLOG

    return LogFormat.RAW


def detect_file_format(sample_lines: list[str]) -> LogFormat:
    """Determine dominant format across a sample of log lines."""
    if not sample_lines:
        return LogFormat.RAW

    counts: dict[LogFormat, int] = {fmt: 0 for fmt in LogFormat}
    for line in sample_lines[:50]:  # Sample up to 50 lines
        fmt = detect_line_format(line)
        counts[fmt] += 1

    # Return format with highest votes
    dominant_format = max(counts.items(), key=lambda kv: kv[1])[0]
    return dominant_format if counts[dominant_format] > 0 else LogFormat.RAW


def parse_detected_line(line: str, expected_format: LogFormat | None = None) -> dict[str, Any]:
    """Parse a log line according to detected or specified format."""
    stripped = line.strip()
    fmt = expected_format or detect_line_format(stripped)

    if fmt == LogFormat.JSON:
        try:
            data = json.loads(stripped)
            msg = data.get("message") or data.get("msg") or data.get("log") or str(data)
            severity = normalize_severity(data.get("level") or data.get("severity"))
            ts = normalize_timestamp(data.get("timestamp") or data.get("time"))
            host = data.get("host") or data.get("hostname") or "localhost"
            service = data.get("service") or data.get("app") or "app"
            component = data.get("component") or data.get("logger") or "default"
            return {
                "format": fmt,
                "timestamp": ts,
                "host": str(host),
                "service": str(service),
                "component": str(component),
                "severity": severity,
                "message": str(msg).strip(),
                "attributes": {k: v for k, v in data.items() if k not in ("message", "msg", "log")},
                "is_valid": True,
            }
        except json.JSONDecodeError:
            pass

    elif fmt == LogFormat.HDFS:
        m = RE_HDFS.match(stripped)
        if m:
            d = m.groupdict()
            ts = normalize_timestamp(f"{d['date']} {d['time']}")
            severity = normalize_severity(d["level"])
            # Extract block ID attribute if present
            blk_match = re.search(r"(blk_-?\d+)", d["message"])
            attributes = {"pid": d["pid"]}
            if blk_match:
                attributes["block_id"] = blk_match.group(1)
            return {
                "format": fmt,
                "timestamp": ts,
                "host": "hdfs-cluster",
                "service": "hadoop-hdfs",
                "component": d["component"].strip(),
                "severity": severity,
                "message": d["message"].strip(),
                "attributes": attributes,
                "is_valid": True,
            }

    elif fmt == LogFormat.BGL:
        m = RE_BGL.match(stripped)
        if m:
            d = m.groupdict()
            ts = normalize_timestamp(d["epoch"])
            severity = normalize_severity(d["level"])
            attributes = {
                "raw_label": d["label"],
                "is_anomaly": d["label"] != "-",
                "subsys": d["subsys"],
                "node": d["node"],
            }
            return {
                "format": fmt,
                "timestamp": ts,
                "host": d["node"],
                "service": d["subsys"].lower(),
                "component": d["component"],
                "severity": severity,
                "message": d["message"].strip(),
                "attributes": attributes,
                "is_valid": True,
            }

    elif fmt == LogFormat.APP_LOG:
        m = RE_APP_LOG.match(stripped)
        if m:
            d = m.groupdict()
            ts = normalize_timestamp(d["timestamp"])
            severity = normalize_severity(d["level"])
            return {
                "format": fmt,
                "timestamp": ts,
                "host": "localhost",
                "service": (d.get("service") or "app").strip(),
                "component": "application",
                "severity": severity,
                "message": d["message"].strip(),
                "attributes": {},
                "is_valid": True,
            }

    elif fmt == LogFormat.SYSLOG:
        m = RE_SYSLOG.match(stripped)
        if m:
            d = m.groupdict()
            ts = normalize_timestamp(d["timestamp"])
            return {
                "format": fmt,
                "timestamp": ts,
                "host": d["host"],
                "service": d["service"],
                "component": d["service"],
                "severity": LogSeverity.INFO,
                "message": d["message"].strip(),
                "attributes": {"pid": d.get("pid")},
                "is_valid": True,
            }

    # Fallback RAW handling
    return {
        "format": LogFormat.RAW,
        "timestamp": normalize_timestamp(None),
        "host": "localhost",
        "service": "unknown",
        "component": "raw",
        "severity": LogSeverity.INFO,
        "message": stripped,
        "attributes": {},
        "is_valid": bool(stripped),
    }

