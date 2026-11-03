"""Drain3 Online Log Template Mining Engine."""

from pathlib import Path
from typing import Any

from drain3.file_persistence import FilePersistence
from drain3.template_miner import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

from config.logging import get_logger
from src.exceptions import ParsingError
from src.ingestion.models import LogEvent
from src.parsing.masks import get_default_masking_instructions
from src.parsing.models import ParsedLogEvent
from src.parsing.template_store import TemplateCatalog

logger = get_logger("drain_parser")


class DrainParser:
    """Production-grade online log template miner based on Drain3 tree clustering."""

    def __init__(
        self,
        config_path: Path | str | None = None,
        state_file: Path | str | None = None,
        catalog_path: Path | str | None = None,
        sim_th: float = 0.5,
        depth: int = 4,
        max_children: int = 100,
    ) -> None:
        self.state_file = Path(state_file) if state_file else None
        self.catalog = TemplateCatalog(
            persistence_path=Path(catalog_path) if catalog_path else None
        )

        # Configure Drain3 Miner
        config = TemplateMinerConfig()
        if config_path and Path(config_path).exists():
            config.load(str(config_path))
        else:
            config.drain_sim_th = sim_th
            config.drain_depth = depth
            config.drain_max_children = max_children

        # Attach custom parameter masking rules
        config.masking_instructions = get_default_masking_instructions()

        # Optional persistence handler for Drain3 tree
        persistence = FilePersistence(str(self.state_file)) if self.state_file else None

        self.miner = TemplateMiner(persistence_handler=persistence, config=config)
        logger.info(
            "DrainParser initialized (sim_th=%.2f, depth=%d, max_children=%d, state_file=%s)",
            config.drain_sim_th,
            config.drain_depth,
            config.drain_max_children,
            self.state_file,
        )

    def parse_message(self, message: str) -> tuple[str, str, list[str], bool]:
        """Parse raw log text into (template_id, template_mined, extracted_parameters, is_unseen)."""
        clean_msg = message.strip()
        if not clean_msg:
            return "E0", "", [], False

        try:
            result = self.miner.add_log_message(clean_msg)
            cluster_id = result["cluster_id"]
            template_mined = result["template_mined"]
            change_type = result["change_type"]

            # Extract dynamic parameters matching wildcards
            raw_params = self.miner.extract_parameters(template_mined, clean_msg)
            extracted_params: list[str] = (
                [p.value for p in raw_params] if raw_params else []
            )

            # Register with catalog
            template_record, is_unseen = self.catalog.register_or_update(
                cluster_id=cluster_id,
                template_pattern=template_mined,
                sample_params=extracted_params,
            )

            # Flag as unseen if either cluster was just created or catalog detected unseen
            unseen = is_unseen or (change_type == "cluster_created")

            return template_record.template_id, template_mined, extracted_params, unseen

        except Exception as exc:
            logger.error("Failed to parse log message '%s': %s", message, exc)
            raise ParsingError(f"Drain3 parsing failed on message: {message}", details={"error": str(exc)}) from exc

    def parse_event(self, event: LogEvent) -> ParsedLogEvent:
        """Parse an individual ingested LogEvent into a structured ParsedLogEvent."""
        tmpl_id, tmpl_text, params, is_unseen = self.parse_message(event.message)

        return ParsedLogEvent.from_log_event(
            event=event,
            template_id=tmpl_id,
            template_text=tmpl_text,
            parameters=params,
            is_unseen_template=is_unseen,
        )

    def parse_batch(self, events: list[LogEvent]) -> list[ParsedLogEvent]:
        """Parse a batch of LogEvents sequentially, maintaining online tree state."""
        parsed_events: list[ParsedLogEvent] = []
        for event in events:
            parsed_events.append(self.parse_event(event))
        return parsed_events

    def save_state(self) -> None:
        """Persist Drain3 miner tree snapshot and template catalog."""
        if self.state_file:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.miner.save_state("Drain3 manual snapshot")
        if self.catalog.persistence_path:
            self.catalog.save()
        logger.info("Saved Drain3 parser state and catalog.")

    def get_template_vocabulary(self) -> dict[str, int]:
        """Return mapping of canonical template_id -> integer index for ML sequence models."""
        vocab: dict[str, int] = {}
        # Reserve 0 for padding, 1 for UNK (unseen)
        vocab["<PAD>"] = 0
        vocab["<UNK>"] = 1
        for idx, tmpl in enumerate(self.catalog.get_all_templates(), start=2):
            vocab[tmpl.template_id] = idx
        return vocab

    def get_template_count(self) -> int:
        """Return total count of mined templates."""
        return self.catalog.total_templates

