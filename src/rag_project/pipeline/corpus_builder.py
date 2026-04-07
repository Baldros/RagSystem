from __future__ import annotations

from datetime import datetime

from rag_project.models import RawDocument
from rag_project.processing.chunker import Chunker
from rag_project.processing.sectionizer import split_markdown_into_sections
from rag_project.utils.hashing import sha256_text


class CorpusBuilder:
    def __init__(self, extractor, chunker: Chunker, min_section_length: int, collection: str) -> None:
        self.extractor = extractor
        self.chunker = chunker
        self.min_section_length = min_section_length
        self.collection = collection

    def build_document(
        self,
        canonical_url: str,
        source_url: str,
        html: str,
        status_code: int,
        headers: dict,
        source_metadata: dict | None = None,
    ):
        title, text_content, markdown_content = self.extractor.extract(html=html, url=source_url)
        metadata = {
            "etag": headers.get("ETag"),
            "last_modified": headers.get("Last-Modified"),
        }
        if source_metadata:
            metadata.update(source_metadata)
        raw_document = RawDocument(
            collection=self.collection,
            canonical_url=canonical_url,
            source_url=source_url,
            title=title,
            html=html,
            text_content=text_content,
            markdown_content=markdown_content,
            http_status=status_code,
            content_hash=sha256_text(markdown_content or text_content),
            fetched_at=datetime.utcnow(),
            metadata=metadata,
        )
        sections = split_markdown_into_sections(
            collection=self.collection,
            canonical_url=canonical_url,
            markdown=markdown_content or text_content,
            min_section_length=self.min_section_length,
        )
        chunks = []
        for section in sections:
            chunks.extend(self.chunker.chunk_section(section))
        return raw_document, sections, chunks
