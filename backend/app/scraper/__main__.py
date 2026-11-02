"""Scrape a central.co.th brand listing to a JSON file.

python -m app.scraper --brand mc-jeans --pages 3 --out ../data/processed/products.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from app.core.logging import configure_logging
from app.scraper.fetcher import fetch_pages
from app.scraper.parser import BASE_URL, parse_listing

logger = logging.getLogger("app.scraper")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--brand", default="mc-jeans")
    ap.add_argument("--pages", type=int, default=3)
    ap.add_argument("--out", type=Path, default=Path("../data/processed/products.json"))
    ap.add_argument("--delay", type=float, default=2.0, help="seconds between page loads")
    args = ap.parse_args()
    configure_logging()

    urls = [f"{BASE_URL}/en/{args.brand}?page={p}" for p in range(1, args.pages + 1)]
    pages = asyncio.run(fetch_pages(urls, delay_s=args.delay))

    products = {p.sku: p for html in pages.values() for p in parse_listing(html)}  # dedupe by SKU
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            [p.model_dump(mode="json") for p in products.values()], ensure_ascii=False, indent=2
        )
    )
    logger.info("wrote %d products from %d pages to %s", len(products), len(pages), args.out)


if __name__ == "__main__":
    main()
