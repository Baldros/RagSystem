from __future__ import annotations

import re

from rag_project.models import Section
from rag_project.utils.hashing import sha256_text


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


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
                )
            )
        return sections

    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        body = markdown[start:end].strip()
        if len(body) < min_section_length:
            continue

        heading = match.group(2).strip()
        level = len(match.group(1))
        sections.append(
            Section(
                collection=collection,
                section_id=sha256_text(f"{canonical_url}::{heading}::{index}"),
                canonical_url=canonical_url,
                heading=heading,
                level=level,
                order_in_page=index,
                text=body,
                metadata={"heading_markdown_level": level},
            )
        )

    return sections
