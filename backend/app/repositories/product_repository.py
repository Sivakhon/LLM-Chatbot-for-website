"""Vector-store backed product repository (ChromaDB)."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.api.types import Documents, EmbeddingFunction

from app.core.errors import VectorStoreError
from app.domain.chat import ProductFilters, ScoredProduct
from app.domain.product import Product
from app.embeddings import default_embedding_function

logger = logging.getLogger(__name__)

_BATCH_SIZE = 100


def build_where(filters: ProductFilters | None) -> dict[str, Any] | None:
    """Translate API filters to a Chroma `where` clause."""
    if filters is None:
        return None
    clauses: list[dict[str, Any]] = []
    if filters.gender == "unisex":
        clauses.append({"gender": "unisex"})
    elif filters.gender:
        # A unisex product matches both men and women searches.
        clauses.append({"gender": {"$in": [filters.gender, "unisex"]}})
    if filters.product_types:
        clauses.append({"product_type": {"$in": list(filters.product_types)}})
    if filters.min_price is not None:
        clauses.append({"price": {"$gte": filters.min_price}})
    if filters.max_price is not None:
        clauses.append({"price": {"$lte": filters.max_price}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


class ProductRepository:
    def __init__(
        self,
        client: ClientAPI,
        collection_name: str,
        embedding_function: EmbeddingFunction[Documents] | None = None,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._embedding_function = embedding_function or default_embedding_function()
        self._collection = self._get_collection()

    def _get_collection(self) -> Collection:
        return self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._embedding_function,  # type: ignore[arg-type]
            metadata={"hnsw:space": "cosine"},
        )

    # -- writes ---------------------------------------------------------------
    def upsert(self, products: Iterable[Product]) -> int:
        items = list(products)
        for start in range(0, len(items), _BATCH_SIZE):
            batch = items[start : start + _BATCH_SIZE]
            self._collection.upsert(
                ids=[p.sku for p in batch],
                documents=[p.to_document() for p in batch],
                metadatas=[p.to_metadata() for p in batch],
            )
        logger.info("Upserted %d products into '%s'", len(items), self._collection_name)
        return len(items)

    def reset(self) -> None:
        """Drop and recreate the collection (used by full re-ingestion)."""
        self._client.delete_collection(self._collection_name)
        self._collection = self._get_collection()

    # -- reads ----------------------------------------------------------------
    def count(self) -> int:
        try:
            return self._collection.count()
        except Exception as exc:  # chroma raises a variety of transport errors
            raise VectorStoreError(f"Vector store unreachable: {exc}") from exc

    def get(self, sku: str) -> Product | None:
        res = self._collection.get(ids=[sku], include=["metadatas"])
        metas = res.get("metadatas") or []
        return Product.from_metadata(metas[0]) if metas else None  # type: ignore[arg-type]

    def find(
        self, filters: ProductFilters | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[Product], int]:
        where = build_where(filters)
        res = self._collection.get(where=where, include=["metadatas"])
        products = sorted(
            (Product.from_metadata(m) for m in res.get("metadatas") or []),  # type: ignore[arg-type]
            key=lambda p: (p.name.lower(), p.sku),
        )
        return products[offset : offset + limit], len(products)

    def search(
        self, query: str, k: int = 5, filters: ProductFilters | None = None
    ) -> list[ScoredProduct]:
        """Semantic search. Results are de-duplicated by product name, because the
        listing exposes variants of one product as separate cards."""
        total = self.count()
        if total == 0:
            return []
        try:
            res = self._collection.query(
                query_texts=[query],
                n_results=min(k * 3, total),  # over-fetch to survive de-duplication
                where=build_where(filters),
                include=["metadatas", "distances"],
            )
        except Exception as exc:
            raise VectorStoreError(f"Vector search failed: {exc}") from exc

        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        results: list[ScoredProduct] = []
        seen_names: set[str] = set()
        for meta, dist in zip(metas, dists, strict=True):
            product = Product.from_metadata(meta)  # type: ignore[arg-type]
            key = product.name.casefold()
            if key in seen_names:
                continue
            seen_names.add(key)
            # cosine distance is in [0, 2]; map it to a [0, 1] similarity
            results.append(ScoredProduct(product=product, score=round(1 - dist / 2, 4)))
            if len(results) == k:
                break
        return results
