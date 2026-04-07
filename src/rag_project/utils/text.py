from __future__ import annotations

import re


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def estimate_tokens(text: str) -> int:
    # Approximation good enough for chunk sizing before tokenizer-specific tuning.
    return max(1, len(text) // 4)
