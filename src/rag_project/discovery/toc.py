from __future__ import annotations

from bs4 import BeautifulSoup

from rag_project.utils.text import normalize_whitespace
from rag_project.utils.url import absolutize


def extract_toc_links(html: str, base_url: str, css_selectors: list[str]) -> list[str]:
    return [entry["url"] for entry in extract_toc_entries(html, base_url, css_selectors)]


def extract_toc_entries(html: str, base_url: str, css_selectors: list[str]) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    entries_by_url: dict[str, dict] = {}
    order = 0

    for selector in css_selectors:
        for node in soup.select(selector):
            for anchor in node.select("a[href]"):
                href = anchor.get("href")
                if href:
                    absolute_url = absolutize(base_url, href)
                    if absolute_url in entries_by_url:
                        continue
                    entries_by_url[absolute_url] = {
                        "url": absolute_url,
                        "text": normalize_whitespace(anchor.get_text(" ", strip=True)),
                        "level": _anchor_depth(anchor, stop_node=node),
                        "order": order,
                    }
                    order += 1

    return sorted(entries_by_url.values(), key=lambda item: item["order"])


def _anchor_depth(anchor, stop_node) -> int:
    depth = 1
    current = anchor.parent
    while current and current is not stop_node:
        if getattr(current, "name", None) in {"dl", "ul", "ol"}:
            depth += 1
        current = current.parent
    return depth
