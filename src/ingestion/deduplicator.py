"""Sliding Window Log Duplicate Detection."""

import hashlib
from collections import OrderedDict


class DuplicateDetector:
    """Detect duplicate log events within a rolling capacity window."""

    def __init__(self, capacity: int = 10_000) -> None:
        self.capacity = capacity
        # Ordered set to maintain LRU eviction
        self._seen_hashes: OrderedDict[str, float] = OrderedDict()

    def _compute_hash(self, host: str, service: str, message: str, timestamp_epoch: float | None = None) -> str:
        """Create deterministic content fingerprint."""
        raw_key = f"{host}|{service}|{message}"
        if timestamp_epoch is not None:
            # Group identical messages within the exact same second
            raw_key += f"|{int(timestamp_epoch)}"
        return hashlib.md5(raw_key.encode("utf-8")).hexdigest()

    def is_duplicate(
        self,
        host: str,
        service: str,
        message: str,
        timestamp_epoch: float | None = None
    ) -> bool:
        """Check whether a log signature was recently seen, and record it."""
        sig = self._compute_hash(host, service, message, timestamp_epoch)

        if sig in self._seen_hashes:
            # Move to end to renew recency
            self._seen_hashes.move_to_end(sig)
            return True

        self._seen_hashes[sig] = timestamp_epoch or 0.0

        # Evict oldest entry if capacity exceeded
        if len(self._seen_hashes) > self.capacity:
            self._seen_hashes.popitem(last=False)

        return False

    def clear(self) -> None:
        """Clear cache state."""
        self._seen_hashes.clear()

