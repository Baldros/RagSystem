from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from pgvector.psycopg import Vector

from rag_project.models import Chunk, CrawlRun, DiscoveredNode, RawDocument, RetrievalHit, RetrievalTrace, Section


class RagRepository:
    def __init__(self, db) -> None:
        self.db = db

    def clear_collection(self, collection: str) -> None:
        statements = [
            ("delete from retrieval_traces where collection_name = %s", (collection,)),
            ("delete from discovered_nodes where collection_name = %s", (collection,)),
            ("delete from raw_documents where collection_name = %s", (collection,)),
        ]
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                for sql, params in statements:
                    cur.execute(sql, params)
            conn.commit()

    def upsert_crawl_run(self, run: CrawlRun) -> None:
        sql = """
        insert into crawl_runs (run_id, collection_name, started_at, seed_urls, notes)
        values (%s, %s, %s, %s::jsonb, %s)
        on conflict (run_id) do update
        set collection_name = excluded.collection_name,
            started_at = excluded.started_at,
            seed_urls = excluded.seed_urls,
            notes = excluded.notes
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (run.run_id, run.collection, run.started_at, json.dumps(run.seed_urls), run.notes))
            conn.commit()

    def upsert_raw_document(self, document: RawDocument) -> None:
        sql = """
        insert into raw_documents (
            collection_name,
            canonical_url,
            source_url,
            title,
            html,
            text_content,
            markdown_content,
            http_status,
            content_hash,
            fetched_at,
            metadata
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        on conflict (collection_name, canonical_url) do update
        set source_url = excluded.source_url,
            title = excluded.title,
            html = excluded.html,
            text_content = excluded.text_content,
            markdown_content = excluded.markdown_content,
            http_status = excluded.http_status,
            content_hash = excluded.content_hash,
            fetched_at = excluded.fetched_at,
            metadata = excluded.metadata
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        document.collection,
                        document.canonical_url,
                        document.source_url,
                        document.title,
                        document.html,
                        document.text_content,
                        document.markdown_content,
                        document.http_status,
                        document.content_hash,
                        document.fetched_at,
                        json.dumps(document.metadata),
                    ),
                )
            conn.commit()

    def upsert_discovered_nodes(self, nodes: Iterable[DiscoveredNode]) -> None:
        sql = """
        insert into discovered_nodes (
            collection_name,
            node_id,
            canonical_url,
            url,
            title,
            source,
            depth,
            parent_node_id,
            parent_canonical_url,
            toc_level,
            toc_order,
            doc_version,
            metadata
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        on conflict (collection_name, node_id) do update
        set canonical_url = excluded.canonical_url,
            url = excluded.url,
            title = excluded.title,
            source = excluded.source,
            depth = excluded.depth,
            parent_node_id = excluded.parent_node_id,
            parent_canonical_url = excluded.parent_canonical_url,
            toc_level = excluded.toc_level,
            toc_order = excluded.toc_order,
            doc_version = excluded.doc_version,
            metadata = excluded.metadata
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                for node in nodes:
                    cur.execute(
                        sql,
                        (
                            node.collection,
                            node.node_id,
                            node.canonical_url,
                            node.url,
                            node.title,
                            node.source,
                            node.depth,
                            node.parent_node_id,
                            node.parent_canonical_url,
                            node.toc_level,
                            node.toc_order,
                            node.doc_version,
                            json.dumps(node.metadata),
                        ),
                    )
            conn.commit()

    def replace_sections(self, collection: str, canonical_url: str, sections: Iterable[Section]) -> None:
        delete_sql = "delete from sections where collection_name = %s and canonical_url = %s"
        insert_sql = """
        insert into sections (
            collection_name,
            section_id,
            canonical_url,
            heading,
            level,
            order_in_page,
            text,
            metadata
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(delete_sql, (collection, canonical_url))
                for section in sections:
                    cur.execute(
                        insert_sql,
                        (
                            section.collection,
                            section.section_id,
                            section.canonical_url,
                            section.heading,
                            section.level,
                            section.order_in_page,
                            section.text,
                            json.dumps(section.metadata),
                        ),
                    )
            conn.commit()

    def replace_chunks(
        self,
        collection: str,
        canonical_url: str,
        chunks: Iterable[Chunk],
        embeddings_by_chunk_id: dict[str, list[float]] | None = None,
    ) -> None:
        delete_sql = "delete from chunks where collection_name = %s and canonical_url = %s"
        insert_sql = """
        insert into chunks (
            collection_name,
            chunk_id,
            section_id,
            canonical_url,
            order_in_section,
            text,
            token_estimate,
            metadata,
            embedding
        )
        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
        """
        embeddings_by_chunk_id = embeddings_by_chunk_id or {}
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(delete_sql, (collection, canonical_url))
                for chunk in chunks:
                    embedding = embeddings_by_chunk_id.get(chunk.chunk_id)
                    vector_value = Vector(embedding) if embedding is not None else None
                    cur.execute(
                        insert_sql,
                        (
                            chunk.collection,
                            chunk.chunk_id,
                            chunk.section_id,
                            chunk.canonical_url,
                            chunk.order_in_section,
                            chunk.text,
                            chunk.token_estimate,
                            json.dumps(chunk.metadata),
                            vector_value,
                        ),
                    )
            conn.commit()

    def lexical_search(self, collection: str, query: str, limit: int) -> list[RetrievalHit]:
        sql = """
        select
            collection_name,
            chunk_id,
            canonical_url,
            section_id,
            ts_rank_cd(search_vector, websearch_to_tsquery('english', %s)) as score,
            text,
            metadata
        from chunks
        where collection_name = %s
          and search_vector @@ websearch_to_tsquery('english', %s)
        order by score desc, chunk_id asc
        limit %s
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (query, collection, query, limit))
                rows = cur.fetchall()
        return [
            RetrievalHit(
                collection=row[0],
                chunk_id=row[1],
                canonical_url=row[2],
                section_id=row[3],
                score=float(row[4]),
                source="lexical",
                text=row[5],
                metadata=row[6] or {},
            )
            for row in rows
        ]

    def vector_search(self, collection: str, embedding: list[float], limit: int) -> list[RetrievalHit]:
        sql = """
        select
            collection_name,
            chunk_id,
            canonical_url,
            section_id,
            1 - (embedding <=> %s::vector) as score,
            text,
            metadata
        from chunks
        where collection_name = %s
          and embedding is not null
        order by embedding <=> %s::vector asc
        limit %s
        """
        vector_value = Vector(embedding)
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (vector_value, collection, vector_value, limit))
                rows = cur.fetchall()
        return [
            RetrievalHit(
                collection=row[0],
                chunk_id=row[1],
                canonical_url=row[2],
                section_id=row[3],
                score=float(row[4]),
                source="vector",
                text=row[5],
                metadata=row[6] or {},
            )
            for row in rows
        ]

    def insert_retrieval_trace(self, trace: RetrievalTrace) -> None:
        sql = """
        insert into retrieval_traces (
            collection_name,
            query,
            created_at,
            lexical_hits,
            vector_hits,
            fused_hits
        )
        values (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        trace.collection,
                        trace.query,
                        trace.created_at,
                        json.dumps([asdict(hit) for hit in trace.lexical_hits]),
                        json.dumps([asdict(hit) for hit in trace.vector_hits]),
                        json.dumps([asdict(hit) for hit in trace.fused_hits]),
                    ),
                )
            conn.commit()

    def fetch_chunks_for_url(self, collection: str, canonical_url: str) -> list[tuple]:
        sql = """
        select chunk_id, section_id, canonical_url, order_in_section, text, token_estimate, metadata
        from chunks
        where collection_name = %s and canonical_url = %s
        order by order_in_section asc
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (collection, canonical_url))
                return cur.fetchall()

    def fetch_recent_documents(self, collection: str, limit: int = 20) -> list[tuple]:
        sql = """
        select canonical_url, title, fetched_at, content_hash
        from raw_documents
        where collection_name = %s
        order by fetched_at desc
        limit %s
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (collection, limit))
                return cur.fetchall()

    def fetch_discovered_node_by_url(self, collection: str, canonical_url: str) -> tuple | None:
        sql = """
        select node_id, canonical_url, title, parent_node_id, parent_canonical_url, toc_level, toc_order
        from discovered_nodes
        where collection_name = %s and canonical_url = %s
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (collection, canonical_url))
                return cur.fetchone()

    def fetch_discovered_node_by_id(self, collection: str, node_id: str) -> tuple | None:
        sql = """
        select node_id, canonical_url, title, parent_node_id, parent_canonical_url, toc_level, toc_order
        from discovered_nodes
        where collection_name = %s and node_id = %s
        """
        with self.db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (collection, node_id))
                return cur.fetchone()
