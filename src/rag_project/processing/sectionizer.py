from __future__ import annotations

import re
from dataclasses import dataclass

from rag_project.models import Section
from rag_project.utils.hashing import sha256_text


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(slots=True)
class _HeadingState:
    level: int
    heading: str
    slug: str
    section_id: str
    emitted: bool


def split_markdown_into_sections(
    collection: str,
    canonical_url: str,
    markdown: str,
    min_section_length: int,
) -> list[Section]:
    matches = list(HEADING_RE.finditer(markdown))
    sections: list[Section] = []

    if not matches:
        text = markdown.strip()
        if len(text) >= min_section_length:
            sections.append(
                Section(
                    collection=collection,
                    section_id=sha256_text(f"{canonical_url}::root"),
                    canonical_url=canonical_url,
                    heading="Document",
                    level=1,
                    order_in_page=0,
                    text=text,
                    metadata={
                        "heading_markdown_level": 1,
                        "parent_section_id": None,
                        "section_path": ["Document"],
                        "section_slug_path": ["document"],
                    },
                )
            )
        return sections

    heading_stack: list[_HeadingState] = []

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()

        heading = match.group(2).strip()
        level = len(match.group(1))
        slug = _slugify(heading)
        section_id = sha256_text(f"{canonical_url}::{slug}::{index}")

        while heading_stack and heading_stack[-1].level >= level:
            heading_stack.pop()

        section_path = [item.heading for item in heading_stack] + [heading]
        section_slug_path = [item.slug for item in heading_stack] + [slug]
        parent_section_id = next(
            (item.section_id for item in reversed(heading_stack) if item.emitted),
            None,
        )
        emitted = len(body) >= min_section_length
        heading_stack.append(
            _HeadingState(
                level=level,
                heading=heading,
                slug=slug,
                section_id=section_id,
                emitted=emitted,
            )
        )

        if not emitted:
            continue

        sections.append(
            Section(
                collection=collection,
                section_id=section_id,
                canonical_url=canonical_url,
                heading=heading,
                level=level,
                order_in_page=index,
                text=body,
                metadata={
                    "heading_markdown_level": level,
                    "parent_section_id": parent_section_id,
                    "section_path": section_path,
                    "section_slug_path": section_slug_path,
                },
            )
        )

    return sections


def _slugify(value: str) -> str:
    normalized = SLUG_RE.sub("-", value.lower()).strip("-")
    return normalized or "section"
