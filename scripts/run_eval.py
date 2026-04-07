from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import bootstrap_src_path

bootstrap_src_path()

from rag_project import build_config
from rag_project.db.connection import Database
from rag_project.db.repositories import RagRepository
from rag_project.embeddings.factory import build_embedder
from rag_project.logging_utils import configure_logging
from rag_project.pipeline.jobs import preflight_database
from rag_project.retrieval.hybrid import HybridRetriever


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simple Recall@K evaluation over fused retrieval output.")
    parser.add_argument("--collection", required=True, help="Logical collection name to search.")
    parser.add_argument(
        "--root-url",
        default="https://placeholder.local/",
        help="Optional root URL used only to build runtime defaults.",
    )
    parser.add_argument("--db-dsn", default=None, help="Optional PostgreSQL DSN override.")
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
        help="Batch size used by the embedding model.",
    )
    parser.add_argument(
        "--eval-file",
        required=True,
        help="Path to a JSON file with [{'query': str, 'expected_urls': [..]}].",
    )
    args = parser.parse_args()

    configure_logging()
    config = build_config(
        root_url=args.root_url,
        collection=args.collection,
        db_dsn=args.db_dsn,
        embedding_device=args.device,
        embedding_batch_size=args.embedding_batch_size,
    )
    try:
        preflight_database(config, debug=True)
    except RuntimeError as exc:
        print("")
        print(str(exc))
        raise SystemExit(2) from exc
    repository = RagRepository(Database(config.database_dsn))
    embedder = build_embedder(config.embeddings)
    retriever = HybridRetriever(repository=repository, embedder=embedder, settings=config.retrieval)

    rows = json.loads(Path(args.eval_file).read_text(encoding="utf-8"))
    hits = 0
    for row in rows:
        trace = retriever.search(collection=args.collection, query=row["query"])
        retrieved_urls = {item.canonical_url for item in trace.fused_hits}
        expected_urls = set(row["expected_urls"])
        success = bool(retrieved_urls & expected_urls)
        hits += int(success)
        print(json.dumps({"query": row["query"], "hit": success, "retrieved_urls": sorted(retrieved_urls)}))

    recall_at_k = hits / len(rows) if rows else 0.0
    print("")
    print(json.dumps({"recall_at_k": recall_at_k, "total_queries": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
