from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class DataPaths:
    root: Path
    inventory_jsonl: Path
    skipped_urls_jsonl: Path
    discovered_nodes_jsonl: Path
    link_tree_json: Path
    discovery_report_json: Path
    raw_documents_jsonl: Path
    sections_jsonl: Path
    chunks_jsonl: Path
    coverage_report_json: Path


def build_data_paths(data_dir: Path) -> DataPaths:
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"
    return DataPaths(
        root=data_dir,
        inventory_jsonl=raw_dir / "inventory.jsonl",
        skipped_urls_jsonl=raw_dir / "skipped_urls.jsonl",
        discovered_nodes_jsonl=raw_dir / "discovered_nodes.jsonl",
        link_tree_json=raw_dir / "link_tree.json",
        discovery_report_json=processed_dir / "discovery_report.json",
        raw_documents_jsonl=raw_dir / "documents.jsonl",
        sections_jsonl=processed_dir / "sections.jsonl",
        chunks_jsonl=processed_dir / "chunks.jsonl",
        coverage_report_json=processed_dir / "coverage_report.json",
    )
