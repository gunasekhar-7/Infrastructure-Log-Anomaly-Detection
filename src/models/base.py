"""Abstract Base Interface for All Anomaly Detection Models."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any
import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)

from config.logging import get_logger
from src.exceptions import ModelNotTrainedError

logger = get_logger("model_base")


class BaseAnomalyDetector(ABC):
    """Abstract base class establishing the contract for all anomaly detection algorithms."""

    def __init__(
        self,
        model_name: str,
        algorithm: str,
        version: str = "v1.0",
        threshold: float = 0.5,
    ) -> None:
        self.model_name = model_name
        self.algorithm = algorithm
        self.version = version
        self.threshold = threshold
        self.is_fitted = False
        self.hyperparameters: dict[str, Any] = {}
        self.training_metadata: dict[str, Any] = {}

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray | None = None) -> "BaseAnomalyDetector":
        """Fit the detector on normal (or semi-supervised) baseline feature vectors."""
        pass

    @abstractmethod
    def score(self, X: np.ndarray) -> np.ndarray:
        """Calculate continuous anomaly scores normalized to the [0.0, 1.0] interval.

        Higher scores indicate greater deviation from normal behavior.
        """
        pass

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Classify input samples as Normal (0) or Anomaly (1) based on calibrated threshold."""
        if not self.is_fitted:
            raise ModelNotTrainedError(f"Model {self.model_name} must be fitted before predict.")

        scores = self.score(X)
        return (scores >= self.threshold).astype(int)

    def calibrate_threshold(
        self,
        val_scores: np.ndarray,
        val_labels: np.ndarray | None = None,
        target_fpr: float = 0.05,
        percentile: float = 95.0,
    ) -> float:
        """Calibrate the decision threshold using a validation set.

        If ground-truth labels are available, selects threshold maximizing F1 score.
        Otherwise, uses the target upper percentile of normal validation scores.
        """
        if len(val_scores) == 0:
            return self.threshold

        if val_labels is not None and len(np.unique(val_labels)) > 1:
            # Optimize F1 score over candidate thresholds
            precisions, recalls, thresholds = precision_recall_curve(val_labels, val_scores)
            f1_scores = np.zeros_like(thresholds)
            for i, t in enumerate(thresholds):
                p = precisions[i]
                r = recalls[i]
                f1_scores[i] = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0

            best_idx = int(np.argmax(f1_scores))
            calibrated = float(thresholds[best_idx])
            logger.info(
                "Calibrated threshold for %s using F1 optimization: %.4f (Max Val F1: %.4f)",
                self.model_name,
                calibrated,
                f1_scores[best_idx],
            )
        else:
            # Unsupervised percentile-based threshold calibration
            calibrated = float(np.percentile(val_scores, percentile))
            logger.info(
                "Calibrated threshold for %s using %dth percentile: %.4f",
                self.model_name,
                int(percentile),
                calibrated,
            )

        self.threshold = calibrated
        return self.threshold

    @abstractmethod
    def save(self, artifact_path: Path | str) -> None:
        """Serialize model weights and metadata to disk."""
        pass

    @classmethod
    @abstractmethod
    def load(cls, artifact_path: Path | str) -> "BaseAnomalyDetector":
        """Load serialized model from disk."""
        pass

    def evaluate(
        self,
        X_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict[str, Any]:
        """Compute comprehensive evaluation metrics against ground-truth labels."""
        if not self.is_fitted:
            raise ModelNotTrainedError(f"Model {self.model_name} is not fitted.")

        scores = self.score(X_test)
        preds = (scores >= self.threshold).astype(int)
        y_int = y_test.astype(int)

        precision = float(precision_score(y_int, preds, zero_division=0))
        recall = float(recall_score(y_int, preds, zero_division=0))
        f1 = float(f1_score(y_int, preds, zero_division=0))
        acc = float(accuracy_score(y_int, preds))

        # Confusion Matrix [TN, FP, FN, TP]
        cm = confusion_matrix(y_int, preds, labels=[0, 1])
        tn, fp, fn, tp = int(cm[0, 0]), int(cm[0, 1]), int(cm[1, 0]), int(cm[1, 1])

        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

        try:
            auc = float(roc_auc_score(y_int, scores))
        except ValueError:
            auc = 0.5

        return {
            "model_name": self.model_name,
            "algorithm": self.algorithm,
            "threshold": round(self.threshold, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "accuracy": round(acc, 4),
            "roc_auc": round(auc, 4),
            "fpr": round(fpr, 4),
            "fnr": round(fnr, 4),
            "confusion_matrix": {
                "tn": tn,
                "fp": fp,
                "fn": fn,
                "tp": tp,
            },
            "score_mean": round(float(np.mean(scores)), 4),
            "score_std": round(float(np.std(scores)), 4),
            "score_max": round(float(np.max(scores)), 4),
        }

