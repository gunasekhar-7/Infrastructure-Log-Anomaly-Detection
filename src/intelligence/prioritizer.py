"""Contextual Multi-Factor Anomaly Severity Prioritizer."""

from typing import Any
from src.intelligence.models import AnomalyCategory, AnomalySeverity


class SeverityPrioritizer:
    """Calculates operational triage severity combining ML confidence with domain signals."""

    def __init__(
        self,
        critical_score_threshold: float = 0.85,
        high_score_threshold: float = 0.70,
        medium_score_threshold: float = 0.50,
        low_score_threshold: float = 0.35,
    ) -> None:
        self.critical_score_threshold = critical_score_threshold
        self.high_score_threshold = high_score_threshold
        self.medium_score_threshold = medium_score_threshold
        self.low_score_threshold = low_score_threshold

    def calculate_severity(
        self,
        anomaly_score: float,
        error_count: int = 0,
        fatal_count: int = 0,
        error_rate: float = 0.0,
        category: AnomalyCategory = AnomalyCategory.FREQUENCY_SPIKE,
        is_unseen_template: bool = False,
    ) -> AnomalySeverity:
        """Assign categorical severity using contextual multi-factor evaluation."""
        score = float(anomaly_score)

        # 1. CRITICAL: Confirmed severe infrastructure failure signals
        if fatal_count > 0 and score >= 0.6:
            return AnomalySeverity.CRITICAL
        if error_rate >= 0.5 and score >= self.high_score_threshold:
            return AnomalySeverity.CRITICAL
        if score >= self.critical_score_threshold and error_count >= 3:
            return AnomalySeverity.CRITICAL

        # 2. HIGH: Substantial sequence break or significant error rate
        if error_count > 0 and score >= self.high_score_threshold:
            return AnomalySeverity.HIGH
        if category == AnomalyCategory.SEQUENCE_DEVIATION and error_count > 0:
            return AnomalySeverity.HIGH
        if score >= self.high_score_threshold:
            return AnomalySeverity.HIGH
        if error_rate >= 0.25:
            return AnomalySeverity.HIGH

        # 3. MEDIUM: Notable deviation or unverified unusual sequence
        if score >= self.medium_score_threshold:
            return AnomalySeverity.MEDIUM
        if category == AnomalyCategory.SEQUENCE_DEVIATION:
            return AnomalySeverity.MEDIUM
        if is_unseen_template and error_count > 0:
            return AnomalySeverity.MEDIUM

        # 4. LOW: Mild statistical drift or isolated warning
        if score >= self.low_score_threshold or is_unseen_template:
            return AnomalySeverity.LOW

        # 5. INFO: Below operational attention threshold
        return AnomalySeverity.INFO
