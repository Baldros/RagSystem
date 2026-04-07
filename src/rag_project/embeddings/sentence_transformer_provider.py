from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

from rag_project.embeddings.base import Embedder
from rag_project.embeddings.device import resolve_device


LOGGER = logging.getLogger(__name__)


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str, *, device: str = "auto", batch_size: int = 32) -> None:
        self.device = resolve_device(device)
        self.batch_size = batch_size
        LOGGER.info("loading embedding model %s on device %s", model_name, self.device)
        self.model = SentenceTransformer(model_name, device=self.device)

    def embed_texts(self, texts: list[str], *, show_progress: bool = True) -> list[list[float]]:
        return self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
            batch_size=self.batch_size,
        ).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode([text], normalize_embeddings=True, batch_size=1)[0].tolist()
