from __future__ import annotations

import argparse
import logging

from _bootstrap import bootstrap_src_path

bootstrap_src_path()

from rag_project import build_config
from rag_project.logging_utils import configure_logging, resolve_log_level
from rag_project.pipeline.jobs import crawl_to_filesystem


LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover, fetch, and parse technical documentation.")
    parser.add_argument("--root-url", required=True, help="Root URL of the documentation corpus.")
    parser.add_argument("--collection", default=None, help="Logical collection name for the corpus.")
    parser.add_argument("--db-dsn", default=None, help="Optional PostgreSQL DSN override.")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=300,
        help="Maximum number of pages to process. Use 0 (or negative) for no page-count limit.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Maximum depth to expand TOC links. Use a negative value for no depth limit.",
    )
    parser.add_argument(
        "--max-runtime-minutes",
        type=int,
        default=0,
        help="Stop discovery after this runtime in minutes (0 disables this guard rail).",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=0,
        help="Stop discovery after this number of fetch/TOC failures (0 disables this guard rail).",
    )
    parser.add_argument(
        "--max-total-bytes",
        type=int,
        default=0,
        help="Stop discovery after collecting this many HTML bytes (0 disables this guard rail).",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of worker threads for page processing.",
    )
    parser.add_argument(
        "--include-pattern",
        action="append",
        default=None,
        help="Optional URL substring allowed in scope (can be passed multiple times).",
    )
    parser.add_argument(
        "--exclude-pattern",
        action="append",
        default=None,
        help="Optional URL substring excluded from scope (can be passed multiple times).",
    )
    parser.add_argument(
        "--index-navigation-pages",
        action="store_true",
        help="Also index pages classified as navigation (default is to skip them).",
    )
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bars.")
    parser.add_argument("--quiet", action="store_true", help="Reduce log output.")
    parser.add_argument("--no-debug", action="store_true", help="Disable stage-level informational logs.")
    args = parser.parse_args()

    debug = not args.no_debug
    configure_logging(level=resolve_log_level(quiet=args.quiet, debug=debug))
    config = build_config(
        root_url=args.root_url,
        collection=args.collection,
        db_dsn=args.db_dsn,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        max_runtime_minutes=args.max_runtime_minutes,
        max_failures=args.max_failures,
        max_total_bytes=args.max_total_bytes,
        max_workers=args.max_workers,
        include_patterns=args.include_pattern,
        exclude_patterns=args.exclude_pattern,
        index_navigation_pages=args.index_navigation_pages,
    )
    stats = crawl_to_filesystem(config, show_progress=not args.no_progress, debug=debug)
    LOGGER.info("filesystem crawl finished for %s: %s", config.project.collection, stats)


if __name__ == "__main__":
    main()
