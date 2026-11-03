"""Sequential Template Windowing and Tokenization for DeepLog Models."""

from typing import Any
import numpy as np
from src.features.models import SequenceSample
from src.parsing.models import ParsedLogEvent


class SequenceFeatureExtractor:
    """Generate sequential sliding-window training samples for next-token prediction models."""

    def __init__(
        self,
        vocabulary: dict[str, int],
        window_size: int = 20,
        step_size: int = 1,
        pad_token: str = "<PAD>",
        unk_token: str = "<UNK>",
    ) -> None:
        self.vocabulary = vocabulary
        self.window_size = window_size
        self.step_size = step_size
        self.pad_token = pad_token
        self.unk_token = unk_token

        self.pad_idx = vocabulary.get(pad_token, 0)
        self.unk_idx = vocabulary.get(unk_token, 1)

    def template_to_index(self, template_id: str) -> int:
        """Map canonical template string ID to integer token index."""
        return self.vocabulary.get(template_id, self.unk_idx)

    def extract_from_event_stream(
        self,
        events: list[ParsedLogEvent],
    ) -> list[SequenceSample]:
        """Extract sliding sequence samples from a continuous chronological event stream (e.g. BGL)."""
        if len(events) <= self.window_size:
            return []

        templates = [e.template_id for e in events]
        indices = [self.template_to_index(t) for t in templates]
        anomalies = [
            e.attributes.get("is_anomaly", False) or e.severity.value in ("ERROR", "FATAL")
            for e in events
        ]

        samples: list[SequenceSample] = []
        n_events = len(events)

        for i in range(0, n_events - self.window_size, self.step_size):
            seq_templates = templates[i : i + self.window_size]
            seq_indices = indices[i : i + self.window_size]
            next_t = templates[i + self.window_size]
            next_idx = indices[i + self.window_size]

            is_anom = any(anomalies[i : i + self.window_size + 1])

            sample = SequenceSample(
                sample_id=f"seq_{i}",
                sequence_templates=seq_templates,
                sequence_indices=seq_indices,
                next_template=next_t,
                next_index=next_idx,
                is_anomaly=is_anom,
                label="Anomaly" if is_anom else "Normal",
            )
            samples.append(sample)

        return samples

    def extract_from_blocks(
        self,
        events: list[ParsedLogEvent],
        block_key: str = "block_id",
    ) -> list[SequenceSample]:
        """Extract sequence samples grouped by discrete block ID (e.g. HDFS)."""
        blocks: dict[str, list[ParsedLogEvent]] = {}
        for ev in events:
            b_id = ev.attributes.get(block_key, "unknown")
            blocks.setdefault(b_id, []).append(ev)

        samples: list[SequenceSample] = []

        for b_id, b_events in blocks.items():
            templates = [e.template_id for e in b_events]
            indices = [self.template_to_index(t) for t in templates]
            is_anom = any(
                e.attributes.get("is_anomaly", False) or e.severity.value in ("ERROR", "FATAL")
                for e in b_events
            )
            label = "Anomaly" if is_anom else "Normal"

            n = len(indices)
            if n == 0:
                continue

            # If sequence is shorter than window_size, pad with <PAD> tokens
            if n <= self.window_size:
                pad_len = self.window_size - n + 1
                padded_templates = [self.pad_token] * pad_len + templates
                padded_indices = [self.pad_idx] * pad_len + indices

                seq_tmpl = padded_templates[:-1]
                seq_idx = padded_indices[:-1]
                next_tmpl = padded_templates[-1]
                next_id = padded_indices[-1]

                sample = SequenceSample(
                    sample_id=f"block_{b_id}_0",
                    sequence_templates=seq_tmpl,
                    sequence_indices=seq_idx,
                    next_template=next_tmpl,
                    next_index=next_id,
                    block_id=b_id,
                    is_anomaly=is_anom,
                    label=label,
                )
                samples.append(sample)
            else:
                for i in range(0, n - self.window_size, self.step_size):
                    seq_tmpl = templates[i : i + self.window_size]
                    seq_idx = indices[i : i + self.window_size]
                    next_tmpl = templates[i + self.window_size]
                    next_id = indices[i + self.window_size]

                    sample = SequenceSample(
                        sample_id=f"block_{b_id}_{i}",
                        sequence_templates=seq_tmpl,
                        sequence_indices=seq_idx,
                        next_template=next_tmpl,
                        next_index=next_id,
                        block_id=b_id,
                        is_anomaly=is_anom,
                        label=label,
                    )
                    samples.append(sample)

        return samples

    def to_tensors(self, samples: list[SequenceSample]) -> tuple[np.ndarray, np.ndarray]:
        """Convert sequence samples into (X, y) numpy arrays for PyTorch Dataset ingestion."""
        if not samples:
            return np.empty((0, self.window_size), dtype=np.int64), np.empty((0,), dtype=np.int64)

        X = np.array([s.sequence_indices for s in samples], dtype=np.int64)
        y = np.array([s.next_index for s in samples], dtype=np.int64)
        return X, y

