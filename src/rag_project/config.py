from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse


DEFAULT_DATABASE_DSN = "postgresql://postgres:postgres@localhost:5432/rag_project"
DEFAULT_USER_AGENT = "rag-project-bot/0.1"
DEFAULT_TOC_SELECTORS = [
    "nav", 
    "aside", 
    ".sidebar", 
    ".sphinxsidebar", 
    ".toctree-wrapper", 
    ".toc", 
    "#toc", 
    ".tree-node",
    ".nav-list",
    ".manual-toc",
    "#main_book_toc",
    ".main_book_toc",
    "#docs-menu",
    ".docs-nav",
    "#big_toc",
    ".big_toc_container",
]
DEFAULT_EXCLUDE_PATTERNS = ["/search", "/genindex", "/py-modindex", "/login", "/logout"]


@dataclass(slots=True)
class ProjectSettings:
    collection: str
    data_dir: Path


@dataclass(slots=True)
class DiscoverySettings:
    allowed_domains: list[str]
    start_urls: list[str]
    sitemap_urls: list[str]
    toc_css_selectors: list[str]
    include_url_patterns: list[str]
    exclude_url_patterns: list[str]
    max_pages: int


@dataclass(slots=True)
class FetchingSettings:
    user_agent: str
    request_timeout_seconds: int
    retry_attempts: int
    retry_backoff_seconds: float
    max_workers: int
    headless: bool


@dataclass(slots=True)
class ProcessingSettings:
    chunk_size: int
    chunk_overlap: int
    min_section_length: int


@dataclass(slots=True)
class EmbeddingSettings:
    provider: str
    model_name: str
    dimension: int
    device: str
    batch_size: int


@dataclass(slots=True)
class RetrievalSettings:
    lexical_limit: int
    vector_limit: int
    fused_limit: int
    rrf_k: int


@dataclass(slots=True)
class AppConfig:
    project: ProjectSettings
    discovery: DiscoverySettings
    fetching: FetchingSettings
    processing: ProcessingSettings
    embeddings: EmbeddingSettings
    retrieval: RetrievalSettings
    database_dsn: str


def build_config(
    *,
    root_url: str,
    collection: str | None = None,
    db_dsn: str | None = None,
    data_root: str | Path = "data",
    user_agent: str | None = None,
    max_pages: int = 300,
    max_workers: int = 4,
    request_timeout_seconds: int = 20,
    retry_attempts: int = 3,
    retry_backoff_seconds: float = 2.0,
    headless: bool = False,
    chunk_size: int = 1200,
    chunk_overlap: int = 150,
    min_section_length: int = 80,
    embedding_provider: str = "sentence_transformer",
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    embedding_dimension: int = 384,
    embedding_device: str = "auto",
    embedding_batch_size: int = 32,
    lexical_limit: int = 20,
    vector_limit: int = 20,
    fused_limit: int = 8,
    rrf_k: int = 60,
) -> AppConfig:
    parsed = urlparse(root_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid root URL: {root_url!r}")

    normalized_root_url = _normalize_root_url(root_url)
    collection_name = collection or derive_collection_name(normalized_root_url)
    
    # Improved pattern matching for Ansys-style secured URLs
    include_patterns = []
    if "returnurl=" in root_url.lower():
        # Extract the path from the returnurl parameter
        from urllib.parse import parse_qs
        params = parse_qs(parsed.query)
        return_url = params.get("returnurl", [None])[0]
        if return_url:
            return_path = urlparse(return_url).path
            # Use a broader pattern if it's a deep link
            include_patterns.append("/".join(return_path.split("/")[:3]))
    
    if not include_patterns and parsed.path and parsed.path != "/":
        include_patterns.append(parsed.path)
    
    collection_data_dir = Path(data_root) / collection_name

    return AppConfig(
        project=ProjectSettings(collection=collection_name, data_dir=collection_data_dir),
        discovery=DiscoverySettings(
            allowed_domains=[parsed.netloc],
            start_urls=[normalized_root_url],
            sitemap_urls=[],
            toc_css_selectors=list(DEFAULT_TOC_SELECTORS),
            include_url_patterns=include_patterns,
            exclude_url_patterns=list(DEFAULT_EXCLUDE_PATTERNS),
            max_pages=max_pages,
        ),
        fetching=FetchingSettings(
            user_agent=user_agent or os.getenv("RAG_USER_AGENT", DEFAULT_USER_AGENT),
            request_timeout_seconds=request_timeout_seconds,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
            max_workers=max_workers,
            headless=headless,
        ),
        processing=ProcessingSettings(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            min_section_length=min_section_length,
        ),
        embeddings=EmbeddingSettings(
            provider=embedding_provider,
            model_name=embedding_model,
            dimension=embedding_dimension,
            device=embedding_device,
            batch_size=embedding_batch_size,
        ),
        retrieval=RetrievalSettings(
            lexical_limit=lexical_limit,
            vector_limit=vector_limit,
            fused_limit=fused_limit,
            rrf_k=rrf_k,
        ),
        database_dsn=db_dsn or os.getenv("RAG_DATABASE_DSN", DEFAULT_DATABASE_DSN),
    )


def derive_collection_name(root_url: str) -> str:
    parsed = urlparse(root_url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/").replace("/", "-")
    raw = f"{host}-{path}" if path else host
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return slug or "default-collection"


def _normalize_root_url(root_url: str) -> str:
    parsed = urlparse(root_url)
    if parsed.query or parsed.fragment:
        return root_url

    path = parsed.path or "/"
    if path.endswith("/"):
        return root_url
    return urlunparse(parsed._replace(path=f"{path}/"))
