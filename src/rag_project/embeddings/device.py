from __future__ import annotations

import logging


LOGGER = logging.getLogger(__name__)


def resolve_device(requested_device: str) -> str:
    normalized = requested_device.lower().strip()
    if normalized in {"cpu", "cuda"}:
        return normalized
    if normalized != "auto":
        raise ValueError(f"Unsupported embedding device: {requested_device}")

    try:
        import torch
    except Exception:
        LOGGER.info("torch not available for explicit device detection, falling back to cpu")
        return "cpu"

    if torch.cuda.is_available():
        return "cuda"
    return "cpu"
