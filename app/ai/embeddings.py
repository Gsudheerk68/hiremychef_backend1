"""Sentence embeddings for semantic chef matching."""
from functools import lru_cache

import numpy as np

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def encode(texts: list[str]) -> np.ndarray:
    """Unit-length vectors, so a dot product equals cosine similarity."""
    vecs = _model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def similarity(query_vecs: np.ndarray, chef_vecs: np.ndarray) -> np.ndarray:
    return query_vecs @ chef_vecs.T
