"""Frequency-Based and Rare Pattern Anomaly Detector."""

import json
from collections import Counter
from pathlib import Path

import numpy as np

from config.logging import get_logger
from src.exceptions import ModelNotTrainedError
from src.models.base import BaseAnomalyDetector

logger = get_logger("frequency_detector")


class FrequencyAnomalyDetector(BaseAnomalyDetector):
    """Detects anomalies based on template sparsity, rare transitions, and abnormal event distributions."""

    def __init__(
        self,
        rare_template_threshold: float = 0.01,
        rare_transition_penalty: float = 0.8,
        version: str = "v1.0",
    ) -> None:
        super().__init__(
            model_name="FrequencyAnomalyDetector",
            algorithm="FREQUENCY_RARE_PATTERN",
            version=version,
            threshold=0.5,
        )
        self.rare_template_threshold = rare_template_threshold
        self.rare_transition_penalty = rare_transition_penalty

        self.template_priors: dict[str, float] = {}
        self.transition_matrix: dict[str, dict[str, float]] = {}
        self.total_training_events: int = 0
        self.hyperparameters = {
            "rare_template_threshold": rare_template_threshold,
            "rare_transition_penalty": rare_transition_penalty,
        }

    def fit_from_sequences(
        self,
        template_sequences: list[list[str]],
    ) -> "FrequencyAnomalyDetector":
        """Profile normal template distribution and pairwise state transitions."""
        template_counts: Counter[str] = Counter()
        transition_counts: dict[str, Counter[str]] = {}
        total_transitions = 0

        for seq in template_sequences:
            for i, tmpl in enumerate(seq):
                template_counts[tmpl] += 1
                if i > 0:
                    prev_t = seq[i - 1]
                    transition_counts.setdefault(prev_t, Counter())[tmpl] += 1
                    total_transitions += 1

        self.total_training_events = sum(template_counts.values())
        if self.total_training_events == 0:
            raise ValueError("Cannot fit FrequencyAnomalyDetector on empty sequences.")

        # Compute prior probabilities P(e)
        self.template_priors = {
            t: count / self.total_training_events for t, count in template_counts.items()
        }

        # Compute transition probabilities P(e_t | e_{t-1})
        self.transition_matrix = {}
        for prev_t, next_counts in transition_counts.items():
            total_from_prev = sum(next_counts.values())
            self.transition_matrix[prev_t] = {
                next_t: c / total_from_prev for next_t, c in next_counts.items()
            }

        self.is_fitted = True
        self.training_metadata = {
            "total_events": self.total_training_events,
            "unique_templates": len(self.template_priors),
            "unique_transitions": total_transitions,
        }
        logger.info(
            "Fitted FrequencyAnomalyDetector on %d events (%d templates, %d transitions).",
            self.total_training_events,
            len(self.template_priors),
            total_transitions,
        )
        return self

    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> "FrequencyAnomalyDetector":
        """Compatibility fit using tabular template count columns (assumed columns starting from index 11)."""
        # For tabular matrices, we treat columns as template frequencies
        self.total_training_events = int(np.sum(X))
        col_sums = np.sum(X, axis=0)
        total = np.sum(col_sums) if np.sum(col_sums) > 0 else 1.0
        self.template_priors = {
            f"T{i}": float(col_sums[i] / total) for i in range(X.shape[1])
        }
        self.is_fitted = True
        self.training_metadata = {
            "n_samples": int(X.shape[0]),
            "n_features": int(X.shape[1]),
        }
        return self

    def score_sequence(self, sequence: list[str]) -> float:
        """Calculate anomaly score for a single template sequence."""
        if not self.is_fitted:
            raise ModelNotTrainedError("FrequencyAnomalyDetector is not fitted.")

        if not sequence:
            return 0.0

        n = len(sequence)
        rare_count = 0
        unexpected_transitions = 0

        for i, t in enumerate(sequence):
            p = self.template_priors.get(t, 0.0)
            if p < self.rare_template_threshold:
                rare_count += 1

            if i > 0:
                prev_t = sequence[i - 1]
                p_trans = self.transition_matrix.get(prev_t, {}).get(t, 0.0)
                if p_trans < 1e-4:  # Unseen or impossible transition
                    unexpected_transitions += 1

        rare_ratio = rare_count / n
        trans_ratio = unexpected_transitions / (n - 1) if n > 1 else 0.0

        # Weighted combination of rarity and transition surprise
        score = 0.5 * rare_ratio + 0.5 * trans_ratio
        return float(np.clip(score, 0.0, 1.0))

    def score(self, X: np.ndarray) -> np.ndarray:
        """Compute tabular anomaly scores based on presence of rare template frequencies."""
        if not self.is_fitted:
            raise ModelNotTrainedError("FrequencyAnomalyDetector is not fitted.")

        scores = np.zeros(X.shape[0], dtype=np.float32)
        # Identify columns with rare priors
        rare_indices = [
            i for i, (t, p) in enumerate(self.template_priors.items()) if p < self.rare_template_threshold
        ]

        if not rare_indices:
            # If no templates are rare, score based on negative log frequency
            return np.zeros(X.shape[0], dtype=np.float32)

        for row_idx in range(X.shape[0]):
            rare_activity = np.sum(X[row_idx, rare_indices])
            # Sigmoid saturation of rare activity
            scores[row_idx] = 1.0 - np.exp(-rare_activity / 2.0)

        return np.clip(scores, 0.0, 1.0)

    def save(self, artifact_path: Path | str) -> None:
        """Serialize detector to JSON file."""
        if not self.is_fitted:
            raise ModelNotTrainedError("Cannot save unfitted FrequencyAnomalyDetector.")

        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "model_name": self.model_name,
            "algorithm": self.algorithm,
            "version": self.version,
            "threshold": self.threshold,
            "rare_template_threshold": self.rare_template_threshold,
            "rare_transition_penalty": self.rare_transition_penalty,
            "template_priors": self.template_priors,
            "transition_matrix": self.transition_matrix,
            "total_training_events": self.total_training_events,
            "training_metadata": self.training_metadata,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved FrequencyAnomalyDetector to %s", path)

    @classmethod
    def load(cls, artifact_path: Path | str) -> "FrequencyAnomalyDetector":
        """Load detector from JSON file."""
        path = Path(artifact_path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        detector = cls(
            rare_template_threshold=data.get("rare_template_threshold", 0.01),
            rare_transition_penalty=data.get("rare_transition_penalty", 0.8),
            version=data.get("version", "v1.0"),
        )
        detector.threshold = data.get("threshold", 0.5)
        detector.template_priors = data.get("template_priors", {})
        detector.transition_matrix = data.get("transition_matrix", {})
        detector.total_training_events = data.get("total_training_events", 0)
        detector.training_metadata = data.get("training_metadata", {})
        detector.is_fitted = True
        return detector

