from __future__ import annotations

from collections import deque
import time
from urllib.parse import unquote, urlparse

from rag_project.config import AppConfig
from rag_project.discovery.robots import build_robot_parser
from rag_project.discovery.sitemap import fetch_sitemap_urls
from rag_project.discovery.toc import extract_toc_entries
from rag_project.fetching.http_client import HttpClient
from rag_project.models import DiscoveryResult, DiscoverySkip, UrlRecord
from rag_project.utils.url import canonicalize_url, extract_effective_path, same_domain


class DiscoveryService:
    def __init__(self, config: AppConfig, http_client: HttpClient) -> None:
        self.config = config
        self.http_client = http_client

    def discover(self) -> DiscoveryResult:
        started_at = time.monotonic()
        seen: set[str] = set()
        records: list[UrlRecord] = []
        skipped: list[DiscoverySkip] = []
        queue = deque((url, "seed", 0, None, {}) for url in self.config.discovery.start_urls)
        max_pages = self.config.discovery.max_pages
        unlimited_pages = max_pages <= 0
        max_depth = self.config.discovery.max_depth
        unlimited_depth = max_depth < 0
        max_runtime_seconds = self.config.discovery.max_runtime_minutes * 60 if self.config.discovery.max_runtime_minutes > 0 else 0
        max_failures = self.config.discovery.max_failures
        max_total_bytes = self.config.discovery.max_total_bytes
        failure_count = 0
        total_bytes = 0
        stopped_reason = "completed"

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
                else:
                    skipped.append(
                        self._build_skip(
                            url=url,
                            source="sitemap",
                            depth=0,
                            reason="blocked_by_robots",
                        )
                    )

        while queue:
            if max_runtime_seconds and (time.monotonic() - started_at) >= max_runtime_seconds:
                stopped_reason = "guard_rail_runtime"
                break
            if max_failures > 0 and failure_count >= max_failures:
                stopped_reason = "guard_rail_failures"
                break
            if max_total_bytes > 0 and total_bytes >= max_total_bytes:
                stopped_reason = "guard_rail_total_bytes"
                break
            if not unlimited_pages and len(records) >= max_pages:
                stopped_reason = "guard_rail_max_pages"
                break

            url, source, depth, discovered_from, metadata = queue.popleft()
            canonical = canonicalize_url(url)
            if canonical in seen:
                skipped.append(
                    self._build_skip(
                        url=url,
                        source=source,
                        depth=depth,
                        reason="duplicate",
                        discovered_from=discovered_from,
                        metadata=metadata,
                    )
                )
                continue

            # Seed URLs should always be allowed to start discovery.
            if source != "seed":
                allowed, reason = self._allowance_status(canonical)
                if not allowed:
                    skipped.append(
                        self._build_skip(
                            url=url,
                            source=source,
                            depth=depth,
                            reason=reason,
                            discovered_from=discovered_from,
                            metadata=metadata,
                        )
                    )
                    continue

            try:
                response = self.http_client.get(url)
                total_bytes += len(response.text.encode("utf-8", errors="ignore"))
            except Exception as exc:
                failure_count += 1
                skipped.append(
                    self._build_skip(
                        url=url,
                        source=source,
                        depth=depth,
                        reason="fetch_error",
                        discovered_from=discovered_from,
                        metadata={**metadata, "error": str(exc)[:200]},
                    )
                )
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

            if not unlimited_depth and depth >= max_depth:
                continue

            try:
                toc_entries = self.http_client.extract_toc_entries(url, self.config.discovery.toc_css_selectors)
            except Exception:
                try:
                    toc_entries = extract_toc_entries(
                        html=response.text,
                        base_url=response.url,
                        css_selectors=self.config.discovery.toc_css_selectors,
                    )
                except Exception:
                    failure_count += 1
                    skipped.append(
                        self._build_skip(
                            url=url,
                            source=source,
                            depth=depth,
                            reason="toc_extraction_error",
                            discovered_from=discovered_from,
                            metadata=metadata,
                        )
                    )
                    continue
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

        if stopped_reason != "completed":
            remaining: set[str] = set()
            for url, source, depth, discovered_from, metadata in queue:
                canonical = canonicalize_url(url)
                if canonical in remaining:
                    continue
                remaining.add(canonical)
                skipped.append(
                    self._build_skip(
                        url=url,
                        source=source,
                        depth=depth,
                        reason=stopped_reason,
                        discovered_from=discovered_from,
                        metadata=metadata,
                    )
                )

        return DiscoveryResult(
            records=records,
            skipped=skipped,
            stopped_reason=stopped_reason,
            total_bytes=total_bytes,
            failure_count=failure_count,
        )

    def _allowance_status(self, url: str) -> tuple[bool, str]:
        decoded_url = unquote(url)
        parsed = urlparse(decoded_url)
        if parsed.scheme not in {"http", "https"}:
            return False, "invalid_scheme"
        if not same_domain(decoded_url, self.config.discovery.allowed_domains):
            return False, "outside_domain"
        if self.config.discovery.allowed_path_prefixes:
            effective_path = (extract_effective_path(decoded_url) or "/").rstrip("/") or "/"
            if not any(self._path_matches_prefix(effective_path, prefix) for prefix in self.config.discovery.allowed_path_prefixes):
                return False, "outside_scope"
        if self.config.discovery.include_url_patterns and not any(
            pattern in decoded_url for pattern in self.config.discovery.include_url_patterns
        ):
            return False, "not_matching_include_pattern"
        if any(pattern in decoded_url for pattern in self.config.discovery.exclude_url_patterns):
            return False, "excluded_pattern"
        return True, "allowed"

    @staticmethod
    def _path_matches_prefix(path: str, prefix: str) -> bool:
        normalized_prefix = (prefix or "/").rstrip("/") or "/"
        if normalized_prefix == "/":
            return True
        return path == normalized_prefix or path.startswith(f"{normalized_prefix}/")

    @staticmethod
    def _build_skip(
        *,
        url: str,
        source: str,
        depth: int,
        reason: str,
        discovered_from: str | None = None,
        metadata: dict | None = None,
    ) -> DiscoverySkip:
        return DiscoverySkip(
            url=url,
            canonical_url=canonicalize_url(url),
            source=source,
            depth=depth,
            reason=reason,
            discovered_from=discovered_from,
            metadata=dict(metadata or {}),
        )

    @staticmethod
    def _extract_doc_version(url: str) -> str | None:
        parts = [part for part in extract_effective_path(url).split("/") if part]
        for part in parts:
            lowered = part.lower()
            if lowered.startswith("v") and any(char.isdigit() for char in lowered):
                return part
        return None
