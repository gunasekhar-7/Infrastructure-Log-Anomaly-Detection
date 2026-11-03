"""Statistical Anomaly Detector using Modified Z-Score and Robust Quartiles."""

import json
from pathlib import Path

import numpy as np

from config.logging import get_logger
from src.exceptions import ModelNotTrainedError
from src.models.base import BaseAnomalyDetector

logger = get_logger("statistical_detector")


class StatisticalDetector(BaseAnomalyDetector):
    """Detects statistical outliers using Modified Z-scores and Median Absolute Deviation (MAD).

    Robust against non-Gaussian distributions and extreme outliers in baseline telemetry.
    """

    def __init__(
        self,
        z_threshold: float = 3.5,
        version: str = "v1.0",
        epsilon: float = 1e-6,
    ) -> None:
        super().__init__(
            model_name="StatisticalOutlierDetector",
            algorithm="STATISTICAL_MODIFIED_Z",
            version=version,
            threshold=0.5,  # Continuous normalized score threshold
        )
        self.z_threshold = z_threshold
        self.epsilon = epsilon
        self.medians: np.ndarray | None = None
        self.mads: np.ndarray | None = None
        self.q25: np.ndarray | None = None
        self.q75: np.ndarray | None = None
        self.iqr: np.ndarray | None = None

        self.hyperparameters = {
            "z_threshold": z_threshold,
            "epsilon": epsilon,
        }

    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> "StatisticalDetector":
        """Fit median and dispersion parameters on baseline training data."""
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        self.medians = np.median(X, axis=0)
        abs_deviations = np.abs(X - self.medians)
        self.mads = np.median(abs_deviations, axis=0)
        # Ensure mads have at least epsilon to prevent division by zero
        self.mads = np.maximum(self.mads, self.epsilon)

        self.q25 = np.percentile(X, 25, axis=0)
        self.q75 = np.percentile(X, 75, axis=0)
        self.iqr = np.maximum(self.q75 - self.q25, self.epsilon)

        self.is_fitted = True
        self.training_metadata = {
            "n_samples": int(X.shape[0]),
            "n_features": int(X.shape[1]),
        }
        logger.info(
            "Fitted StatisticalDetector on %d samples across %d features.",
            X.shape[0],
            X.shape[1],
        )
        return self

    def compute_modified_z(self, X: np.ndarray) -> np.ndarray:
        """Compute Modified Z-scores: 0.6745 * |X - medians| / MAD."""
        if not self.is_fitted or self.medians is None or self.mads is None:
            raise ModelNotTrainedError("StatisticalDetector is not fitted.")

        if X.ndim == 1:
            X = X.reshape(-1, 1)

        diff = np.abs(X - self.medians)
        mod_z = 0.6745 * diff / self.mads
        return mod_z

    def score(self, X: np.ndarray) -> np.ndarray:
        """Compute normalized anomaly score [0.0, 1.0] from maximum Modified Z-score."""
        mod_z = self.compute_modified_z(X)
        # Maximum deviation across all monitored dimensions
        max_z = np.max(mod_z, axis=1)

        # Non-linear mapping: 1.0 - exp(-max_z / z_threshold) -> bounds naturally into [0, 1]
        scores = 1.0 - np.exp(-max_z / self.z_threshold)
        return np.clip(scores, 0.0, 1.0)

    def save(self, artifact_path: Path | str) -> None:
        """Serialize detector state to JSON file."""
        if not self.is_fitted:
            raise ModelNotTrainedError("Cannot save unfitted StatisticalDetector.")

        path = Path(artifact_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "model_name": self.model_name,
            "algorithm": self.algorithm,
            "version": self.version,
            "threshold": self.threshold,
            "z_threshold": self.z_threshold,
            "epsilon": self.epsilon,
            "medians": self.medians.tolist() if self.medians is not None else [],
            "mads": self.mads.tolist() if self.mads is not None else [],
            "q25": self.q25.tolist() if self.q25 is not None else [],
            "q75": self.q75.tolist() if self.q75 is not None else [],
            "iqr": self.iqr.tolist() if self.iqr is not None else [],
            "training_metadata": self.training_metadata,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved StatisticalDetector to %s", path)

    @classmethod
    def load(cls, artifact_path: Path | str) -> "StatisticalDetector":
        """Load detector from JSON file."""
        path = Path(artifact_path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        detector = cls(
            z_threshold=data.get("z_threshold", 3.5),
            version=data.get("version", "v1.0"),
            epsilon=data.get("epsilon", 1e-6),
        )
        detector.threshold = data.get("threshold", 0.5)
        detector.medians = np.array(data["medians"], dtype=np.float64)
        detector.mads = np.array(data["mads"], dtype=np.float64)
        detector.q25 = np.array(data["q25"], dtype=np.float64)
        detector.q75 = np.array(data["q75"], dtype=np.float64)
        detector.iqr = np.array(data["iqr"], dtype=np.float64)
        detector.is_fitted = True
        detector.training_metadata = data.get("training_metadata", {})
        return detector

