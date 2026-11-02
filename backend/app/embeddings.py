"""Embedding function used by the vector store.

Defaults to Chroma's built-in ONNX `all-MiniLM-L6-v2`, the same model the original
notebook loaded via sentence-transformers, without pulling PyTorch into the image.
"""

from chromadb.api.types import Documents, EmbeddingFunction
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction


def default_embedding_function() -> EmbeddingFunction[Documents]:
    return DefaultEmbeddingFunction()
