from __future__ import annotations

from rag_project.reporting.coverage import build_coverage_report


def test_coverage_report_includes_operational_breakdown() -> None:
    inventory = [
        {"canonical_url": "https://docs.example.com/root", "source": "seed", "depth": 0, "metadata": {}},
        {
            "canonical_url": "https://docs.example.com/root/topic-a",
            "source": "toc",
            "depth": 1,
            "metadata": {"parent_canonical_url": "https://docs.example.com/root"},
        },
        {
            "canonical_url": "https://docs.example.com/root/topic-b",
            "source": "toc",
            "depth": 1,
            "metadata": {"parent_canonical_url": "https://docs.example.com/root"},
        },
    ]
    documents = [
        {
            "canonical_url": "https://docs.example.com/root",
            "metadata": {"doc_type": "content", "indexed_for_retrieval": True},
        },
        {
            "canonical_url": "https://docs.example.com/root/topic-a",
            "metadata": {"doc_type": "navigation", "indexed_for_retrieval": False},
        },
    ]
    skipped = [
        {
            "canonical_url": "https://docs.example.com/root/topic-b",
            "source": "toc",
            "depth": 1,
            "reason": "outside_scope",
            "metadata": {"parent_canonical_url": "https://docs.example.com/root"},
        }
    ]

    report = build_coverage_report(
        inventory=inventory,
        documents=documents,
        skipped=skipped,
        stopped_reason="completed",
    )

    assert report["content_url_count"] == 1
    assert report["navigation_url_count"] == 1
    assert report["indexed_content_url_count"] == 1
    assert report["seed_toc_level1_total"] == 2
    assert report["seed_toc_level1_processed"] == 1
    assert report["seed_toc_level1_rejected_by_reason"] == {"outside_scope": 1}
