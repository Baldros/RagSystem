from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from collections import defaultdict
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from tqdm.auto import tqdm

from rag_project.config import AppConfig
from rag_project.db.connection import Database, DatabaseConnectionError
from rag_project.db.repositories import RagRepository
from rag_project.discovery.service import DiscoveryService
from rag_project.embeddings.factory import build_embedder
from rag_project.extraction.content_extractor import ContentExtractor
from rag_project.fetching.http_client import HttpClient
from rag_project.models import Chunk, CrawlRun, DiscoveredNode, RawDocument, Section
from rag_project.paths import build_data_paths
from rag_project.pipeline.corpus_builder import CorpusBuilder
from rag_project.processing.chunker import Chunker
from rag_project.reporting.coverage import build_coverage_report
from rag_project.utils.files import read_jsonl, write_json, write_jsonl
from rag_project.utils.hashing import sha256_text


LOGGER = logging.getLogger(__name__)


def preflight_database(config: AppConfig, *, debug: bool = True) -> None:
    database = Database(config.database_dsn)
    if debug:
        LOGGER.info("checking PostgreSQL connectivity")
    try:
        database.ping()
    except DatabaseConnectionError as exc:
        if not exc.missing_database:
            raise
        if debug:
            LOGGER.info("target database is missing, attempting automatic creation")
        created = database.ensure_database_exists()
        if created and debug:
            LOGGER.info("database created successfully")
        database.ping()
    if debug:
        LOGGER.info("PostgreSQL connection ok")


def initialize_database(config: AppConfig, sql_path: Path, *, debug: bool = True) -> None:
    if debug:
        LOGGER.info("[1/3] initializing database schema for collection %s", config.project.collection)
    sql = sql_path.read_text(encoding="utf-8").replace("vector(384)", f"vector({config.embeddings.dimension})")
    temp_sql_path = sql_path.parent / ".tmp_001_init.sql"
    temp_sql_path.write_text(sql, encoding="utf-8")
    try:
        Database(config.database_dsn).execute_sql_file(temp_sql_path)
    finally:
        temp_sql_path.unlink(missing_ok=True)
    if debug:
        LOGGER.info("database schema ready")


