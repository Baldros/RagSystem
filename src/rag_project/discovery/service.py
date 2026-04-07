from __future__ import annotations

from collections import deque
from urllib.parse import unquote, urlparse

from rag_project.config import AppConfig
from rag_project.discovery.robots import build_robot_parser
from rag_project.discovery.sitemap import fetch_sitemap_urls
from rag_project.discovery.toc import extract_toc_entries
from rag_project.fetching.http_client import HttpClient
from rag_project.models import UrlRecord
from rag_project.utils.url import canonicalize_url, same_domain


class DiscoveryService:
    def __init__(self, config: AppConfig, http_client: HttpClient) -> None:
        self.config = config
        self.http_client = http_client

    def discover(self) -> list[UrlRecord]:
        seen: set[str] = set()
        records: list[UrlRecord] = []
        queue = deque((url, "seed", 0, None, {}) for url in self.config.discovery.start_urls)

        for root_url in self.config.discovery.start_urls:
            parser, robots_sitemaps = build_robot_parser(
                root_url=root_url,
                user_agent=self.config.fetching.user_agent,
                timeout_seconds=self.config.fetching.request_timeout_seconds,
            )
            sitemap_urls = list(dict.fromkeys(self.config.discovery.sitemap_urls + robots_sitemaps))
            for url in fetch_sitemap_urls(
                sitemap_urls=sitemap_urls,
                timeout_seconds=self.config.fetching.request_timeout_seconds,
                user_agent=self.config.fetching.user_agent,
            ):
                if parser.can_fetch(self.config.fetching.user_agent, url):
                    queue.append((url, "sitemap", 0, None, {}))

        while queue and len(records) < self.config.discovery.max_pages:
            url, source, depth, discovered_from, metadata = queue.popleft()
            canonical = canonicalize_url(url)
            if canonical in seen:
                continue
            
            # Seed URLs should always be allowed to start the discovery
            if source != "seed" and not self._is_allowed(canonical):
                continue

            seen.add(canonical)
            records.append(
                UrlRecord(
                    collection=self.config.project.collection,
                    url=url,
                    canonical_url=canonical,
                    source=source,
                    depth=depth,
                    discovered_from=discovered_from,
                    doc_version=self._extract_doc_version(canonical),
                    metadata=metadata,
                )
            )

            if depth > 2:
                continue

            try:
                toc_entries = self.http_client.extract_toc_entries(url, self.config.discovery.toc_css_selectors)
            except Exception:
                try:
                    response = self.http_client.get(url)
                except Exception:
                    continue
                toc_entries = extract_toc_entries(
                    html=response.text,
                    base_url=response.url,
                    css_selectors=self.config.discovery.toc_css_selectors,
                )
            for entry in toc_entries:
                queue.append(
                    (
                        entry["url"],
                        "toc",
                        depth + 1,
                        canonical,
                        {
                            "parent_canonical_url": canonical,
                            "link_text": entry["text"],
                            "toc_level": entry["level"],
                            "toc_order": entry["order"],
                        },
                    )
                )

        return records

    def _is_allowed(self, url: str) -> bool:
        decoded_url = unquote(url)
        if not same_domain(decoded_url, self.config.discovery.allowed_domains):
            return False
        if self.config.discovery.include_url_patterns and not any(
            pattern in decoded_url for pattern in self.config.discovery.include_url_patterns
        ):
            return False
        if any(pattern in decoded_url for pattern in self.config.discovery.exclude_url_patterns):
            return False
        parsed = urlparse(decoded_url)
        return parsed.scheme in {"http", "https"}

    @staticmethod
    def _extract_doc_version(url: str) -> str | None:
        parts = [part for part in urlparse(url).path.split("/") if part]
        for part in parts:
            lowered = part.lower()
            if lowered.startswith("v") and any(char.isdigit() for char in lowered):
                return part
        return None
