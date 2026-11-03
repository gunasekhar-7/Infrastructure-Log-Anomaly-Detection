"""Standardized Evaluation Harness for Anomaly Detection Models."""

from typing import Any
import numpy as np
import pandas as pd

from config.logging import get_logger
from src.models.base import BaseAnomalyDetector

logger = get_logger("model_evaluator")


def evaluate_detector_on_splits(
    detector: BaseAnomalyDetector,
    X_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    calibrate_threshold: bool = True,
) -> dict[str, Any]:
    """Train, calibrate, and evaluate an anomaly detector on held-out benchmark splits."""
    logger.info("Evaluating model %s on benchmark splits...", detector.model_name)

    # 1. Fit detector on training split (normal baseline)
    detector.fit(X_train)

    # 2. Calibrate threshold on validation split
    val_scores = detector.score(X_val)
    if calibrate_threshold:
        detector.calibrate_threshold(val_scores, val_labels=y_val)

    # 3. Evaluate on held-out test partition
    test_metrics = detector.evaluate(X_test, y_test)

    # Add dataset metadata
    test_metrics["train_samples"] = int(X_train.shape[0])
    test_metrics["val_samples"] = int(X_val.shape[0])
    test_metrics["test_samples"] = int(X_test.shape[0])
    test_metrics["test_positives"] = int(np.sum(y_test))
    test_metrics["test_negatives"] = int(len(y_test) - np.sum(y_test))

    logger.info(
        "Evaluation results for %s: Precision=%.4f, Recall=%.4f, F1=%.4f, ROC-AUC=%.4f (Threshold=%.4f)",
        detector.model_name,
        test_metrics["precision"],
        test_metrics["recall"],
        test_metrics["f1"],
        test_metrics["roc_auc"],
        test_metrics["threshold"],
    )

    return test_metrics


def compare_models(
    models: list[BaseAnomalyDetector],
    X_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> pd.DataFrame:
    """Run comparative benchmark across multiple anomaly detection models."""
    results = []
    for model in models:
        metrics = evaluate_detector_on_splits(
            detector=model,
            X_train=X_train,
            X_val=X_val,
            y_val=y_val,
            X_test=X_test,
            y_test=y_test,
        )
        results.append(metrics)

    df = pd.DataFrame(results)
    return df