def crawl_to_filesystem(config: AppConfig, *, show_progress: bool = True, debug: bool = True) -> dict[str, object]:
    data_paths = build_data_paths(config.project.data_dir)
    http_client = HttpClient(
        user_agent=config.fetching.user_agent,
        timeout_seconds=config.fetching.request_timeout_seconds,
        headless=config.fetching.headless,
        retry_attempts=config.fetching.retry_attempts,
        retry_backoff_seconds=config.fetching.retry_backoff_seconds,
    )
    if debug:
        LOGGER.info("[2/3] discovering documentation pages from %s", config.discovery.start_urls[0])
    discovery_service = DiscoveryService(config=config, http_client=http_client)
    discovery_result = discovery_service.discover()
    inventory = discovery_result.records
    skipped_urls = discovery_result.skipped
    write_jsonl(data_paths.inventory_jsonl, [asdict(item) for item in inventory])
    write_jsonl(data_paths.skipped_urls_jsonl, [asdict(item) for item in skipped_urls])
    discovered_nodes = _build_discovered_nodes(inventory)
    write_jsonl(data_paths.discovered_nodes_jsonl, [asdict(item) for item in discovered_nodes])
    write_json(data_paths.link_tree_json, _build_link_tree_payload(discovered_nodes))
    write_json(
        data_paths.discovery_report_json,
        {
            "stopped_reason": discovery_result.stopped_reason,
            "discovered_url_count": len(inventory),
            "skipped_url_count": len(skipped_urls),
            "failure_count": discovery_result.failure_count,
            "total_bytes": discovery_result.total_bytes,
            "max_pages": config.discovery.max_pages,
            "max_depth": config.discovery.max_depth,
            "max_runtime_minutes": config.discovery.max_runtime_minutes,
            "max_failures": config.discovery.max_failures,
            "max_total_bytes": config.discovery.max_total_bytes,
        },
    )
    if debug:
        LOGGER.info(
            "discovered %s candidate URLs (%s skipped, stop=%s) for collection %s",
            len(inventory),
            len(skipped_urls),
            discovery_result.stopped_reason,
            config.project.collection,
        )

    extractor = ContentExtractor()
    chunker = Chunker(
        chunk_size=config.processing.chunk_size,
        chunk_overlap=config.processing.chunk_overlap,
    )
    builder = CorpusBuilder(
        extractor=extractor,
        chunker=chunker,
        min_section_length=config.processing.min_section_length,
        collection=config.project.collection,
        index_navigation_pages=config.processing.index_navigation_pages,
    )

    documents: list[dict] = []
    sections: list[dict] = []
    chunks: list[dict] = []
    failures = 0

    def process_record(record):
        response = http_client.get(record.url)
        raw_document, page_sections, page_chunks = builder.build_document(
            canonical_url=record.canonical_url,
            source_url=response.url,
            html=response.text,
            status_code=response.status_code,
            headers=response.headers,
            source_metadata=record.metadata,
        )
        return asdict(raw_document), [asdict(item) for item in page_sections], [asdict(item) for item in page_chunks]

    try:
        max_workers = max(1, config.fetching.max_workers)
        if max_workers == 1:
            progress = tqdm(
                inventory,
                total=len(inventory),
                desc="Processing pages",
                disable=not show_progress,
            )
            for record in progress:
                try:
                    raw_document, page_sections, page_chunks = process_record(record)
                except Exception as exc:
                    failures += 1
                    LOGGER.warning("failed to process %s: %s", record.url, exc)
                    continue
                documents.append(raw_document)
                sections.extend(page_sections)
                chunks.extend(page_chunks)
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(process_record, record): record for record in inventory}
                progress = tqdm(
                    as_completed(future_map),
                    total=len(future_map),
                    desc="Processing pages",
                    disable=not show_progress,
                )
                for future in progress:
                    record = future_map[future]
                    try:
                        raw_document, page_sections, page_chunks = future.result()
                    except Exception as exc:
                        failures += 1
                        LOGGER.warning("failed to process %s: %s", record.url, exc)
                        continue
                    documents.append(raw_document)
                    sections.extend(page_sections)
                    chunks.extend(page_chunks)
    finally:
        http_client.close()

    documents.sort(key=lambda item: item["canonical_url"])
    sections.sort(key=lambda item: (item["canonical_url"], item["order_in_page"], item["section_id"]))
    chunks.sort(key=lambda item: (item["canonical_url"], item["section_id"], item["order_in_section"], item["chunk_id"]))

    write_jsonl(data_paths.raw_documents_jsonl, documents)
    write_jsonl(data_paths.sections_jsonl, sections)
    write_jsonl(data_paths.chunks_jsonl, chunks)
    report = build_coverage_report(
        inventory=[asdict(item) for item in inventory],
        documents=documents,
        skipped=[asdict(item) for item in skipped_urls],
        stopped_reason=discovery_result.stopped_reason,
    )
    write_json(data_paths.coverage_report_json, report)
    if debug:
        LOGGER.info(
            "crawl finished: %s nodes, %s docs (%s content / %s nav), %s sections, %s chunks, %s failures, %.2f%% coverage",
            len(discovered_nodes),
            len(documents),
            report["content_url_count"],
            report["navigation_url_count"],
            len(sections),
            len(chunks),
            failures,
            report["coverage_ratio"] * 100,
        )
    return {
        "nodes": len(discovered_nodes),
        "documents": len(documents),
        "sections": len(sections),
        "chunks": len(chunks),
        "failures": failures,
        "skipped_urls": len(skipped_urls),
        "discovery_failures": discovery_result.failure_count,
        "discovery_stop_reason": discovery_result.stopped_reason,
        "coverage_ratio": report["coverage_ratio"],
    }


