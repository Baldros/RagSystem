from __future__ import annotations


def build_coverage_report(inventory: list[dict], documents: list[dict]) -> dict:
    expected_urls = {item["canonical_url"] for item in inventory}
    crawled_urls = {item["canonical_url"] for item in documents}

    missing_urls = sorted(expected_urls - crawled_urls)
    orphan_urls = sorted(crawled_urls - expected_urls)
    coverage_ratio = (len(crawled_urls & expected_urls) / len(expected_urls)) if expected_urls else 0.0

    return {
        "expected_url_count": len(expected_urls),
        "crawled_url_count": len(crawled_urls),
        "coverage_ratio": coverage_ratio,
        "missing_urls": missing_urls,
        "orphan_urls": orphan_urls,
    }
