from __future__ import annotations

from rag_project.config import EmbeddingSettings
from rag_project.embeddings.base import Embedder
from rag_project.embeddings.sentence_transformer_provider import SentenceTransformerEmbedder


def build_embedder(settings: EmbeddingSettings) -> Embedder:
    if settings.provider == "sentence_transformer":
        return SentenceTransformerEmbedder(
            settings.model_name,
            device=settings.device,
            batch_size=settings.batch_size,
        )
    raise ValueError(f"Unsupported embedding provider: {settings.provider}")
