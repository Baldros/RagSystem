from __future__ import annotations

import re

from bs4 import BeautifulSoup


NAVIGATION_TERMS_RE = re.compile(
    r"\b(collapse\s+all|table\s+of\s+contents|toc|navigation|index|next|previous)\b",
    flags=re.IGNORECASE,
)


def classify_document(html: str, text_content: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "lxml")
    anchors = soup.select("a[href]")
    paragraphs = soup.select("p")
    headings = soup.select("h1, h2, h3, h4, h5, h6")
    list_items = soup.select("li")

    anchor_text_chars = sum(len(anchor.get_text(" ", strip=True)) for anchor in anchors)
    text_chars = max(1, len(text_content))
    link_density = anchor_text_chars / text_chars
    nav_term_hits = len(NAVIGATION_TERMS_RE.findall(text_content[:12000]))

    nav_score = 0.0
    if link_density >= 0.60:
        nav_score += 0.50
    elif link_density >= 0.40:
        nav_score += 0.30

    if len(paragraphs) <= 2:
        nav_score += 0.20
    elif len(paragraphs) <= 5:
        nav_score += 0.10

    if len(headings) <= 1:
        nav_score += 0.10

    if nav_term_hits > 0:
        nav_score += 0.30

    if len(list_items) > max(5, len(paragraphs) * 3):
        nav_score += 0.15

    nav_score = min(1.0, nav_score)
    doc_type = "navigation" if nav_score >= 0.55 else "content"
    quality_score = round(max(0.0, 1.0 - nav_score), 4)

    return {
        "doc_type": doc_type,
        "quality_score": quality_score,
        "navigation_score": round(nav_score, 4),
        "signals": {
            "link_density": round(link_density, 4),
            "paragraph_count": len(paragraphs),
            "heading_count": len(headings),
            "list_item_count": len(list_items),
            "navigation_term_hits": nav_term_hits,
        },
    }
