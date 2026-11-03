"""Template Store and Catalog for Drain3 Mined Templates."""

from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from typing import Any

from config.logging import get_logger
from src.parsing.models import LogTemplate

logger = get_logger("template_store")


class TemplateCatalog:
    """Thread-safe persistent registry of all identified log templates."""

    def __init__(self, persistence_path: Path | None = None) -> None:
        self.persistence_path = persistence_path
        self._templates: dict[str, LogTemplate] = {}
        self._pattern_to_id: dict[str, str] = {}
        self._lock = RLock()

        if self.persistence_path and self.persistence_path.exists():
            self.load()

    def register_or_update(
        self,
        cluster_id: int | str,
        template_pattern: str,
        sample_params: list[str] | None = None,
    ) -> tuple[LogTemplate, bool]:
        """Register a new template cluster or update occurrence metadata for an existing one."""
        canonical_id = f"E{cluster_id}"
        now = datetime.now(timezone.utc)

        with self._lock:
            if canonical_id in self._templates:
                tmpl = self._templates[canonical_id]
                tmpl.template_pattern = template_pattern
                tmpl.occurrence_count += 1
                tmpl.last_seen = now
                if sample_params:
                    tmpl.sample_parameters = sample_params[:5]
                is_unseen = False
            else:
                tmpl = LogTemplate(
                    template_id=canonical_id,
                    template_pattern=template_pattern,
                    occurrence_count=1,
                    first_seen=now,
                    last_seen=now,
                    sample_parameters=sample_params[:5] if sample_params else [],
                )
                self._templates[canonical_id] = tmpl
                self._pattern_to_id[template_pattern] = canonical_id
                is_unseen = True
                logger.debug("New template registered: %s -> %s", canonical_id, template_pattern)

        return tmpl, is_unseen

    def get_template(self, template_id: str) -> LogTemplate | None:
        """Lookup template by canonical template ID."""
        with self._lock:
            return self._templates.get(template_id)

    def get_all_templates(self) -> list[LogTemplate]:
        """Retrieve snapshot list of all registered templates."""
        with self._lock:
            return list(self._templates.values())

    @property
    def total_templates(self) -> int:
        """Total unique template clusters identified."""
        with self._lock:
            return len(self._templates)

    def save(self, target_path: Path | None = None) -> None:
        """Persist catalog to JSON file."""
        dest = target_path or self.persistence_path
        if not dest:
            return

        dest.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            data = {
                t_id: {
                    "template_id": t.template_id,
                    "template_pattern": t.template_pattern,
                    "occurrence_count": t.occurrence_count,
                    "first_seen": t.first_seen.isoformat(),
                    "last_seen": t.last_seen.isoformat(),
                    "sample_parameters": t.sample_parameters,
                }
                for t_id, t in self._templates.items()
            }

        with open(dest, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved %d templates to %s", len(data), dest)

    def load(self, source_path: Path | None = None) -> None:
        """Load catalog from persisted JSON file."""
        src = source_path or self.persistence_path
        if not src or not src.exists():
            return

        with open(src, "r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)

        with self._lock:
            self._templates.clear()
            self._pattern_to_id.clear()
            for t_id, record in data.items():
                tmpl = LogTemplate(
                    template_id=record["template_id"],
                    template_pattern=record["template_pattern"],
                    occurrence_count=record["occurrence_count"],
                    first_seen=datetime.fromisoformat(record["first_seen"]),
                    last_seen=datetime.fromisoformat(record["last_seen"]),
                    sample_parameters=record.get("sample_parameters", []),
                )
                self._templates[t_id] = tmpl
                self._pattern_to_id[tmpl.template_pattern] = t_id

        logger.info("Loaded %d templates from %s", len(self._templates), src)

    def clear(self) -> None:
        """Clear all registered templates."""
        with self._lock:
            self._templates.clear()
            self._pattern_to_id.clear()

