from __future__ import annotations

from collections import Counter


def build_coverage_report(
    inventory: list[dict],
    documents: list[dict],
    skipped: list[dict] | None = None,
    stopped_reason: str = "completed",
) -> dict:
    skipped = skipped or []
    expected_urls = {item["canonical_url"] for item in inventory}
    crawled_urls = {item["canonical_url"] for item in documents}

    missing_urls = sorted(expected_urls - crawled_urls)
    orphan_urls = sorted(crawled_urls - expected_urls)
    coverage_ratio = (len(crawled_urls & expected_urls) / len(expected_urls)) if expected_urls else 0.0
    source_distribution = Counter(item.get("source", "unknown") for item in inventory)
    depth_distribution = Counter(str(item.get("depth", "unknown")) for item in inventory)
    skipped_by_reason = Counter(item.get("reason", "unknown") for item in skipped)

    navigation_documents = [item for item in documents if _doc_type(item) == "navigation"]
    content_documents = [item for item in documents if _doc_type(item) != "navigation"]
    indexed_content_documents = [
        item
        for item in content_documents
        if bool((item.get("metadata") or {}).get("indexed_for_retrieval", False))
    ]
    seed_urls = {item["canonical_url"] for item in inventory if item.get("source") == "seed"}
    level1_inventory = [
        item
        for item in inventory
        if item.get("source") == "toc"
        and item.get("depth") == 1
        and _parent_url(item) in seed_urls
    ]
    level1_rejected = [
        item
        for item in skipped
        if item.get("source") == "toc"
        and item.get("depth") == 1
        and _parent_url(item) in seed_urls
    ]
    level1_urls = {item["canonical_url"] for item in level1_inventory} | {
        item["canonical_url"] for item in level1_rejected
    }
    level1_processed_count = len(level1_urls & crawled_urls)
    level1_rejected_by_reason = Counter()
    for item in level1_rejected:
        if item["canonical_url"] in crawled_urls:
            continue
        level1_rejected_by_reason[item.get("reason", "unknown")] += 1

    return {
        "expected_url_count": len(expected_urls),
        "crawled_url_count": len(crawled_urls),
        "coverage_ratio": coverage_ratio,
        "missing_urls": missing_urls,
        "orphan_urls": orphan_urls,
        "stopped_reason": stopped_reason,
        "discovered_url_count": len(inventory),
        "content_url_count": len(content_documents),
        "indexed_content_url_count": len(indexed_content_documents),
        "navigation_url_count": len(navigation_documents),
        "source_distribution": dict(sorted(source_distribution.items())),
        "depth_distribution": dict(sorted(depth_distribution.items(), key=lambda item: item[0])),
        "skipped_url_count": len(skipped),
        "skipped_by_reason": dict(sorted(skipped_by_reason.items())),
        "seed_toc_level1_total": len(level1_urls),
        "seed_toc_level1_processed": level1_processed_count,
        "seed_toc_level1_rejected_by_reason": dict(
            sorted(level1_rejected_by_reason.items())
        ),
    }


def _doc_type(document: dict) -> str:
    metadata = document.get("metadata") or {}
    return str(metadata.get("doc_type", "content"))


def _parent_url(item: dict) -> str | None:
    metadata = item.get("metadata") or {}
    return metadata.get("parent_canonical_url") or item.get("discovered_from")
