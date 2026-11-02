"""Load product JSON into the vector store.

    python -m app.ingest ../data/raw/mc_jeans_products.json [--reset]

Accepts both the clean schema (scraper output) and the legacy notebook format.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.domain.product import Product
from app.repositories.product_repository import ProductRepository
from app.repositories.vector_store import create_chroma_client

logger = logging.getLogger("app.ingest")


def load_products(path: Path) -> list[Product]:
    records = json.loads(path.read_text(encoding="utf-8"))
    products: dict[str, Product] = {}
    for i, raw in enumerate(records):
        try:
            product = Product.from_any(raw)
        except (ValidationError, ValueError, KeyError) as exc:
            logger.warning("record %d skipped: %s", i, exc)
            continue
        products[product.sku] = product  # last write wins on duplicate SKUs
    return list(products.values())


def ingest(path: Path, repo: ProductRepository, reset: bool = False) -> int:
    products = load_products(path)
    if reset:
        repo.reset()
    return repo.upsert(products)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("path", type=Path)
    ap.add_argument("--reset", action="store_true", help="drop the collection first")
    args = ap.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level)
    repo = ProductRepository(create_chroma_client(settings), settings.collection_name)
    n = ingest(args.path, repo, reset=args.reset)
    logger.info("done: %d products indexed (collection size: %d)", n, repo.count())


if __name__ == "__main__":
    main()
