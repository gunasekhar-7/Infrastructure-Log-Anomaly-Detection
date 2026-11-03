"""Log Input Validation and Sanitization."""

from pathlib import Path

from src.exceptions import IngestionError

MAX_LINE_LENGTH = 32_768  # 32 KB per log line safeguard
ALLOWED_EXTENSIONS = {".log", ".txt", ".json", ".jsonl", ".csv"}


def validate_file(path: Path | str, max_file_size_mb: int = 500) -> Path:
    """Validate that a target file exists, is readable, and within safe operating parameters."""
    file_path = Path(path).resolve()

    if not file_path.exists():
        raise IngestionError(f"Log file does not exist: {file_path}")
    if not file_path.is_file():
        raise IngestionError(f"Path is not a regular file: {file_path}")

    if file_path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise IngestionError(
            f"Unsupported file extension '{file_path.suffix}'. Allowed: {ALLOWED_EXTENSIONS}"
        )

    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > max_file_size_mb:
        raise IngestionError(
            f"File size {size_mb:.2f} MB exceeds maximum allowed limit of {max_file_size_mb} MB"
        )

    return file_path


def sanitize_line(raw_line: str) -> str:
    """Sanitize raw log line by stripping null bytes and enforcing max length."""
    if not raw_line:
        return ""

    # Strip harmful null characters and trailing whitespace
    cleaned = raw_line.replace("\x00", "").rstrip("\r\n")

    # Enforce safe length boundary
    if len(cleaned) > MAX_LINE_LENGTH:
        cleaned = cleaned[:MAX_LINE_LENGTH] + "...[TRUNCATED]"

    return cleaned

