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
    parser.add_argument("--max-pages", type=int, default=300, help="Maximum number of pages to process.")
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
    )
    stats = crawl_to_filesystem(config, show_progress=not args.no_progress, debug=debug)
    LOGGER.info("filesystem crawl finished for %s: %s", config.project.collection, stats)


if __name__ == "__main__":
    main()
