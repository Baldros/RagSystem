from __future__ import annotations

from bs4 import BeautifulSoup
import trafilatura

from rag_project.utils.text import normalize_whitespace


class ContentExtractor:
    def extract(self, html: str, url: str) -> tuple[str, str, str]:
        markdown = trafilatura.extract(
            html,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
        )
        text = trafilatura.extract(
            html,
            url=url,
            output_format="txt",
            include_comments=False,
            include_tables=True,
        )

        if not markdown or not text:
            soup = BeautifulSoup(html, "lxml")
            title = normalize_whitespace(soup.title.get_text(" ", strip=True) if soup.title else "")
            plain_text = normalize_whitespace(soup.get_text(" ", strip=True))
            return title, plain_text, plain_text

        soup = BeautifulSoup(html, "lxml")
        title = normalize_whitespace(soup.title.get_text(" ", strip=True) if soup.title else "")
        return title, normalize_whitespace(text), markdown.strip()
