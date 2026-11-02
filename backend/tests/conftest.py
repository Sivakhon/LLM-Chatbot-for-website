import hashlib
import math
import re
import uuid
from collections.abc import Iterator

import chromadb
import numpy as np
import pytest
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.config import Settings as ChromaSettings
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.domain.product import Product, SizeVariant
from app.llm.fake import FakeLLMClient
from app.main import create_app
from app.repositories.product_repository import ProductRepository


class HashingEmbedding(EmbeddingFunction[Documents]):
    """Deterministic bag-of-words embedding: offline, fast, good enough for tests."""

    DIM = 256

    def __init__(self) -> None:
        pass

    @staticmethod
    def name() -> str:
        return "test-hashing"

    def get_config(self) -> dict[str, object]:
        return {}

    @staticmethod
    def build_from_config(config: dict[str, object]) -> "HashingEmbedding":
        return HashingEmbedding()

    def __call__(self, input: Documents) -> Embeddings:
        out = []
        for text in input:
            vec = np.zeros(self.DIM, dtype=np.float32)
            for tok in re.findall(r"\w+", text.lower()):
                tok = tok.rstrip("s")  # crude singularisation: jeans/jean, shorts/short
                vec[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.DIM] += 1.0
            norm = math.sqrt(float((vec**2).sum())) or 1.0
            out.append(vec / norm)
        return out


def make_product(sku: str, name: str, price: float, original: float, cats: str) -> Product:
    return Product(
        sku=sku,
        name=name,
        price=price,
        original_price=original,
        categories=cats,
        sizes=[SizeVariant(size="M", sku=sku)],
        image_url=f"https://img.example/{sku}.jpg",
    )


SAMPLE_PRODUCTS = [
    make_product("SKU-1", "Men's Slim Jeans Blue", 1290, 1990, "Men,Men Clothing,Men Jeans"),
    make_product(
        "SKU-2", "Women's Skinny Jeans Black", 990, 990, "Women,Women Clothing,Women Jeans"
    ),
    make_product("SKU-3", "Short pants Brown", 565, 595, "Women,Women Clothing,Women Shorts"),
    make_product("SKU-4", "Jacket Bomber Black", 1595, 2695, "Men,Men Clothing,Men Jackets"),
    make_product("SKU-5", "Selvedge Jeans Black", 2465, 2595, "Men,Men Pants,Women,Women Pants"),
]


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment="test",
        llm_provider="fake",
        chroma_mode="memory",
        log_level="WARNING",
    )


@pytest.fixture
def repository() -> ProductRepository:
    client = chromadb.EphemeralClient(settings=ChromaSettings(anonymized_telemetry=False))
    repo = ProductRepository(client, f"test-{uuid.uuid4().hex}", HashingEmbedding())
    repo.upsert(SAMPLE_PRODUCTS)
    return repo


@pytest.fixture
def client(settings: Settings, repository: ProductRepository) -> Iterator[TestClient]:
    app = create_app(settings, repository=repository, llm=FakeLLMClient())
    with TestClient(app) as c:
        yield c
