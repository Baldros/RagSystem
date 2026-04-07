from __future__ import annotations

import argparse
import logging

from _bootstrap import bootstrap_src_path

PROJECT_ROOT = bootstrap_src_path()

from rag_project import build_config
from rag_project.logging_utils import configure_logging, resolve_log_level
from rag_project.pipeline.jobs import (
    crawl_to_filesystem,
    index_filesystem_corpus,
    initialize_database,
    preflight_database,
)


LOGGER = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a vector-ready documentation corpus from a single root URL."
    )
    parser.add_argument("--root-url", required=True, help="Root URL of the documentation corpus.")
    parser.add_argument("--collection", default=None, help="Logical collection name for the corpus.")
    parser.add_argument("--db-dsn", default=None, help="Optional PostgreSQL DSN override.")
    parser.add_argument("--max-pages", type=int, default=300, help="Maximum number of pages to process.")
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=20,
        help="Per-page browser/network timeout in seconds.",
    )
    parser.add_argument(
        "--fetch-retries",
        type=int,
        default=3,
        help="How many times to retry a page when browser navigation fails.",
    )
    parser.add_argument(
        "--retry-backoff",
        type=float,
        default=2.0,
        help="Seconds to wait between fetch retries.",
    )
    parser.add_argument(
        "--filesystem-only",
        action="store_true",
        help="Run discovery and parsing only, without requiring PostgreSQL or indexing.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Device for embeddings. 'auto' prefers CUDA when available.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=32,
        help="Batch size used during embedding generation.",
    )
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bars.")
    parser.add_argument("--quiet", action="store_true", help="Reduce log output.")
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Disable stage-level informational logs while keeping warnings/errors.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode (no window).",
    )
    args = parser.parse_args()

    debug = not args.no_debug
    configure_logging(level=resolve_log_level(quiet=args.quiet, debug=debug))
    config = build_config(
        root_url=args.root_url,
        collection=args.collection,
        db_dsn=args.db_dsn,
        max_pages=args.max_pages,
        request_timeout_seconds=args.request_timeout,
        retry_attempts=args.fetch_retries,
        retry_backoff_seconds=args.retry_backoff,
        headless=args.headless,
        embedding_device=args.device,
        embedding_batch_size=args.embedding_batch_size,
    )

    LOGGER.info("building vector store for collection %s", config.project.collection)
    LOGGER.info(
        "browser mode: %s | request timeout: %ss | fetch retries: %s",
        "headless" if config.fetching.headless else "visible",
        config.fetching.request_timeout_seconds,
        config.fetching.retry_attempts,
    )
    index_stats = {"nodes": 0, "documents": 0, "sections": 0, "chunks": 0}
    if args.filesystem_only:
        LOGGER.info("filesystem-only mode enabled: skipping PostgreSQL initialization and indexing")
        crawl_stats = crawl_to_filesystem(config, show_progress=not args.no_progress, debug=debug)
    else:
        try:
            preflight_database(config, debug=debug)
        except RuntimeError as exc:
            print("")
            print(str(exc))
            print("")
            print("Tip:")
            print(
                "Use --filesystem-only if you want to keep the crawl artifacts now and index into PostgreSQL later."
            )
            raise SystemExit(2) from exc
        try:
            initialize_database(config, PROJECT_ROOT / "sql" / "001_init.sql", debug=debug)
        except RuntimeError as exc:
            print("")
            print(str(exc))
            print("")
            print("Tip:")
            print(
                "Use --filesystem-only if you want to keep the crawl artifacts now and finish the PostgreSQL setup later."
            )
            raise SystemExit(2) from exc
        crawl_stats = crawl_to_filesystem(config, show_progress=not args.no_progress, debug=debug)
        index_stats = index_filesystem_corpus(config, show_progress=not args.no_progress, debug=debug)
    LOGGER.info("build completed for %s", config.project.collection)
    LOGGER.info("crawl stats: %s", crawl_stats)
    LOGGER.info("index stats: %s", index_stats)
    print("")
    print("Build summary")
    print(f"Collection: {config.project.collection}")
    print(f"Root URL: {config.discovery.start_urls[0]}")
    print(f"Discovered nodes: {crawl_stats.get('nodes', index_stats.get('nodes', 0))}")
    print(f"Indexed documents: {index_stats['documents']}")
    print(f"Indexed sections: {index_stats['sections']}")
    print(f"Indexed chunks: {index_stats['chunks']}")
    if "coverage_ratio" in crawl_stats:
        print(f"Coverage: {crawl_stats['coverage_ratio'] * 100:.2f}%")
    if "failures" in crawl_stats:
        print(f"Failures: {crawl_stats['failures']}")
    print(f"Embedding device: {index_stats.get('embedding_device', config.embeddings.device)}")
    print(f"Embedding batch size: {config.embeddings.batch_size}")


if __name__ == "__main__":
    main()
