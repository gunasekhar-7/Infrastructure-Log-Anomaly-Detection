"""Dataset Acquisition Script for HDFS and BGL Benchmarks from Loghub."""

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging import get_logger, setup_logging

logger = get_logger("dataset_downloader")

DATASET_URLS = {
    "hdfs_2k": {
        "url": "https://raw.githubusercontent.com/logpai/loghub/master/HDFS/HDFS_2k.log",
        "dest": Path("data/raw/hdfs/HDFS_2k.log"),
        "expected_min_bytes": 200_000,
    },
    "hdfs_labels": {
        "url": "https://raw.githubusercontent.com/logpai/loglizer/master/data/HDFS/anomaly_label.csv",
        "dest": Path("data/raw/hdfs/anomaly_label.csv"),
        "expected_min_bytes": 10_000_000,
    },
    "bgl_2k": {
        "url": "https://raw.githubusercontent.com/logpai/loghub/master/BGL/BGL_2k.log",
        "dest": Path("data/raw/bgl/BGL_2k.log"),
        "expected_min_bytes": 250_000,
    },
}


def download_file(url: str, destination: Path, expected_min_bytes: int = 1000) -> bool:
    """Download a remote file with progress reporting and size validation."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists() and destination.stat().st_size >= expected_min_bytes:
        logger.info("File already exists and passes size check: %s (%d bytes)", destination, destination.stat().st_size)
        return True

    logger.info("Downloading %s -> %s ...", url, destination)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LogPulse/1.0"}
        )
        with urllib.request.urlopen(req, timeout=60) as response, open(destination, "wb") as out_file:
            content = response.read()
            out_file.write(content)

        file_size = destination.stat().st_size
        if file_size < expected_min_bytes:
            logger.error("Downloaded file %s size (%d bytes) smaller than expected (%d bytes)", destination, file_size, expected_min_bytes)
            return False

        # Calculate SHA256 checksum for audit reproducibility
        sha256_hash = hashlib.sha256()
        with open(destination, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)

        logger.info("Successfully downloaded %s (%d bytes, SHA256: %s)", destination, file_size, sha256_hash.hexdigest()[:16])
        return True
    except Exception as exc:
        logger.exception("Failed to download %s: %s", url, exc)
        return False


def acquire_all_datasets(download_labels: bool = True) -> bool:
    """Acquire all required benchmark datasets."""
    setup_logging(level="INFO")
    logger.info("Starting benchmark dataset acquisition...")

    success = True
    for key, spec in DATASET_URLS.items():
        if key == "hdfs_labels" and not download_labels:
            continue
        ok = download_file(spec["url"], spec["dest"], spec["expected_min_bytes"])
        if not ok:
            success = False

    if success:
        logger.info("All benchmark datasets acquired successfully!")
    else:
        logger.error("One or more datasets failed to download.")
    return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Acquire HDFS and BGL benchmark datasets from Loghub")
    parser.add_argument("--skip-full-labels", action="store_true", help="Skip large anomaly_label.csv if already present")
    args = parser.parse_args()

    ok = acquire_all_datasets(download_labels=not args.skip_full_labels)
    sys.exit(0 if ok else 1)
