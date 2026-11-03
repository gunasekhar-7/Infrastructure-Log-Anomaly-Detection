"""Weighted Ensemble Anomaly Detector combining Tabular and Sequential Models."""

from pathlib import Path

import numpy as np

from config.logging import get_logger
from src.exceptions import ModelNotTrainedError
from src.models.base import BaseAnomalyDetector

logger = get_logger("anomaly_ensemble")


class AnomalyEnsembleDetector(BaseAnomalyDetector):
    """Ensemble combining Tabular (e.g. Isolation Forest) and Sequential (DeepLog) detectors."""

    def __init__(
        self,
        tabular_detector: BaseAnomalyDetector,
        sequential_detector: BaseAnomalyDetector,
        weight_tabular: float = 0.4,
        weight_sequential: float = 0.6,
        version: str = "v1.0",
    ) -> None:
        super().__init__(
            model_name="EnsembleHybridDetector",
            algorithm="ENSEMBLE_TABULAR_AND_DEEPLOG",
            version=version,
            threshold=0.5,
        )
        self.tabular_detector = tabular_detector
        self.sequential_detector = sequential_detector
        self.weight_tabular = weight_tabular
        self.weight_sequential = weight_sequential

        # Normalize weights to sum to 1.0
        total_w = weight_tabular + weight_sequential
        self.w_tab = weight_tabular / total_w
        self.w_seq = weight_sequential / total_w

    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> "AnomalyEnsembleDetector":
        """Fit tabular model on X; sequential model is assumed pre-fitted or fitted via fit_hybrid."""
        self.tabular_detector.fit(X, y)
        self.is_fitted = True
        return self

    def fit_hybrid(
        self,
        X_tabular: np.ndarray,
        X_seq: np.ndarray,
        y_seq: np.ndarray,
    ) -> "AnomalyEnsembleDetector":
        """Fit both constituent detectors on respective feature matrices."""
        self.tabular_detector.fit(X_tabular)
        if hasattr(self.sequential_detector, "fit_sequences"):
            self.sequential_detector.fit_sequences(X_seq, y_seq)
        else:
            self.sequential_detector.fit(X_seq)
        self.is_fitted = True
        return self

    def score_hybrid(
        self,
        X_tabular: np.ndarray,
        X_seq: np.ndarray,
        y_seq: np.ndarray,
    ) -> np.ndarray:
        """Compute combined weighted score across tabular and sequential representations."""
        if not self.is_fitted:
            raise ModelNotTrainedError("AnomalyEnsembleDetector is not fitted.")

        s_tab = self.tabular_detector.score(X_tabular)
        if hasattr(self.sequential_detector, "score_sequences"):
            s_seq = self.sequential_detector.score_sequences(X_seq, y_seq)
        else:
            s_seq = self.sequential_detector.score(X_seq)

        # Align lengths if needed
        min_len = min(len(s_tab), len(s_seq))
        s_tab_aligned = s_tab[:min_len]
        s_seq_aligned = s_seq[:min_len]

        ensemble_scores = (self.w_tab * s_tab_aligned) + (self.w_seq * s_seq_aligned)
        return np.clip(ensemble_scores, 0.0, 1.0)

    def score(self, X: np.ndarray) -> np.ndarray:
        """Fallback score method using tabular detector."""
        return self.tabular_detector.score(X)

    def save(self, artifact_path: Path | str) -> None:
        """Save constituent detectors."""
        path = Path(artifact_path)
        path.mkdir(parents=True, exist_ok=True)
        self.tabular_detector.save(path / "tabular_model")
        self.sequential_detector.save(path / "sequential_model")

    @classmethod
    def load(cls, artifact_path: Path | str) -> "AnomalyEnsembleDetector":
        """Load constituent models from disk."""
        raise NotImplementedError("Use constituent model load functions and initialize Ensemble.")

