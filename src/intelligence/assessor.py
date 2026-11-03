"""Anomaly Assessment and Prioritization Engine."""

from datetime import datetime, timezone
from typing import Any

from src.features.models import SequenceSample, WindowFeatureRecord
from src.intelligence.explainer import AnomalyExplainer
from src.intelligence.models import (
    AnomalyCategory,
    AnomalySeverity,
    DetectedAnomaly,
    InvestigationStatus,
)
from src.intelligence.prioritizer import SeverityPrioritizer
from src.parsing.models import ParsedLogEvent


class AnomalyAssessor:
    """Evaluates raw model outputs, classifies category, assigns severity, and attaches evidence."""

    def __init__(
        self,
        prioritizer: SeverityPrioritizer | None = None,
        explainer: AnomalyExplainer | None = None,
    ) -> None:
        self.prioritizer = prioritizer or SeverityPrioritizer()
        self.explainer = explainer or AnomalyExplainer()

    def assess_window(
        self,
        window: WindowFeatureRecord,
        events: list[ParsedLogEvent],
        anomaly_score: float,
        algorithm: str = "ISOLATION_FOREST",
    ) -> DetectedAnomaly:
        """Create structured DetectedAnomaly for a window-based outlier."""
        score = float(anomaly_score)
        category = AnomalyCategory.FREQUENCY_SPIKE

        fatal_count = sum(1 for e in events if e.severity.value == "FATAL")
        severity = self.prioritizer.calculate_severity(
            anomaly_score=score,
            error_count=window.error_count,
            fatal_count=fatal_count,
            error_rate=window.error_rate,
            category=category,
        )

        explanation, evidence = self.explainer.explain_volumetric_anomaly(
            window=window,
            events=events,
            anomaly_score=score,
            algorithm=algorithm,
        )

        host = events[0].host if events else "localhost"
        service = events[0].service if events else "default"
        related_templates = list(window.template_counts.keys())

        return DetectedAnomaly(
            timestamp=window.end_time,
            host=host,
            service=service,
            anomaly_score=round(score, 4),
            severity=severity,
            anomaly_category=category,
            algorithm=algorithm,
            explanation=explanation,
            related_templates=related_templates,
            supporting_evidence=evidence,
            investigation_status=InvestigationStatus.UNINVESTIGATED,
            context_metadata={
                "window_id": window.window_id,
                "event_count": window.event_count,
                "error_rate": window.error_rate,
                "template_entropy": window.template_entropy,
            },
        )

    def assess_sequence(
        self,
        sample: SequenceSample,
        actual_event: ParsedLogEvent,
        anomaly_score: float,
        expected_candidates: list[str],
        candidate_prob_sum: float = 0.95,
        algorithm: str = "DEEPLOG_LSTM",
    ) -> DetectedAnomaly:
        """Create structured DetectedAnomaly for a sequential next-token deviation."""
        score = float(anomaly_score)
        category = AnomalyCategory.SEQUENCE_DEVIATION

        is_error = actual_event.severity.value in ("ERROR", "FATAL")
        severity = self.prioritizer.calculate_severity(
            anomaly_score=score,
            error_count=1 if is_error else 0,
            fatal_count=1 if actual_event.severity.value == "FATAL" else 0,
            error_rate=1.0 if is_error else 0.0,
            category=category,
        )

        explanation, evidence = self.explainer.explain_sequential_anomaly(
            sample=sample,
            actual_event=actual_event,
            expected_candidates=expected_candidates,
            candidate_prob_sum=candidate_prob_sum,
            anomaly_score=score,
        )

        related = list(dict.fromkeys(sample.sequence_templates + [sample.next_template]))

        return DetectedAnomaly(
            timestamp=actual_event.timestamp,
            host=actual_event.host,
            service=actual_event.service,
            anomaly_score=round(score, 4),
            severity=severity,
            anomaly_category=category,
            algorithm=algorithm,
            explanation=explanation,
            related_templates=related,
            supporting_evidence=evidence,
            investigation_status=InvestigationStatus.UNINVESTIGATED,
            context_metadata={
                "sample_id": sample.sample_id,
                "block_id": sample.block_id,
                "expected_candidates": expected_candidates,
            },
        )

    def assess_unseen_template(
        self,
        event: ParsedLogEvent,
        anomaly_score: float = 0.65,
        algorithm: str = "DRAIN3_ONLINE",
    ) -> DetectedAnomaly:
        """Create structured DetectedAnomaly for a novel unseen log template."""
        score = float(anomaly_score)
        category = AnomalyCategory.UNSEEN_TEMPLATE

        is_error = event.severity.value in ("ERROR", "FATAL")
        severity = self.prioritizer.calculate_severity(
            anomaly_score=score,
            error_count=1 if is_error else 0,
            is_unseen_template=True,
            category=category,
        )

        explanation, evidence = self.explainer.explain_unseen_template(
            event=event,
            anomaly_score=score,
        )

        return DetectedAnomaly(
            timestamp=event.timestamp,
            host=event.host,
            service=event.service,
            anomaly_score=round(score, 4),
            severity=severity,
            anomaly_category=category,
            algorithm=algorithm,
            explanation=explanation,
            related_templates=[event.template_id],
            supporting_evidence=evidence,
            investigation_status=InvestigationStatus.UNINVESTIGATED,
            context_metadata={
                "template_pattern": event.template_text,
                "component": event.component,
            },
        )
