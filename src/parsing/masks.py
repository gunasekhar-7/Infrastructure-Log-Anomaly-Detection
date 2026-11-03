"""Masking rules and regular expressions for dynamic parameter normalization in Drain3."""

import re
from drain3.masking import MaskingInstruction

# Pre-compiled masking patterns
DEFAULT_MASKS = [
    # Hadoop Block IDs: blk_-1608999687919862906
    (r"blk_-?\d+", "<*BLOCK*>"),
    # IPv4 addresses with optional port: 10.251.73.220:50010 or 192.168.1.1
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d+)?\b", "<*IP*>"),
    # UUIDs: 123e4567-e89b-12d3-a456-426614174000
    (r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b", "<*UUID*>"),
    # Hexadecimal memory addresses: 0x7fff5fbff8e0
    (r"\b0x[a-fA-F0-9]+\b", "<*HEX*>"),
    # Absolute Unix file paths: /usr/local/bin/app or /var/log/syslog
    (r"(?:/[a-zA-Z0-9_\.\-]+){2,}", "<*PATH*>"),
    # Numbers preceded by key terms: size 67108864, port 8080, retry 3
    (r"(?<=\bsize\s)\d+", "<*NUM*>"),
    (r"(?<=\bport\s)\d+", "<*NUM*>"),
    (r"(?<=\bretries\s)\d+", "<*NUM*>"),
    (r"(?<=\bretry\s)\d+", "<*NUM*>"),
]


def get_default_masking_instructions() -> list[MaskingInstruction]:
    """Build list of Drain3 MaskingInstruction objects."""
    instructions: list[MaskingInstruction] = []
    for pattern, mask in DEFAULT_MASKS:
        instructions.append(MaskingInstruction(pattern, mask))
    return instructions


def pre_mask_message(message: str) -> str:
    """Pre-clean message before tree insertion to normalize common tokens."""
    cleaned = message.strip()
    for pattern, mask in DEFAULT_MASKS:
        cleaned = re.sub(pattern, mask, cleaned)
    return cleaned
