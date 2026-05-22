from __future__ import annotations

from dataclasses import dataclass

from rag_project.config import build_config
from rag_project.discovery.service import DiscoveryService
from rag_project.fetching.http_client import HttpClient


class _AllowAllRobotsParser:
    def can_fetch(self, user_agent: str, url: str) -> bool:
        del user_agent, url
        return True


@dataclass(slots=True)
class _FakeResponse:
    url: str
    status_code: int
    text: str
    headers: dict


class _FakeDiscoveryHttpClient:
    def __init__(self, toc_graph: dict[str, list[str]]) -> None:
        self.toc_graph = toc_graph

    def extract_toc_entries(self, url: str, css_selectors: list[str]) -> list[dict]:
        del css_selectors
        return [
            {"url": child_url, "text": child_url.rsplit("/", 1)[-1], "level": 1, "order": index}
            for index, child_url in enumerate(self.toc_graph.get(url, []))
        ]

    def get(self, url: str):
        return _FakeResponse(
            url=url,
            status_code=200,
            text=f"<html><body>{url}</body></html>",
            headers={},
        )


class _FakeDriver:
    def __init__(self, url: str) -> None:
        self.current_url = url


class _SpyHttpClient(HttpClient):
    def __init__(self) -> None:
        super().__init__(user_agent="tests", timeout_seconds=1)
        self.prepare_calls = 0

    def _prepare_page(self, url: str):  # type: ignore[override]
        self.prepare_calls += 1
        return _FakeDriver(url)

    def _capture_rendered_html(self, driver) -> str:  # type: ignore[override]
        return f"<html>{driver.current_url}</html>"

    def _collect_toc_entries_from_dom(self, driver, css_selectors: list[str]) -> list[dict]:  # type: ignore[override]
        del css_selectors
        return [{"url": f"{driver.current_url}/child", "text": "child", "level": 1, "order": 0}]


def _patch_discovery_sources(monkeypatch) -> None:
    monkeypatch.setattr(
        "rag_project.discovery.service.build_robot_parser",
        lambda root_url, user_agent, timeout_seconds: (_AllowAllRobotsParser(), []),
    )
    monkeypatch.setattr(
        "rag_project.discovery.service.fetch_sitemap_urls",
        lambda sitemap_urls, timeout_seconds, user_agent: [],
    )


def test_discover_treats_zero_max_pages_as_unlimited(monkeypatch) -> None:
    _patch_discovery_sources(monkeypatch)
    toc_graph = {
        "https://docs.example.com/manual/": [
            "https://docs.example.com/manual/page-a",
            "https://docs.example.com/manual/page-b",
        ],
        "https://docs.example.com/manual/page-a": ["https://docs.example.com/manual/page-c"],
        "https://docs.example.com/manual/page-b": [],
        "https://docs.example.com/manual/page-c": [],
    }
    service = DiscoveryService(
        config=build_config(root_url="https://docs.example.com/manual/", max_pages=0),
        http_client=_FakeDiscoveryHttpClient(toc_graph),
    )

    result = service.discover()
    records = result.records

    assert len(records) == 4
    assert {record.canonical_url for record in records} == {
        "https://docs.example.com/manual",
        "https://docs.example.com/manual/page-a",
        "https://docs.example.com/manual/page-b",
        "https://docs.example.com/manual/page-c",
    }
    assert result.stopped_reason == "completed"


def test_discover_still_respects_positive_max_pages(monkeypatch) -> None:
    _patch_discovery_sources(monkeypatch)
    toc_graph = {
        "https://docs.example.com/manual/": [
            "https://docs.example.com/manual/page-a",
            "https://docs.example.com/manual/page-b",
        ],
        "https://docs.example.com/manual/page-a": ["https://docs.example.com/manual/page-c"],
        "https://docs.example.com/manual/page-b": [],
    }
    service = DiscoveryService(
        config=build_config(root_url="https://docs.example.com/manual/", max_pages=2),
        http_client=_FakeDiscoveryHttpClient(toc_graph),
    )

    result = service.discover()
    records = result.records

    assert len(records) == 2
    assert [record.canonical_url for record in records] == [
        "https://docs.example.com/manual",
        "https://docs.example.com/manual/page-a",
    ]
    assert result.stopped_reason == "guard_rail_max_pages"


def test_discover_respects_max_depth_without_enqueuing_deeper_levels(monkeypatch) -> None:
    _patch_discovery_sources(monkeypatch)
    toc_graph = {
        "https://docs.example.com/manual/": [
            "https://docs.example.com/manual/page-a",
            "https://docs.example.com/manual/page-b",
        ],
        "https://docs.example.com/manual/page-a": ["https://docs.example.com/manual/page-c"],
        "https://docs.example.com/manual/page-b": [],
    }
    service = DiscoveryService(
        config=build_config(root_url="https://docs.example.com/manual/", max_pages=0, max_depth=0),
        http_client=_FakeDiscoveryHttpClient(toc_graph),
    )

    result = service.discover()

    assert [record.canonical_url for record in result.records] == ["https://docs.example.com/manual"]
    assert result.stopped_reason == "completed"


def test_extract_toc_entries_primes_response_cache() -> None:
    client = _SpyHttpClient()
    url = "https://docs.example.com/manual/page-a"

    entries = client.extract_toc_entries(url, ["nav"])
    response = client.get(url)

    assert client.prepare_calls == 1
    assert response.url == url
    assert response.text == "<html>https://docs.example.com/manual/page-a</html>"
    assert entries == [{"url": "https://docs.example.com/manual/page-a/child", "text": "child", "level": 1, "order": 0}]
