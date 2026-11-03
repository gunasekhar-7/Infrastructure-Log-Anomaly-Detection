"""Data models and schemas for feature extraction and windowing."""

from datetime import datetime
from typing import Any
import numpy as np
from pydantic import BaseModel, Field


class WindowFeatureRecord(BaseModel):
    """Extracted statistical and frequency feature record for a single temporal window."""

    window_id: str
    start_time: datetime
    end_time: datetime
    event_count: int
    error_count: int
    warn_count: int
    info_count: int
    error_rate: float
    template_entropy: float
    inter_event_time_mean_ms: float
    inter_event_time_std_ms: float
    unique_templates_count: int
    unique_services_count: int
    unique_hosts_count: int
    template_counts: dict[str, int] = Field(default_factory=dict)
    label: str = "Normal"
    is_anomaly: bool = False


class SequenceSample(BaseModel):
    """Sequential template sequence sample for DeepLog-style next-token prediction."""

    sample_id: str
    sequence_templates: list[str]  # e.g. ["E1", "E2", "E3", ...]
    sequence_indices: list[int]    # token indices e.g. [2, 3, 4, ...]
    next_template: str             # target next template e.g. "E4"
    next_index: int                # target next token index e.g. 5
    block_id: str | None = None
    label: str = "Normal"
    is_anomaly: bool = False


class FeatureDataset(BaseModel):
    """Container for tabular feature matrix and sequential tensors."""

    feature_names: list[str]
    total_samples: int
    is_normalized: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True
