from __future__ import annotations

from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests


def build_robot_parser(root_url: str, user_agent: str, timeout_seconds: int) -> tuple[RobotFileParser, list[str]]:
    parsed = urlparse(root_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    sitemap_urls: list[str] = []

    try:
        response = requests.get(robots_url, timeout=timeout_seconds, headers={"User-Agent": user_agent})
        if response.ok:
            parser.parse(response.text.splitlines())
            for line in response.text.splitlines():
                if line.lower().startswith("sitemap:"):
                    sitemap_urls.append(line.split(":", 1)[1].strip())
    except requests.RequestException:
        parser.parse([])

    if not sitemap_urls:
        sitemap_urls.extend(
            [
                urljoin(root_url, "/sitemap.xml"),
                urljoin(root_url, "/sitemap_index.xml"),
            ]
        )

    return parser, sitemap_urls
