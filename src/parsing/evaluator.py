"""Parser Evaluation and Template Stability Metrics."""

import time
from typing import Any

from config.logging import get_logger
from src.ingestion.models import LogEvent
from src.parsing.drain_engine import DrainParser

logger = get_logger("parser_evaluator")


class ParserEvaluator:
    """Benchmark and evaluate Drain3 template mining accuracy and stability."""

    def __init__(self, parser: DrainParser) -> None:
        self.parser = parser

    def evaluate_stream(self, events: list[LogEvent]) -> dict[str, Any]:
        """Process log stream and calculate parsing throughput and template discovery trajectory."""
        start_time = time.perf_counter()
        total_logs = len(events)
        if total_logs == 0:
            return {"error": "Empty event list"}

        new_template_counts: list[int] = []
        parsed_events = []
        param_extraction_count = 0

        for idx, event in enumerate(events, start=1):
            parsed = self.parser.parse_event(event)
            parsed_events.append(parsed)
            if parsed.parameters:
                param_extraction_count += 1
            if idx % 500 == 0 or idx == total_logs:
                new_template_counts.append(self.parser.catalog.total_templates)

        duration_sec = time.perf_counter() - start_time
        throughput = (total_logs / duration_sec) if duration_sec > 0 else 0.0

        # Template stability: ratio of templates discovered in second half vs first half of stream
        first_half_templates = new_template_counts[0] if new_template_counts else 0
        total_final_templates = self.parser.catalog.total_templates
        second_half_growth = total_final_templates - first_half_templates

        metrics = {
            "total_logs_evaluated": total_logs,
            "duration_sec": round(duration_sec, 4),
            "throughput_logs_per_sec": round(throughput, 2),
            "unique_templates_mined": total_final_templates,
            "logs_with_parameters_extracted": param_extraction_count,
            "parameter_extraction_ratio": round(param_extraction_count / total_logs, 4),
            "template_growth_trajectory": new_template_counts,
            "template_stability_metric": "STABLE" if second_half_growth <= (first_half_templates * 0.5) else "GROWING",
        }

        logger.info(
            "Parser Evaluation: %d logs in %.2fs (%.1f logs/s, %d unique templates, stability: %s)",
            total_logs,
            duration_sec,
            throughput,
            total_final_templates,
            metrics["template_stability_metric"],
        )

        return metrics

