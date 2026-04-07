from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class CrawlRun:
    run_id: str
    collection: str
    started_at: datetime
    seed_urls: list[str]
    notes: str = ""


@dataclass(slots=True)
class UrlRecord:
    collection: str
    url: str
    canonical_url: str
    source: str
    depth: int
    discovered_from: str | None = None
    doc_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DiscoveredNode:
    collection: str
    node_id: str
    canonical_url: str
    url: str
    title: str
    source: str
    depth: int
    parent_node_id: str | None = None
    parent_canonical_url: str | None = None
    toc_level: int | None = None
    toc_order: int | None = None
    doc_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RawDocument:
    collection: str
    canonical_url: str
    source_url: str
    title: str
    html: str
    text_content: str
    markdown_content: str
    http_status: int
    content_hash: str
    fetched_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Section:
    collection: str
    section_id: str
    canonical_url: str
    heading: str
    level: int
    order_in_page: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    collection: str
    chunk_id: str
    section_id: str
    canonical_url: str
    order_in_section: int
    text: str
    token_estimate: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalHit:
    collection: str
    chunk_id: str
    canonical_url: str
    section_id: str
    score: float
    source: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalTrace:
    collection: str
    query: str
    lexical_hits: list[RetrievalHit]
    vector_hits: list[RetrievalHit]
    fused_hits: list[RetrievalHit]
    created_at: datetime


def as_dict(item: Any) -> dict[str, Any]:
    return asdict(item)
