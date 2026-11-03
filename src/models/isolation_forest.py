"""Multivariate Isolation Forest Anomaly Detector."""

import json
from pathlib import Path
from typing import Any
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from config.logging import get_logger
from src.exceptions import ModelNotTrainedError
from src.models.base import BaseAnomalyDetector

logger = get_logger("isolation_forest_detector")


class IsolationForestDetector(BaseAnomalyDetector):
    """Unsupervised multivariate anomaly detector using recursive binary isolation trees."""

    def __init__(
        self,
        n_estimators: int = 100,
        contamination: float | str = 0.02,
        max_samples: str | int = "auto",
        random_state: int = 42,
        version: str = "v1.0",
    ) -> None:
        super().__init__(
            model_name="IsolationForestDetector",
            algorithm="ISOLATION_FOREST",
            version=version,
            threshold=0.5,
        )
        self.n_estimators = n_estimators
        self.contamination = contamination
        self.max_samples = max_samples
        self.random_state = random_state

        self.model = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            max_samples=max_samples,
            random_state=random_state,
            n_jobs=-1,
        )
        self.hyperparameters = {
            "n_estimators": n_estimators,
            "contamination": contamination,
            "max_samples": max_samples,
            "random_state": random_state,
        }
        self.score_offset_: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> "IsolationForestDetector":
        """Fit Isolation Forest forest on baseline training features."""
        logger.info(
            "Fitting IsolationForest (n_trees=%d, contamination=%s) on %d samples...",
            self.n_estimators,
            self.contamination,
            X.shape[0],
        )
        self.model.fit(X)
        self.score_offset_ = float(self.model.offset_)
        self.is_fitted = True
        self.training_metadata = {
            "n_samples": int(X.shape[0]),
            "n_features": int(X.shape[1]),
            "score_offset": self.score_offset_,
        }
        return self

    def score(self, X: np.ndarray) -> np.ndarray:
        """Compute normalized anomaly scores in [0.0, 1.0].

        Sklearn score_samples returns opposite of anomaly score (lower is more anomalous).
        We transform s(X) so higher values correspond directly to anomalous deviation.
        """
        if not self.is_fitted:
            raise ModelNotTrainedError("IsolationForestDetector is not fitted.")

        raw_scores = self.model.score_samples(X)  # typically in [-0.8, -0.3]
        # Normalize around offset_: points where raw_score < offset_ are anomalies
        # Normalized: 0.5 - (raw_scores - offset_) gives ~0.5 at decision boundary, >0.5 for anomalies
        normalized_scores = 0.5 - (raw_scores - self.score_offset_)
        return np.clip(normalized_scores, 0.0, 1.0)

    def save(self, artifact_path: Path | str) -> None:
        """Serialize trained model and configuration metadata."""
        if not self.is_fitted:
            raise ModelNotTrainedError("Cannot save unfitted IsolationForestDetector.")

        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save scikit-learn model using joblib
        model_file = path.with_suffix(".joblib")
        joblib.dump(self.model, model_file)

        # Save metadata and parameters
        meta_file = path.with_suffix(".json")
        meta = {
            "model_name": self.model_name,
            "algorithm": self.algorithm,
            "version": self.version,
            "threshold": self.threshold,
            "score_offset": self.score_offset_,
            "hyperparameters": self.hyperparameters,
            "training_metadata": self.training_metadata,
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        logger.info("Saved IsolationForestDetector to %s and %s", model_file, meta_file)

    @classmethod
    def load(cls, artifact_path: Path | str) -> "IsolationForestDetector":
        """Load trained model and metadata."""
        path = Path(artifact_path)
        meta_file = path.with_suffix(".json")
        model_file = path.with_suffix(".joblib")

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        params = meta.get("hyperparameters", {})
        detector = cls(
            n_estimators=params.get("n_estimators", 100),
            contamination=params.get("contamination", 0.02),
            max_samples=params.get("max_samples", "auto"),
            random_state=params.get("random_state", 42),
            version=meta.get("version", "v1.0"),
        )
        detector.threshold = meta.get("threshold", 0.5)
        detector.score_offset_ = meta.get("score_offset", 0.0)
        detector.model = joblib.load(model_file)
        detector.is_fitted = True
        detector.training_metadata = meta.get("training_metadata", {})
        return detector
