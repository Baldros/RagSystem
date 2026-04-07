from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def resolve_log_level(*, quiet: bool = False, debug: bool = True) -> int:
    if quiet:
        return logging.WARNING
    if debug:
        return logging.INFO
    return logging.WARNING
