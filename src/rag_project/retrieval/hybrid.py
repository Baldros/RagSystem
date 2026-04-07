from __future__ import annotations

from datetime import datetime

from rag_project.config import RetrievalSettings
from rag_project.models import RetrievalTrace
from rag_project.retrieval.rrf import reciprocal_rank_fusion


class HybridRetriever:
    def __init__(self, repository, embedder, settings: RetrievalSettings) -> None:
        self.repository = repository
        self.embedder = embedder
        self.settings = settings

    def search(self, collection: str, query: str) -> RetrievalTrace:
        lexical_hits = self.repository.lexical_search(collection, query, self.settings.lexical_limit)
        query_embedding = self.embedder.embed_query(query)
        vector_hits = self.repository.vector_search(collection, query_embedding, self.settings.vector_limit)
        fused_hits = reciprocal_rank_fusion(
            rank_lists=[lexical_hits, vector_hits],
            k=self.settings.rrf_k,
            limit=self.settings.fused_limit,
        )
        trace = RetrievalTrace(
            collection=collection,
            query=query,
            lexical_hits=lexical_hits,
            vector_hits=vector_hits,
            fused_hits=fused_hits,
            created_at=datetime.utcnow(),
        )
        self.repository.insert_retrieval_trace(trace)
        return trace
