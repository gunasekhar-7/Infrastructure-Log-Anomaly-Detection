"""Unified High-Throughput Log Ingestion Engine."""

import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from config.logging import get_logger
from src.ingestion.dead_letter import DeadLetterQueue
from src.ingestion.deduplicator import DuplicateDetector
from src.ingestion.detector import (
    LogFormat,
    detect_file_format,
    parse_detected_line,
)
from src.ingestion.models import (
    IngestionStats,
    LogEvent,
    ParsingStatus,
)
from src.ingestion.validator import sanitize_line, validate_file

logger = get_logger("ingestion_engine")


class LogIngestionEngine:
    """Unified engine for ingesting, validating, and normalizing infrastructure logs."""

    def __init__(
        self,
        dead_letter_dump: Path | None = None,
        dedup_capacity: int = 10_000,
        enable_deduplication: bool = True,
    ) -> None:
        self.dead_letter = DeadLetterQueue(dump_file=dead_letter_dump)
        self.dedup = DuplicateDetector(capacity=dedup_capacity)
        self.enable_deduplication = enable_deduplication

    def ingest_line(
        self,
        raw_line: str,
        source_id: str = "stream",
        expected_format: LogFormat | None = None,
    ) -> LogEvent:
        """Ingest, validate, and convert a single raw log string into a normalized LogEvent."""
        sanitized = sanitize_line(raw_line)
        if not sanitized:
            self.dead_letter.record_failure(
                raw_content=raw_line,
                failure_reason="Empty or whitespace-only log record",
                source_id=source_id,
            )
            return LogEvent(
                message="",
                raw_log=raw_line,
                source_id=source_id,
                parsing_status=ParsingStatus.INVALID_FORMAT,
            )

        parsed = parse_detected_line(sanitized, expected_format=expected_format)
        is_valid = parsed.get("is_valid", False)
        parsing_status = ParsingStatus.VALID if is_valid else ParsingStatus.FALLBACK

        if not is_valid:
            self.dead_letter.record_failure(
                raw_content=raw_line,
                failure_reason="Unrecognized log format structure",
                source_id=source_id,
            )

        # Check for duplicates
        is_dup = False
        if self.enable_deduplication:
            ts_epoch = parsed["timestamp"].timestamp()
            is_dup = self.dedup.is_duplicate(
                host=parsed["host"],
                service=parsed["service"],
                message=parsed["message"],
                timestamp_epoch=ts_epoch,
            )

        return LogEvent(
            timestamp=parsed["timestamp"],
            host=parsed["host"],
            service=parsed["service"],
            component=parsed["component"],
            severity=parsed["severity"],
            message=parsed["message"],
            raw_log=raw_line,
            source_id=source_id,
            parsing_status=parsing_status,
            is_duplicate=is_dup,
            attributes=parsed.get("attributes", {}),
        )

    def ingest_stream(
        self,
        lines: Iterable[str],
        source_id: str = "stream",
        expected_format: LogFormat | None = None,
    ) -> tuple[list[LogEvent], IngestionStats]:
        """Ingest an iterable stream of raw log lines with telemetry tracking."""
        start_time = time.perf_counter()
        events: list[LogEvent] = []
        total_bytes = 0
        valid_count = 0
        invalid_count = 0
        duplicate_count = 0

        for line in lines:
            total_bytes += len(line.encode("utf-8", errors="replace"))
            event = self.ingest_line(line, source_id=source_id, expected_format=expected_format)
            events.append(event)

            if event.parsing_status == ParsingStatus.VALID:
                valid_count += 1
            else:
                invalid_count += 1

            if event.is_duplicate:
                duplicate_count += 1

        duration_sec = time.perf_counter() - start_time
        duration_ms = duration_sec * 1000.0
        total_records = len(events)
        throughput = (total_records / duration_sec) if duration_sec > 0 else 0.0

        stats = IngestionStats(
            source_id=source_id,
            total_records=total_records,
            valid_records=valid_count,
            invalid_records=invalid_count,
            duplicate_records=duplicate_count,
            bytes_processed=total_bytes,
            duration_ms=round(duration_ms, 2),
            throughput_eps=round(throughput, 2),
        )

        logger.info(
            "Ingested %d events from '%s' in %.2f ms (%.1f EPS, %d valid, %d duplicates)",
            total_records,
            source_id,
            duration_ms,
            throughput,
            valid_count,
            duplicate_count,
        )

        return events, stats

    def ingest_file(
        self,
        path: Path | str,
        source_id: str | None = None,
        expected_format: LogFormat | None = None,
    ) -> tuple[list[LogEvent], IngestionStats]:
        """Ingest and normalize a local log file."""
        validated_path = validate_file(path)
        resolved_source_id = source_id or validated_path.name

        # Sample initial lines to auto-detect file format if not provided
        sample_lines: list[str] = []
        with open(validated_path, encoding="utf-8", errors="replace") as f:
            for _ in range(30):
                line = f.readline()
                if not line:
                    break
                sample_lines.append(line)

        detected_fmt = expected_format or detect_file_format(sample_lines)
        logger.info("Auto-detected format '%s' for file '%s'", detected_fmt.value, validated_path)

        def file_line_generator():
            with open(validated_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    yield line

        return self.ingest_stream(
            file_line_generator(),
            source_id=resolved_source_id,
            expected_format=detected_fmt,
        )

    def ingest_json_records(
        self,
        records: list[dict[str, Any]],
        source_id: str = "json_stream",
    ) -> tuple[list[LogEvent], IngestionStats]:
        """Ingest pre-parsed structured JSON records (e.g. from HTTP API payload)."""
        import json
        lines = [json.dumps(r) for r in records]
        return self.ingest_stream(lines, source_id=source_id, expected_format=LogFormat.JSON)

