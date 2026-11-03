"""Event Frequency, Volumetric, and Temporal Feature Extraction."""

from collections import Counter
from datetime import timedelta
import math
from typing import Any
import numpy as np
import pandas as pd

from src.ingestion.models import LogSeverity
from src.parsing.models import ParsedLogEvent
from src.features.models import WindowFeatureRecord


def calculate_entropy(counts: list[int] | Counter) -> float:
    """Calculate Shannon entropy H(X) = -sum(p * log2(p)) over a distribution."""
    total = sum(counts.values()) if isinstance(counts, Counter) else sum(counts)
    if total <= 1:
        return 0.0

    entropy = 0.0
    for count in (counts.values() if isinstance(counts, Counter) else counts):
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return float(entropy)


class FrequencyFeatureExtractor:
    """Extract tabular frequency and temporal features from parsed log event streams."""

    def __init__(
        self,
        window_size_sec: int = 60,
        step_size_sec: int = 10,
        known_templates: list[str] | None = None,
    ) -> None:
        self.window_size_sec = window_size_sec
        self.step_size_sec = step_size_sec
        self.known_templates = known_templates or []
        self._template_to_idx = {t: i for i, t in enumerate(self.known_templates)}

    def extract_from_events(
        self,
        events: list[ParsedLogEvent],
        window_id_prefix: str = "win",
    ) -> tuple[pd.DataFrame, list[WindowFeatureRecord]]:
        """Slice chronological event sequence into sliding windows and extract statistical features."""
        if not events:
            return pd.DataFrame(), []

        # Sort events by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        start_bound = sorted_events[0].timestamp
        end_bound = sorted_events[-1].timestamp

        window_duration = timedelta(seconds=self.window_size_sec)
        step_duration = timedelta(seconds=self.step_size_sec)

        records: list[WindowFeatureRecord] = []
        cur_start = start_bound
        win_idx = 0

        # Two-pointer or linear scan for window events
        event_idx = 0
        total_events = len(sorted_events)

        while cur_start <= end_bound:
            cur_end = cur_start + window_duration
            # Gather events in window [cur_start, cur_end)
            win_events = [e for e in sorted_events if cur_start <= e.timestamp < cur_end]

            if win_events:
                rec = self._compute_window_features(
                    window_id=f"{window_id_prefix}_{win_idx}",
                    start_time=cur_start,
                    end_time=cur_end,
                    events=win_events,
                )
                records.append(rec)
                win_idx += 1

            cur_start += step_duration

        # If events span very short time (< step), ensure at least 1 window is produced
        if not records and sorted_events:
            rec = self._compute_window_features(
                window_id=f"{window_id_prefix}_0",
                start_time=sorted_events[0].timestamp,
                end_time=sorted_events[-1].timestamp + timedelta(seconds=1),
                events=sorted_events,
            )
            records.append(rec)

        df = self._records_to_dataframe(records)
        return df, records

    def extract_from_blocks(
        self,
        events: list[ParsedLogEvent],
        block_key: str = "block_id",
    ) -> tuple[pd.DataFrame, list[WindowFeatureRecord]]:
        """Extract features by grouping events by discrete block ID or session ID."""
        blocks: dict[str, list[ParsedLogEvent]] = {}
        for ev in events:
            b_id = ev.attributes.get(block_key, "unknown")
            blocks.setdefault(b_id, []).append(ev)

        records: list[WindowFeatureRecord] = []
        for b_id, b_events in blocks.items():
            b_events_sorted = sorted(b_events, key=lambda e: e.timestamp)
            start_ts = b_events_sorted[0].timestamp
            end_ts = b_events_sorted[-1].timestamp
            rec = self._compute_window_features(
                window_id=f"block_{b_id}",
                start_time=start_ts,
                end_time=end_ts,
                events=b_events_sorted,
            )
            records.append(rec)

        df = self._records_to_dataframe(records)
        return df, records

    def _compute_window_features(
        self,
        window_id: str,
        start_time: Any,
        end_time: Any,
        events: list[ParsedLogEvent],
    ) -> WindowFeatureRecord:
        """Calculate statistical aggregates for an isolated set of windowed events."""
        event_count = len(events)
        error_count = sum(1 for e in events if e.severity in (LogSeverity.ERROR, LogSeverity.FATAL))
        warn_count = sum(1 for e in events if e.severity == LogSeverity.WARN)
        info_count = sum(1 for e in events if e.severity == LogSeverity.INFO)
        error_rate = error_count / event_count if event_count > 0 else 0.0

        # Template distribution and entropy
        tmpl_counter = Counter(e.template_id for e in events)
        entropy = calculate_entropy(tmpl_counter)

        # Inter-event arrival deltas (in milliseconds)
        if event_count > 1:
            deltas = [
                (events[i].timestamp - events[i - 1].timestamp).total_seconds() * 1000.0
                for i in range(1, event_count)
            ]
            iet_mean = float(np.mean(deltas))
            iet_std = float(np.std(deltas))
        else:
            iet_mean = 0.0
            iet_std = 0.0

        unique_templates = len(tmpl_counter)
        unique_services = len(set(e.service for e in events))
        unique_hosts = len(set(e.host for e in events))

        # Check ground-truth anomaly status if present in attributes
        is_anomaly = any(
            e.attributes.get("is_anomaly", False) or e.severity in (LogSeverity.ERROR, LogSeverity.FATAL)
            for e in events
        )
        label = "Anomaly" if is_anomaly else "Normal"

        return WindowFeatureRecord(
            window_id=window_id,
            start_time=start_time,
            end_time=end_time,
            event_count=event_count,
            error_count=error_count,
            warn_count=warn_count,
            info_count=info_count,
            error_rate=round(error_rate, 4),
            template_entropy=round(entropy, 4),
            inter_event_time_mean_ms=round(iet_mean, 2),
            inter_event_time_std_ms=round(iet_std, 2),
            unique_templates_count=unique_templates,
            unique_services_count=unique_services,
            unique_hosts_count=unique_hosts,
            template_counts=dict(tmpl_counter),
            label=label,
            is_anomaly=is_anomaly,
        )

    def _records_to_dataframe(self, records: list[WindowFeatureRecord]) -> pd.DataFrame:
        """Convert list of WindowFeatureRecord into a structured pandas DataFrame."""
        if not records:
            return pd.DataFrame()

        rows = []
        for r in records:
            row = {
                "window_id": r.window_id,
                "start_time": r.start_time,
                "end_time": r.end_time,
                "event_count": r.event_count,
                "error_count": r.error_count,
                "warn_count": r.warn_count,
                "info_count": r.info_count,
                "error_rate": r.error_rate,
                "template_entropy": r.template_entropy,
                "inter_event_time_mean_ms": r.inter_event_time_mean_ms,
                "inter_event_time_std_ms": r.inter_event_time_std_ms,
                "unique_templates_count": r.unique_templates_count,
                "unique_services_count": r.unique_services_count,
                "unique_hosts_count": r.unique_hosts_count,
                "label": r.label,
                "is_anomaly": r.is_anomaly,
            }

            # Add template frequency columns for known templates
            for t_id in self.known_templates:
                row[f"tmpl_{t_id}"] = r.template_counts.get(t_id, 0)

            rows.append(row)

        return pd.DataFrame(rows)

