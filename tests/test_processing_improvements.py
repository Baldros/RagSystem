from __future__ import annotations

from rag_project.models import Section
from rag_project.processing.chunker import Chunker
from rag_project.processing.document_classifier import classify_document
from rag_project.processing.sectionizer import split_markdown_into_sections


def test_document_classifier_detects_navigation_pages() -> None:
    html = """
    <html>
      <body>
        <nav>
          <a href="/a">Intro</a>
          <a href="/b">Install</a>
          <a href="/c">API</a>
          <a href="/d">CLI</a>
          <a href="/e">FAQ</a>
        </nav>
        <ul><li>Item</li><li>Item</li><li>Item</li><li>Item</li><li>Item</li><li>Item</li></ul>
      </body>
    </html>
    """
    text = "Collapse all table of contents intro install api cli faq"

    result = classify_document(html=html, text_content=text)

    assert result["doc_type"] == "navigation"
    assert float(result["navigation_score"]) >= 0.55


def test_sectionizer_preserves_section_hierarchy_metadata() -> None:
    markdown = """
# Root Topic
Root body text with enough characters to pass threshold.

## Child Topic
Child body text with enough characters to pass threshold.

### Leaf Topic
Leaf body text with enough characters to pass threshold.
""".strip()

    sections = split_markdown_into_sections(
        collection="docs",
        canonical_url="https://docs.example.com/page",
        markdown=markdown,
        min_section_length=10,
    )

    assert [section.heading for section in sections] == ["Root Topic", "Child Topic", "Leaf Topic"]
    assert sections[0].metadata["section_path"] == ["Root Topic"]
    assert sections[1].metadata["section_path"] == ["Root Topic", "Child Topic"]
    assert sections[2].metadata["section_path"] == ["Root Topic", "Child Topic", "Leaf Topic"]
    assert sections[0].metadata["parent_section_id"] is None
    assert sections[1].metadata["parent_section_id"] == sections[0].section_id
    assert sections[2].metadata["parent_section_id"] == sections[1].section_id


def test_chunker_emits_offsets_and_strategy_metadata() -> None:
    section = Section(
        collection="docs",
        section_id="section-1",
        canonical_url="https://docs.example.com/page",
        heading="Child Topic",
        level=2,
        order_in_page=0,
        text="Sentence one. Sentence two. Sentence three. Sentence four.",
        metadata={"section_path": ["Root Topic", "Child Topic"]},
    )
    chunker = Chunker(chunk_size=24, chunk_overlap=8)

    chunks = chunker.chunk_section(section)

    assert len(chunks) >= 2
    for chunk in chunks:
        assert chunk.metadata["section_path"] == ["Root Topic", "Child Topic"]
        assert chunk.metadata["start_char"] < chunk.metadata["end_char"]
        assert chunk.metadata["chunk_strategy"] in {"semantic_boundary", "char_window_fallback"}
