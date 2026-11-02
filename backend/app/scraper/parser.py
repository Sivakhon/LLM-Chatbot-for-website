"""Parse central.co.th listing pages into `Product`s.

The original notebook split prettified HTML on newlines and `data-`. That broke
whenever attribute order or whitespace changed. Here we read the `data-*`
attributes of each product card directly and parse the price block by its
text, so the parser is independent of formatting.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
from pydantic import ValidationError

from app.domain.product import Product, SizeVariant, parse_price

logger = logging.getLogger(__name__)

BASE_URL = "https://www.central.co.th"
CARD_SELECTOR = "div.productCard[data-product-sku]"
_BAHT_RE = re.compile(r"฿\s*([\d,]+(?:\.\d+)?)")


def _loads_lenient(raw: str | None) -> Any:
    """Data attributes sometimes hold JSON with single quotes or HTML-escaped quotes."""
    if not raw:
        return None
    for candidate in (raw, raw.strip("'"), raw.replace("'", '"')):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def parse_categories(raw: str | None) -> list[str]:
    """Accepts the hierarchical facet value, e.g.

    ``{"lvl0": ["Women"], "lvl1": ["Women /// Women Clothing"], ...}``
    and returns the deepest path(s) flattened: ``["Women", "Women Clothing", ...]``.
    """
    data = _loads_lenient(raw)
    if isinstance(data, dict) and data:
        deepest = data[sorted(data)[-1]]
        paths = deepest if isinstance(deepest, list) else [deepest]
    elif isinstance(data, list):
        paths = data
    elif raw:
        paths = [re.sub(r"[\[\]{}\"']", "", raw.split(":")[-1])]
    else:
        return []
    out: list[str] = []
    for path in paths:
        for part in str(path).split("///"):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def parse_sizes(raw: str | None) -> list[SizeVariant]:
    """``{"123": {"size": "28 EU", "sku": "MKP..."}, ...}`` -> [SizeVariant(...)]"""
    data = _loads_lenient(raw)
    if not isinstance(data, dict):
        return []
    sizes = []
    for item in data.values():
        if isinstance(item, dict) and item.get("sku") and item.get("size"):
            sizes.append(SizeVariant(size=str(item["size"]), sku=str(item["sku"])))
    return sizes


def parse_prices(card: Tag) -> tuple[float, float]:
    """Returns (final_price, original_price). Cards show '฿final ฿original ฿saving'."""
    amounts = [parse_price(m) for m in _BAHT_RE.findall(card.get_text(" "))]
    if not amounts:
        raise ValueError("no price found")
    final = amounts[0]
    original = amounts[1] if len(amounts) > 1 and amounts[1] >= final else final
    return final, original


def parse_card(card: Tag) -> Product:
    final, original = parse_prices(card)
    img = card.find("img")
    link = card.find("a", href=True)
    return Product(
        sku=str(card["data-product-sku"]),
        name=str(card.get("data-product-name", "")),
        brand=str(card.get("data-product-brand") or "MC Jeans"),
        price=final,
        original_price=original,
        categories=parse_categories(card.get("data-product-categories")),  # type: ignore[arg-type]
        sizes=parse_sizes(card.get("data-product-config-sku")),  # type: ignore[arg-type]
        image_url=str(img.get("src")) if isinstance(img, Tag) and img.get("src") else None,
        product_url=urljoin(BASE_URL, str(link["href"])) if isinstance(link, Tag) else None,
    )


def parse_listing(html: str) -> list[Product]:
    soup = BeautifulSoup(html, "html.parser")
    products: list[Product] = []
    for card in soup.select(CARD_SELECTOR):
        try:
            products.append(parse_card(card))
        except (ValueError, ValidationError) as exc:
            # One malformed card must not kill the whole page.
            logger.warning("skipping card %s: %s", card.get("data-product-sku"), exc)
    return products
