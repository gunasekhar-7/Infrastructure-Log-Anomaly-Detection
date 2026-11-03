"""Dead-Letter Queue for Unparseable and Malformed Log Records."""

from collections import deque
from pathlib import Path

from config.logging import get_logger
from src.ingestion.models import DeadLetterRecord

logger = get_logger("dead_letter_queue")


class DeadLetterQueue:
    """Safely store rejected or corrupt log records for forensic analysis and zero data loss."""

    def __init__(self, max_size: int = 50_000, dump_file: Path | None = None) -> None:
        self.max_size = max_size
        self.dump_file = dump_file
        self._queue: deque[DeadLetterRecord] = deque(maxlen=max_size)

    def record_failure(self, raw_content: str, failure_reason: str, source_id: str = "unknown") -> DeadLetterRecord:
        """Add rejected entry to dead-letter storage."""
        record = DeadLetterRecord(
            raw_content=raw_content,
            failure_reason=failure_reason,
            source_id=source_id,
        )
        self._queue.append(record)

        if self.dump_file:
            try:
                self.dump_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.dump_file, "a", encoding="utf-8") as f:
                    f.write(f"[{record.timestamp.isoformat()}] [{source_id}] Reason: {failure_reason} | Content: {raw_content}\n")
            except Exception as e:
                logger.error("Failed to append to dead-letter dump file %s: %s", self.dump_file, e)

        return record

    def get_recent_failures(self, limit: int = 50) -> list[DeadLetterRecord]:
        """Retrieve most recent dead-letter records."""
        items = list(self._queue)
        return items[-limit:]

    @property
    def total_failures(self) -> int:
        """Count of dead-letter records captured."""
        return len(self._queue)

    def clear(self) -> None:
        """Clear queue entries."""
        self._queue.clear()

