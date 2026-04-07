from __future__ import annotations

from rag_project.models import RetrievalHit


def reciprocal_rank_fusion(rank_lists: list[list[RetrievalHit]], k: int, limit: int) -> list[RetrievalHit]:
    scores: dict[str, float] = {}
    hits_by_id: dict[str, RetrievalHit] = {}

    for rank_list in rank_lists:
        for rank, hit in enumerate(rank_list, start=1):
            scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + (1.0 / (k + rank))
            hits_by_id.setdefault(hit.chunk_id, hit)

    fused = []
    for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:limit]:
        hit = hits_by_id[chunk_id]
        fused.append(
            RetrievalHit(
                collection=hit.collection,
                chunk_id=hit.chunk_id,
                canonical_url=hit.canonical_url,
                section_id=hit.section_id,
                score=score,
                source="rrf",
                text=hit.text,
                metadata=hit.metadata,
            )
        )
    return fused