def index_filesystem_corpus(config: AppConfig, *, show_progress: bool = True, debug: bool = True) -> dict[str, object]:
    repository = RagRepository(Database(config.database_dsn))
    embedder = build_embedder(config.embeddings)
    paths = build_data_paths(config.project.data_dir)
    if debug:
        LOGGER.info("[3/3] indexing processed corpus into PostgreSQL")

    discovered_nodes = [_parse_discovered_node(item) for item in read_jsonl(paths.discovered_nodes_jsonl)]
    raw_documents = [_parse_raw_document(item) for item in read_jsonl(paths.raw_documents_jsonl)]
    sections = [Section(**item) for item in read_jsonl(paths.sections_jsonl)]
    chunks = [Chunk(**item) for item in read_jsonl(paths.chunks_jsonl)]

    repository.upsert_crawl_run(
        CrawlRun(
            run_id=sha256_text(datetime.utcnow().isoformat()),
            collection=config.project.collection,
            started_at=datetime.utcnow(),
            seed_urls=config.discovery.start_urls,
            notes="db index run",
        )
    )

    repository.clear_collection(config.project.collection)
    repository.upsert_discovered_nodes(discovered_nodes)

    sections_by_url: dict[str, list[Section]] = defaultdict(list)
    for section in sections:
        sections_by_url[section.canonical_url].append(section)

    chunks_by_url: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        chunks_by_url[chunk.canonical_url].append(chunk)

    texts = [chunk.text for chunk in chunks]
    embeddings = embedder.embed_texts(texts, show_progress=show_progress) if texts else []
    embeddings_by_chunk_id = {chunk.chunk_id: embedding for chunk, embedding in zip(chunks, embeddings)}

    iterable = tqdm(
        raw_documents,
        total=len(raw_documents),
        desc="Indexing documents",
        disable=not show_progress,
    )
    for raw_document in iterable:
        repository.upsert_raw_document(raw_document)
        repository.replace_sections(
            raw_document.collection,
            raw_document.canonical_url,
            sections_by_url.get(raw_document.canonical_url, []),
        )
        repository.replace_chunks(
            raw_document.collection,
            raw_document.canonical_url,
            chunks_by_url.get(raw_document.canonical_url, []),
            embeddings_by_chunk_id=embeddings_by_chunk_id,
        )

    actual_device = getattr(embedder, "device", config.embeddings.device)
    if debug:
        LOGGER.info(
            "indexing finished: %s nodes, %s documents, %s sections, %s chunks on device %s",
            len(discovered_nodes),
            len(raw_documents),
            len(sections),
            len(chunks),
            actual_device,
        )
    return {
        "nodes": len(discovered_nodes),
        "documents": len(raw_documents),
        "sections": len(sections),
        "chunks": len(chunks),
        "embedding_device": actual_device,
    }


def _parse_raw_document(item: dict) -> RawDocument:
    payload = dict(item)
    payload["fetched_at"] = datetime.fromisoformat(payload["fetched_at"])
    return RawDocument(**payload)


def _parse_discovered_node(item: dict) -> DiscoveredNode:
    return DiscoveredNode(**item)


def _build_discovered_nodes(inventory: list) -> list[DiscoveredNode]:
    canonical_to_node_id = {
        record.canonical_url: sha256_text(f"{record.collection}::{record.canonical_url}")
        for record in inventory
    }

    nodes: list[DiscoveredNode] = []
    for record in inventory:
        metadata = dict(record.metadata)
        parent_canonical_url = metadata.get("parent_canonical_url") or record.discovered_from
        node = DiscoveredNode(
            collection=record.collection,
            node_id=canonical_to_node_id[record.canonical_url],
            canonical_url=record.canonical_url,
            url=record.url,
            title=metadata.get("link_text") or record.canonical_url,
            source=record.source,
            depth=record.depth,
            parent_node_id=canonical_to_node_id.get(parent_canonical_url),
            parent_canonical_url=parent_canonical_url,
            toc_level=metadata.get("toc_level"),
            toc_order=metadata.get("toc_order"),
            doc_version=record.doc_version,
            metadata=metadata,
        )
        nodes.append(node)
    return nodes


def _build_link_tree_payload(nodes: list[DiscoveredNode]) -> dict:
    nodes_by_id: dict[str, dict] = {}
    children_by_parent: dict[str | None, list[str]] = defaultdict(list)

    for node in nodes:
        nodes_by_id[node.node_id] = {
            "node_id": node.node_id,
            "url": node.url,
            "canonical_url": node.canonical_url,
            "title": node.title,
            "source": node.source,
            "depth": node.depth,
            "doc_version": node.doc_version,
            "toc_level": node.toc_level,
            "toc_order": node.toc_order,
            "children": [],
        }
        children_by_parent[node.parent_node_id].append(node.node_id)

    for parent_id, child_ids in children_by_parent.items():
        ordered_children = sorted(
            [nodes_by_id[child_id] for child_id in child_ids if child_id in nodes_by_id],
            key=lambda child: (
                child["toc_order"] is None,
                child["toc_order"] if child["toc_order"] is not None else child["title"],
            ),
        )
        if parent_id is not None and parent_id in nodes_by_id:
            nodes_by_id[parent_id]["children"] = ordered_children

    roots = [
        nodes_by_id[node_id]
        for node_id in children_by_parent.get(None, [])
        if node_id in nodes_by_id
    ]
    roots.sort(
        key=lambda child: (
            child["toc_order"] is None,
            child["toc_order"] if child["toc_order"] is not None else child["title"],
        )
    )
    return {
        "node_count": len(nodes_by_id),
        "roots": roots,
    }
