from __future__ import annotations

import argparse

from _bootstrap import bootstrap_src_path

PROJECT_ROOT = bootstrap_src_path()

from rag_project import build_config
from rag_project.logging_utils import configure_logging, resolve_log_level
from rag_project.pipeline.jobs import initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize PostgreSQL schema for the RAG project.")
    parser.add_argument("--root-url", required=True, help="Root URL of the documentation corpus.")
    parser.add_argument("--collection", default=None, help="Logical collection name for the corpus.")
    parser.add_argument("--db-dsn", default=None, help="Optional PostgreSQL DSN override.")
    parser.add_argument("--quiet", action="store_true", help="Reduce log output.")
    parser.add_argument("--no-debug", action="store_true", help="Disable stage-level informational logs.")
    args = parser.parse_args()

    debug = not args.no_debug
    configure_logging(level=resolve_log_level(quiet=args.quiet, debug=debug))
    config = build_config(root_url=args.root_url, collection=args.collection, db_dsn=args.db_dsn)
    try:
        initialize_database(config, PROJECT_ROOT / "sql" / "001_init.sql", debug=debug)
    except RuntimeError as exc:
        print("")
        print(str(exc))
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
