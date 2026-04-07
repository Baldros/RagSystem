from __future__ import annotations

from rag_project.models import Chunk, Section
from rag_project.utils.hashing import sha256_text
from rag_project.utils.text import estimate_tokens


class Chunker:
    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_section(self, section: Section) -> list[Chunk]:
        text = section.text.strip()
        if len(text) <= self.chunk_size:
            return [
                Chunk(
                    collection=section.collection,
                    chunk_id=sha256_text(f"{section.section_id}::0"),
                    section_id=section.section_id,
                    canonical_url=section.canonical_url,
                    order_in_section=0,
                    text=text,
                    token_estimate=estimate_tokens(text),
                    metadata={"heading": section.heading},
                )
            ]

        chunks: list[Chunk] = []
        start = 0
        order = 0
        while start < len(text):
            end = min(len(text), start + self.chunk_size)
            window = text[start:end].strip()
            if window:
                chunks.append(
                    Chunk(
                        collection=section.collection,
                        chunk_id=sha256_text(f"{section.section_id}::{order}"),
                        section_id=section.section_id,
                        canonical_url=section.canonical_url,
                        order_in_section=order,
                        text=window,
                        token_estimate=estimate_tokens(window),
                        metadata={"heading": section.heading},
                    )
                )
            if end >= len(text):
                break
            start = max(end - self.chunk_overlap, start + 1)
            order += 1
        return chunks
