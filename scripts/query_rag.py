from __future__ import annotations

import argparse

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
    parser = argparse.ArgumentParser(description="Run a hybrid retrieval query against the indexed corpus.")
    parser.add_argument("--query", required=True, help="User query to search in the documentation corpus.")
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
        "--top-k",
        type=int,
        default=8,
        help="Maximum number of fused hits to print.",
    )
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=600,
        help="Maximum number of text characters to print per hit.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show additional hierarchy and metadata for each result.",
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
    trace = retriever.search(collection=args.collection, query=args.query)

    print("")
    print(f"Collection: {args.collection}")
    print(f"Query: {args.query}")
    print(f"Fused hits available: {len(trace.fused_hits)}")
    print("")
    for index, hit in enumerate(trace.fused_hits[: args.top_k], start=1):
        hierarchy_info = build_hierarchy_info(repository, args.collection, hit.canonical_url)
        print(f"[{index}] score={hit.score:.4f} source={hit.source}")
        print(f"url: {hit.canonical_url}")
        print(f"section: {hit.section_id}")
        heading = hit.metadata.get("heading")
        if heading:
            print(f"heading: {heading}")
        if hierarchy_info["path"]:
            print(f"path: {' > '.join(hierarchy_info['path'])}")
        if args.verbose:
            print(f"chunk_id: {hit.chunk_id}")
            print(f"toc_level: {hierarchy_info['toc_level']}")
            print(f"toc_order: {hierarchy_info['toc_order']}")
            print(f"node_id: {hierarchy_info['node_id']}")
            print(f"parent_node_id: {hierarchy_info['parent_node_id']}")
            if hit.metadata:
                print(f"chunk_metadata: {hit.metadata}")
        print(hit.text[: args.preview_chars].strip())
        print("")


def build_hierarchy_info(repository: RagRepository, collection: str, canonical_url: str) -> dict:
    node = repository.fetch_discovered_node_by_url(collection, canonical_url)
    if not node:
        return {
            "node_id": None,
            "parent_node_id": None,
            "toc_level": None,
            "toc_order": None,
            "path": [],
        }

    path: list[str] = []
    current = node
    seen: set[str] = set()
    root_node = node
    while current:
        node_id, _canonical_url, title, parent_node_id, _parent_canonical_url, _toc_level, _toc_order = current
        if node_id in seen:
            break
        seen.add(node_id)
        root_node = current
        if title:
            path.append(title)
        if not parent_node_id:
            break
        current = repository.fetch_discovered_node_by_id(collection, parent_node_id)

    path.reverse()
    node_id, _canonical_url, _title, parent_node_id, _parent_canonical_url, toc_level, toc_order = node
    return {
        "node_id": node_id,
        "parent_node_id": parent_node_id,
        "toc_level": toc_level,
        "toc_order": toc_order,
        "root_title": root_node[2] if root_node else None,
        "path": path,
    }


if __name__ == "__main__":
    main()
