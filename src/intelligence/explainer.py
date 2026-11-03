"""Factual Evidence and Explainability Engine for Detected Anomalies."""

from typing import Any
from src.features.models import SequenceSample, WindowFeatureRecord
from src.intelligence.models import AnomalyCategory, LogEvidenceItem
from src.parsing.models import ParsedLogEvent


class AnomalyExplainer:
    """Generates objective, evidence-based natural language explanations and attaches supporting logs."""

    def explain_volumetric_anomaly(
        self,
        window: WindowFeatureRecord,
        events: list[ParsedLogEvent],
        anomaly_score: float,
        algorithm: str,
    ) -> tuple[str, list[LogEvidenceItem]]:
        """Construct factual explanation and evidence for frequency / error spikes."""
        explanation_parts = [
            f"Anomalous event frequency pattern detected by {algorithm} (score: {anomaly_score:.2f})."
        ]

        if window.error_count > 0:
            explanation_parts.append(
                f"Observed {window.error_count} error/fatal events out of {window.event_count} total logs "
                f"(error rate: {window.error_rate * 100:.1f}%)."
            )
        else:
            explanation_parts.append(
                f"Volumetric surge observed with {window.event_count} events and template entropy {window.template_entropy:.2f}."
            )

        # Highlight most frequent and error templates
        top_templates = sorted(window.template_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
        tmpl_str = ", ".join(f"{t} ({cnt}x)" for t, cnt in top_templates)
        explanation_parts.append(f"Dominant templates in window: {tmpl_str}.")

        # Collect supporting evidence
        evidence_items: list[LogEvidenceItem] = []
        for ev in events:
            is_err = ev.severity.value in ("ERROR", "FATAL")
            is_warn = ev.severity.value == "WARN"
            if is_err or is_warn or len(evidence_items) < 3:
                evidence_items.append(
                    LogEvidenceItem(
                        event_id=ev.event_id,
                        timestamp=ev.timestamp,
                        template_id=ev.template_id,
                        raw_message=ev.raw_log,
                        severity=ev.severity.value,
                        is_trigger=is_err,
                        reason="Error event contributing to window error rate" if is_err else "Supporting context in window",
                    )
                )

        full_explanation = " ".join(explanation_parts)
        return full_explanation, evidence_items[:10]

    def explain_sequential_anomaly(
        self,
        sample: SequenceSample,
        actual_event: ParsedLogEvent,
        expected_candidates: list[str],
        candidate_prob_sum: float,
        anomaly_score: float,
    ) -> tuple[str, list[LogEvidenceItem]]:
        """Construct factual explanation and evidence for DeepLog sequential breaks."""
        prev_tmpl = sample.sequence_templates[-1] if sample.sequence_templates else "START"
        actual_tmpl = sample.next_template
        candidates_str = ", ".join(expected_candidates) if expected_candidates else "None"

        explanation = (
            f"Sequential path anomaly detected by DeepLog (score: {anomaly_score:.2f}). "
            f"Following template '{prev_tmpl}', observed unexpected event transition to '{actual_tmpl}'. "
            f"The model expected one of top candidates [{candidates_str}] (cumulative probability: {candidate_prob_sum * 100:.1f}%). "
            f"Triggering log record: \"{actual_event.raw_log}\"."
        )

        evidence_items = [
            LogEvidenceItem(
                event_id=actual_event.event_id,
                timestamp=actual_event.timestamp,
                template_id=actual_tmpl,
                raw_message=actual_event.raw_log,
                severity=actual_event.severity.value,
                is_trigger=True,
                reason=f"Unexpected next event following '{prev_tmpl}'; expected [{candidates_str}]",
            )
        ]

        return explanation, evidence_items

    def explain_unseen_template(
        self,
        event: ParsedLogEvent,
        anomaly_score: float,
    ) -> tuple[str, list[LogEvidenceItem]]:
        """Construct explanation for newly registered unseen templates."""
        explanation = (
            f"Previously unseen log template '{event.template_id}' detected (score: {anomaly_score:.2f}). "
            f"Template pattern: \"{event.template_text}\". "
            f"First occurrence observed in service '{event.service}' on host '{event.host}'."
        )

        evidence = [
            LogEvidenceItem(
                event_id=event.event_id,
                timestamp=event.timestamp,
                template_id=event.template_id,
                raw_message=event.raw_log,
                severity=event.severity.value,
                is_trigger=True,
                reason=f"First appearance of template {event.template_id}",
            )
        ]

        return explanation, evidence

