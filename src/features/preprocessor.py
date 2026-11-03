"""End-to-End Feature Pipeline with Scaling, Versioning, and Leakage Guards."""

import json
from pathlib import Path
from typing import Any
import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from config.logging import get_logger
from src.exceptions import FeatureExtractionError
from src.features.frequency import FrequencyFeatureExtractor
from src.features.models import FeatureDataset, WindowFeatureRecord
from src.features.sequence import SequenceFeatureExtractor
from src.parsing.models import ParsedLogEvent

logger = get_logger("feature_pipeline")

NUMERICAL_FEATURE_COLS = [
    "event_count",
    "error_count",
    "warn_count",
    "info_count",
    "error_rate",
    "template_entropy",
    "inter_event_time_mean_ms",
    "inter_event_time_std_ms",
    "unique_templates_count",
    "unique_services_count",
    "unique_hosts_count",
]


class FeaturePipeline:
    """Manages feature extraction, tabular normalization, serialization, and versioning."""

    def __init__(
        self,
        vocabulary: dict[str, int] | None = None,
        window_size_sec: int = 60,
        step_size_sec: int = 10,
        sequence_window_size: int = 20,
        version: str = "v1.0",
    ) -> None:
        self.version = version
        self.vocabulary = vocabulary or {"<PAD>": 0, "<UNK>": 1}
        self.known_templates = [
            t for t in self.vocabulary.keys() if t not in ("<PAD>", "<UNK>")
        ]

        self.freq_extractor = FrequencyFeatureExtractor(
            window_size_sec=window_size_sec,
            step_size_sec=step_size_sec,
            known_templates=self.known_templates,
        )
        self.seq_extractor = SequenceFeatureExtractor(
            vocabulary=self.vocabulary,
            window_size=sequence_window_size,
        )

        self.scaler = StandardScaler()
        self.is_fitted = False
        self.feature_columns: list[str] = []

    def fit_transform_tabular(
        self,
        events: list[ParsedLogEvent],
        by_blocks: bool = False,
    ) -> tuple[np.ndarray, pd.DataFrame, list[WindowFeatureRecord]]:
        """Extract frequency features from training split and fit the numerical scaler."""
        logger.info("Extracting and fitting tabular features on %d training events...", len(events))
        if by_blocks:
            df, records = self.freq_extractor.extract_from_blocks(events)
        else:
            df, records = self.freq_extractor.extract_from_events(events)

        if df.empty:
            raise FeatureExtractionError("No window features could be extracted from provided events.")

        # Identify all feature columns (numerical aggregates + template counts)
        tmpl_cols = [c for c in df.columns if c.startswith("tmpl_")]
        self.feature_columns = NUMERICAL_FEATURE_COLS + tmpl_cols

        # Ensure all columns exist in df
        for col in self.feature_columns:
            if col not in df.columns:
                df[col] = 0.0

        raw_X = df[self.feature_columns].to_numpy(dtype=np.float32)

        # Handle any possible NaN / Inf
        raw_X = np.nan_to_num(raw_X, nan=0.0, posinf=1.0, neginf=-1.0)

        # Fit and transform training data
        scaled_X = self.scaler.fit_transform(raw_X)
        self.is_fitted = True

        logger.info(
            "Fitted FeaturePipeline %s on %d windows with %d features.",
            self.version,
            len(df),
            len(self.feature_columns),
        )

        return scaled_X, df, records

    def transform_tabular(
        self,
        events: list[ParsedLogEvent],
        by_blocks: bool = False,
    ) -> tuple[np.ndarray, pd.DataFrame, list[WindowFeatureRecord]]:
        """Transform validation or test events using pre-fitted scaler parameters (zero leakage)."""
        if not self.is_fitted:
            raise FeatureExtractionError("FeaturePipeline must be fitted on training data before transform.")

        if by_blocks:
            df, records = self.freq_extractor.extract_from_blocks(events)
        else:
            df, records = self.freq_extractor.extract_from_events(events)

        if df.empty:
            return np.empty((0, len(self.feature_columns)), dtype=np.float32), df, []

        for col in self.feature_columns:
            if col not in df.columns:
                df[col] = 0.0

        raw_X = df[self.feature_columns].to_numpy(dtype=np.float32)
        raw_X = np.nan_to_num(raw_X, nan=0.0, posinf=1.0, neginf=-1.0)
        scaled_X = self.scaler.transform(raw_X)

        return scaled_X, df, records

    def extract_sequence_tensors(
        self,
        events: list[ParsedLogEvent],
        by_blocks: bool = False,
    ) -> tuple[np.ndarray, np.ndarray, list[Any]]:
        """Extract (X_seq, y_seq) numpy arrays and sample metadata."""
        if by_blocks:
            samples = self.seq_extractor.extract_from_blocks(events)
        else:
            samples = self.seq_extractor.extract_from_event_stream(events)

        X_seq, y_seq = self.seq_extractor.to_tensors(samples)
        return X_seq, y_seq, samples

    def save(self, artifact_dir: Path | str) -> None:
        """Persist fitted scaler, vocabulary, feature columns, and version metadata."""
        out_dir = Path(artifact_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        joblib.dump(self.scaler, out_dir / "scaler.joblib")
        with open(out_dir / "vocabulary.json", "w", encoding="utf-8") as f:
            json.dump(self.vocabulary, f, indent=2)

        meta = {
            "version": self.version,
            "feature_columns": self.feature_columns,
            "is_fitted": self.is_fitted,
            "window_size_sec": self.freq_extractor.window_size_sec,
            "step_size_sec": self.freq_extractor.step_size_sec,
            "sequence_window_size": self.seq_extractor.window_size,
        }
        with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        logger.info("Saved FeaturePipeline %s to %s", self.version, out_dir)

    @classmethod
    def load(cls, artifact_dir: Path | str) -> "FeaturePipeline":
        """Load fitted pipeline instance from serialized artifacts."""
        in_dir = Path(artifact_dir)
        with open(in_dir / "vocabulary.json", "r", encoding="utf-8") as f:
            vocab = json.load(f)

        with open(in_dir / "metadata.json", "r", encoding="utf-8") as f:
            meta = json.load(f)

        pipeline = cls(
            vocabulary=vocab,
            window_size_sec=meta["window_size_sec"],
            step_size_sec=meta["step_size_sec"],
            sequence_window_size=meta["sequence_window_size"],
            version=meta["version"],
        )
        pipeline.scaler = joblib.load(in_dir / "scaler.joblib")
        pipeline.feature_columns = meta["feature_columns"]
        pipeline.is_fitted = meta["is_fitted"]

        logger.info("Loaded FeaturePipeline %s from %s", pipeline.version, in_dir)
        return pipeline
