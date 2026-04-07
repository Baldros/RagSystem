from __future__ import annotations

from collections import deque
from xml.etree import ElementTree

import requests


def fetch_sitemap_urls(sitemap_urls: list[str], timeout_seconds: int, user_agent: str) -> list[str]:
    discovered: set[str] = set()
    queue = deque(sitemap_urls)
    headers = {"User-Agent": user_agent}

    while queue:
        sitemap_url = queue.popleft()
        try:
            response = requests.get(sitemap_url, timeout=timeout_seconds, headers=headers)
            response.raise_for_status()
        except requests.RequestException:
            continue

        try:
            root = ElementTree.fromstring(response.text)
        except ElementTree.ParseError:
            continue

        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        tag_name = root.tag.rsplit("}", 1)[-1]

        if tag_name == "sitemapindex":
            for node in root.findall("sm:sitemap/sm:loc", ns):
                if node.text:
                    queue.append(node.text.strip())
            continue

        if tag_name == "urlset":
            for node in root.findall("sm:url/sm:loc", ns):
                if node.text:
                    discovered.add(node.text.strip())

    return sorted(discovered)
