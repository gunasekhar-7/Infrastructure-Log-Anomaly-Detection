"""Dataset Engineering, Parsing, Normalization, and Leakage-Free Splitting for HDFS and BGL."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from config.logging import get_logger

logger = get_logger("dataset_engineering")

# HDFS Log Format Regex: Date Time PID Level Component: Message
HDFS_REGEX = re.compile(
    r"^(?P<date>\d{6})\s+(?P<time>\d{6})\s+(?P<pid>\d+)\s+(?P<level>\w+)\s+(?P<component>[^:]+):\s+(?P<message>.*)$"
)
BLOCK_ID_REGEX = re.compile(r"(blk_-?\d+)")

# BGL Log Format Regex: Label Epoch Date Node Timestamp Node Subsys Component Level Message
BGL_REGEX = re.compile(
    r"^(?P<label>\S+)\s+(?P<epoch>\d+)\s+(?P<date>\S+)\s+(?P<node>\S+)\s+(?P<timestamp>\S+)\s+(?P<node2>\S+)\s+(?P<subsys>\S+)\s+(?P<component>\S+)\s+(?P<level>\w+)\s+(?P<message>.*)$"
)


def parse_hdfs_line(line_idx: int, line: str) -> dict[str, Any] | None:
    """Parse a single raw HDFS log line into structured fields."""
    match = HDFS_REGEX.match(line.strip())
    if not match:
        # Fallback extraction for block ID if non-standard line
        block_match = BLOCK_ID_REGEX.search(line)
        block_id = block_match.group(1) if block_match else "unknown"
        return {
            "line_idx": line_idx,
            "timestamp": None,
            "level": "INFO",
            "component": "unknown",
            "message": line.strip(),
            "block_id": block_id,
            "is_valid": False,
        }

    data = match.groupdict()
    # Format date: YYMMDD HHMMSS -> ISO timestamp
    raw_date = data["date"]
    raw_time = data["time"]
    try:
        dt = datetime.strptime(f"20{raw_date} {raw_time}", "%Y%m%d %H%M%S").replace(tzinfo=timezone.utc)
        iso_ts = dt.isoformat()
    except ValueError:
        iso_ts = None

    # Extract block ID
    block_match = BLOCK_ID_REGEX.search(data["message"])
    block_id = block_match.group(1) if block_match else "unknown"

    return {
        "line_idx": line_idx,
        "timestamp": iso_ts,
        "level": data["level"].upper(),
        "component": data["component"].strip(),
        "message": data["message"].strip(),
        "block_id": block_id,
        "is_valid": True,
    }


def parse_bgl_line(line_idx: int, line: str) -> dict[str, Any] | None:
    """Parse a single raw BGL log line into structured fields."""
    match = BGL_REGEX.match(line.strip())
    if not match:
        return {
            "line_idx": line_idx,
            "timestamp": None,
            "level": "INFO",
            "node": "unknown",
            "component": "unknown",
            "message": line.strip(),
            "label": "Normal",
            "is_valid": False,
        }

    data = match.groupdict()
    raw_label = data["label"]
    is_anomaly = raw_label != "-"
    label = "Anomaly" if is_anomaly else "Normal"

    # Timestamp from epoch
    try:
        epoch = int(data["epoch"])
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        iso_ts = dt.isoformat()
    except (ValueError, OSError):
        iso_ts = None

    return {
        "line_idx": line_idx,
        "timestamp": iso_ts,
        "level": data["level"].upper(),
        "node": data["node"],
        "component": data["component"],
        "subsys": data["subsys"],
        "message": data["message"].strip(),
        "raw_label": raw_label,
        "label": label,
        "is_valid": True,
    }


class BenchmarkDataPipeline:
    """End-to-end data engineering pipeline for benchmark dataset loading, cleaning, and splitting."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or Path("data")
        self.raw_hdfs = self.data_dir / "raw" / "hdfs" / "HDFS_2k.log"
        self.raw_hdfs_labels = self.data_dir / "raw" / "hdfs" / "anomaly_label.csv"
        self.raw_bgl = self.data_dir / "raw" / "bgl" / "BGL_2k.log"
        self.processed_dir = self.data_dir / "processed"
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def load_and_process_hdfs(self) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Parse raw HDFS logs, merge with ground-truth block labels, and generate leakage-free splits."""
        logger.info("Processing HDFS dataset from %s ...", self.raw_hdfs)
        if not self.raw_hdfs.exists():
            raise FileNotFoundError(f"HDFS raw log not found at {self.raw_hdfs}")

        records: list[dict[str, Any]] = []
        with open(self.raw_hdfs, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                parsed = parse_hdfs_line(idx, line)
                if parsed:
                    records.append(parsed)

        df = pd.DataFrame(records)
        total_records = len(df)
        valid_records = int(df["is_valid"].sum())
        logger.info("Parsed %d HDFS records (%d valid)", total_records, valid_records)

        # Merge with anomaly labels
        label_map: dict[str, str] = {}
        if self.raw_hdfs_labels.exists():
            logger.info("Loading ground truth anomaly labels from %s ...", self.raw_hdfs_labels)
            labels_df = pd.read_csv(self.raw_hdfs_labels)
            # anomaly_label.csv has columns: BlockId, Label (Normal / Anomaly)
            label_map = dict(zip(labels_df["BlockId"], labels_df["Label"]))

        # Map block labels (default to Normal if not found in label_map)
        df["label"] = df["block_id"].map(lambda b: label_map.get(b, "Normal"))
        df["is_anomaly"] = df["label"] == "Anomaly"

        # Unique blocks
        unique_blocks = df["block_id"].unique()
        block_labels = df.groupby("block_id")["label"].first()
        normal_blocks = block_labels[block_labels == "Normal"].index.to_numpy()
        anomaly_blocks = block_labels[block_labels == "Anomaly"].index.to_numpy()

        # Leakage-Free Splitting: Split strictly by Block ID
        rng = np.random.default_rng(seed=42)
        rng.shuffle(normal_blocks)
        rng.shuffle(anomaly_blocks)

        # 80% train (normal blocks only), 10% val, 10% test
        n_train = int(len(normal_blocks) * 0.8)
        n_val = int(len(normal_blocks) * 0.1)

        train_blocks = set(normal_blocks[:n_train])
        val_normal = set(normal_blocks[n_train : n_train + n_val])
        test_normal = set(normal_blocks[n_train + n_val :])

        # Split anomalies 50/50 between val and test
        n_anom_val = len(anomaly_blocks) // 2
        val_anom = set(anomaly_blocks[:n_anom_val])
        test_anom = set(anomaly_blocks[n_anom_val:])

        val_blocks = val_normal | val_anom
        test_blocks = test_normal | test_anom

        # Assign partition tags
        def assign_split(block_id: str) -> str:
            if block_id in train_blocks:
                return "train"
            elif block_id in val_blocks:
                return "val"
            elif block_id in test_blocks:
                return "test"
            return "train"

        df["split"] = df["block_id"].map(assign_split)

        # Verify zero leakage between splits
        train_set = set(df[df["split"] == "train"]["block_id"])
        val_set = set(df[df["split"] == "val"]["block_id"])
        test_set = set(df[df["split"] == "test"]["block_id"])

        assert len(train_set & test_set) == 0, "Data leakage detected: train and test share blocks!"
        assert len(train_set & val_set) == 0, "Data leakage detected: train and val share blocks!"
        assert len(val_set & test_set) == 0, "Data leakage detected: val and test share blocks!"

        # Save processed data and manifest
        hdfs_processed_path = self.processed_dir / "hdfs_cleaned.csv"
        df.to_csv(hdfs_processed_path, index=False)

        manifest = {
            "dataset": "HDFS_2k",
            "total_records": total_records,
            "valid_records": valid_records,
            "unique_blocks": len(unique_blocks),
            "normal_blocks": len(normal_blocks),
            "anomaly_blocks": len(anomaly_blocks),
            "splits": {
                "train_records": int((df["split"] == "train").sum()),
                "val_records": int((df["split"] == "val").sum()),
                "test_records": int((df["split"] == "test").sum()),
                "train_blocks": len(train_blocks),
                "val_blocks": len(val_blocks),
                "test_blocks": len(test_blocks),
                "test_anomaly_records": int(((df["split"] == "test") & df["is_anomaly"]).sum()),
                "val_anomaly_records": int(((df["split"] == "val") & df["is_anomaly"]).sum()),
            },
            "leakage_check_passed": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        manifest_path = self.processed_dir / "hdfs_splits_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info("HDFS processing complete. Output: %s, Manifest: %s", hdfs_processed_path, manifest_path)
        return df, manifest

    def load_and_process_bgl(self) -> tuple[pd.DataFrame, dict[str, Any]]:
        """Parse raw BGL logs, preserve temporal ordering, and perform chronological split."""
        logger.info("Processing BGL dataset from %s ...", self.raw_bgl)
        if not self.raw_bgl.exists():
            raise FileNotFoundError(f"BGL raw log not found at {self.raw_bgl}")

        records: list[dict[str, Any]] = []
        with open(self.raw_bgl, "r", encoding="utf-8", errors="replace") as f:
            for idx, line in enumerate(f):
                parsed = parse_bgl_line(idx, line)
                if parsed:
                    records.append(parsed)

        df = pd.DataFrame(records)
        total_records = len(df)
        valid_records = int(df["is_valid"].sum())
        df["is_anomaly"] = df["label"] == "Anomaly"
        total_anomalies = int(df["is_anomaly"].sum())

        logger.info("Parsed %d BGL records (%d valid, %d anomalies)", total_records, valid_records, total_anomalies)

        # Chronological Split to prevent future-looking leakage:
        # First 80% -> train, next 10% -> val, last 10% -> test
        n_train = int(total_records * 0.8)
        n_val = int(total_records * 0.1)

        splits = ["train"] * n_train + ["val"] * n_val + ["test"] * (total_records - n_train - n_val)
        df["split"] = splits

        # Verify temporal monotonicity between splits
        train_df = df[df["split"] == "train"]
        val_df = df[df["split"] == "val"]
        test_df = df[df["split"] == "test"]

        # Ensure line indices are disjoint and chronological
        assert train_df["line_idx"].max() < val_df["line_idx"].min(), "BGL chronological ordering violated (train -> val)"
        assert val_df["line_idx"].max() < test_df["line_idx"].min(), "BGL chronological ordering violated (val -> test)"

        bgl_processed_path = self.processed_dir / "bgl_cleaned.csv"
        df.to_csv(bgl_processed_path, index=False)

        manifest = {
            "dataset": "BGL_2k",
            "total_records": total_records,
            "valid_records": valid_records,
            "total_anomalies": total_anomalies,
            "splits": {
                "train_records": len(train_df),
                "val_records": len(val_df),
                "test_records": len(test_df),
                "train_anomalies": int(train_df["is_anomaly"].sum()),
                "val_anomalies": int(val_df["is_anomaly"].sum()),
                "test_anomalies": int(test_df["is_anomaly"].sum()),
            },
            "leakage_check_passed": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        manifest_path = self.processed_dir / "bgl_splits_manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info("BGL processing complete. Output: %s, Manifest: %s", bgl_processed_path, manifest_path)
        return df, manifest
