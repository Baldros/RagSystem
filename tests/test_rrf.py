from rag_project.models import RetrievalHit
from rag_project.retrieval.rrf import reciprocal_rank_fusion


def _hit(chunk_id: str, score: float, source: str) -> RetrievalHit:
    return RetrievalHit(
        collection="test-collection",
        chunk_id=chunk_id,
        canonical_url="https://docs.example.com/x",
        section_id="section-1",
        score=score,
        source=source,
        text="text",
    )


def test_rrf_prefers_documents_present_in_multiple_lists() -> None:
    lexical = [_hit("a", 0.9, "lexical"), _hit("b", 0.8, "lexical")]
    vector = [_hit("b", 0.95, "vector"), _hit("c", 0.7, "vector")]

    fused = reciprocal_rank_fusion([lexical, vector], k=60, limit=3)

    assert fused[0].chunk_id == "b"
