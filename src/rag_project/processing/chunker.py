from __future__ import annotations

from bisect import bisect_left, bisect_right
import re

from rag_project.models import Chunk, Section
from rag_project.utils.hashing import sha256_text
from rag_project.utils.text import estimate_tokens


PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class Chunker:
    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_section(self, section: Section) -> list[Chunk]:
        text = section.text.strip()
        if not text:
            return []

        units = self._semantic_units(text)
        boundaries_end = [unit["end"] for unit in units]
        boundaries_start = [unit["start"] for unit in units]

        chunks: list[Chunk] = []
        start = 0
        order = 0
        while start < len(text):
            target_end = min(len(text), start + self.chunk_size)
            boundary_index = bisect_right(boundaries_end, target_end) - 1
            if boundary_index >= 0 and boundaries_end[boundary_index] > start:
                end = boundaries_end[boundary_index]
                chunk_strategy = "semantic_boundary"
            else:
                end = target_end
                chunk_strategy = "char_window_fallback"

            raw_window = text[start:end]
            leading_trim = len(raw_window) - len(raw_window.lstrip())
            trailing_trim = len(raw_window) - len(raw_window.rstrip())
            trimmed_start = start + leading_trim
            trimmed_end = end - trailing_trim

            if trimmed_end > trimmed_start:
                window = text[trimmed_start:trimmed_end]
                section_path = section.metadata.get("section_path", [section.heading])
                metadata = {
                    "heading": section.heading,
                    "section_path": section_path,
                    "start_char": trimmed_start,
                    "end_char": trimmed_end,
                    "chunk_strategy": chunk_strategy,
                }
                if section.metadata.get("is_navigation") is True:
                    metadata["is_navigation"] = True
                chunks.append(
                    Chunk(
                        collection=section.collection,
                        chunk_id=sha256_text(f"{section.section_id}::{order}"),
                        section_id=section.section_id,
                        canonical_url=section.canonical_url,
                        order_in_section=order,
                        text=window,
                        token_estimate=estimate_tokens(window),
                        metadata=metadata,
                    )
                )
            if end >= len(text):
                break
            overlap_start = max(start + 1, end - self.chunk_overlap)
            start_boundary_index = bisect_left(boundaries_start, overlap_start)
            if start_boundary_index < len(boundaries_start):
                start = max(overlap_start, boundaries_start[start_boundary_index])
            else:
                start = overlap_start
            order += 1
        return chunks

    def _semantic_units(self, text: str) -> list[dict[str, int | str]]:
        paragraph_parts = [item.strip() for item in PARAGRAPH_SPLIT_RE.split(text) if item.strip()]
        if len(paragraph_parts) > 1:
            return self._parts_with_offsets(text, paragraph_parts)

        sentence_parts = [item.strip() for item in SENTENCE_SPLIT_RE.split(text) if item.strip()]
        if len(sentence_parts) > 1:
            return self._parts_with_offsets(text, sentence_parts)

        return [{"text": text, "start": 0, "end": len(text)}]

    @staticmethod
    def _parts_with_offsets(text: str, parts: list[str]) -> list[dict[str, int | str]]:
        units: list[dict[str, int | str]] = []
        search_from = 0
        for part in parts:
            start = text.find(part, search_from)
            if start < 0:
                continue
            end = start + len(part)
            units.append({"text": part, "start": start, "end": end})
            search_from = end
        return units or [{"text": text, "start": 0, "end": len(text)}]
