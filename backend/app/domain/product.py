"""Product domain model + conversions to/from the vector store and legacy scrape format."""

from __future__ import annotations

import html
import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator

Gender = Literal["men", "women", "unisex"]
ProductType = Literal["tops", "bottoms", "footwear", "accessories"]

# Matched against category names (most specific first). Order matters:
# footwear/accessories before tops so "Flip-Flops" never matches a broader rule.
_PRODUCT_TYPE_KEYWORDS: tuple[tuple[ProductType, tuple[str, ...]], ...] = (
    ("footwear", ("sneaker", "flip-flop", "sandal", "shoe", "slipper", "boot")),
    ("accessories", ("belt", "bag", "hat", "cap", "wallet", "sock")),
    ("tops", ("t-shirt", "shirt", "hoodie", "sweater", "jacket", "coat", "polo", "top")),
    ("bottoms", ("pant", "jean", "short", "trouser", "skirt", "chino")),
)

_NUMBER_RE = re.compile(r"[^\d.]")


def parse_price(value: Any) -> float:
    """'฿1,295' / '1,295' / 1295 -> 1295.0"""
    if isinstance(value, int | float):
        return float(value)
    cleaned = _NUMBER_RE.sub("", str(value))
    if not cleaned:
        raise ValueError(f"not a price: {value!r}")
    return float(cleaned)


def infer_gender(categories: list[str]) -> Gender | None:
    roots = {c.strip().lower() for c in categories}
    men, women = "men" in roots, "women" in roots
    if men and women:
        return "unisex"
    if men:
        return "men"
    if women:
        return "women"
    return None


def infer_product_type(categories: list[str], name: str = "") -> ProductType | None:
    """Coarse product type from the most specific category, falling back to the name."""
    for text in [*reversed(categories), name]:
        lowered = text.lower()
        for ptype, keywords in _PRODUCT_TYPE_KEYWORDS:
            if any(k in lowered for k in keywords):
                return ptype
    return None


class SizeVariant(BaseModel):
    size: str
    sku: str


class Product(BaseModel):
    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    brand: str = "MC Jeans"
    price: float = Field(ge=0, description="Final (selling) price in THB")
    original_price: float = Field(ge=0)
    categories: list[str] = Field(default_factory=list)
    sizes: list[SizeVariant] = Field(default_factory=list)
    image_url: str | None = None
    product_url: str | None = None

    @field_validator("name", "brand", mode="before")
    @classmethod
    def _clean_text(cls, v: str) -> str:
        return re.sub(r"\s+", " ", html.unescape(str(v))).strip()

    @field_validator("categories", mode="before")
    @classmethod
    def _clean_categories(cls, v: Any) -> list[str]:
        items = v.split(",") if isinstance(v, str) else list(v or [])
        seen: dict[str, None] = {}
        for item in items:
            clean = html.unescape(str(item)).strip()
            if clean:
                seen.setdefault(clean, None)
        return list(seen)

    @field_validator("image_url", mode="before")
    @classmethod
    def _clean_url(cls, v: str | None) -> str | None:
        return html.unescape(v) if v else None

    # -- derived fields ------------------------------------------------------
    @computed_field  # type: ignore[prop-decorator]
    @property
    def discount_amount(self) -> float:
        return max(self.original_price - self.price, 0.0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def discount_percent(self) -> int:
        if self.original_price <= 0:
            return 0
        return round(self.discount_amount * 100 / self.original_price)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gender(self) -> Gender | None:
        return infer_gender(self.categories)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def product_type(self) -> ProductType | None:
        return infer_product_type(self.categories, self.name)

    # -- vector store mapping -----------------------------------------------
    def to_document(self) -> str:
        """Text that gets embedded. Name + category path carry most of the semantics."""
        cats = ", ".join(self.categories)
        return f"{self.name}. Brand: {self.brand}. Categories: {cats}."

    def to_metadata(self) -> dict[str, str | int | float | bool]:
        """Chroma metadata only accepts scalars, so lists are JSON-encoded."""
        return {
            "sku": self.sku,
            "name": self.name,
            "brand": self.brand,
            "price": self.price,
            "original_price": self.original_price,
            "discount_percent": self.discount_percent,
            "gender": self.gender or "",
            "product_type": self.product_type or "",
            "categories": json.dumps(self.categories, ensure_ascii=False),
            "sizes": json.dumps([s.model_dump() for s in self.sizes]),
            "image_url": self.image_url or "",
            "product_url": self.product_url or "",
        }

    @classmethod
    def from_metadata(cls, meta: dict[str, Any]) -> Product:
        return cls(
            sku=meta["sku"],
            name=meta["name"],
            brand=meta.get("brand", "MC Jeans"),
            price=meta["price"],
            original_price=meta["original_price"],
            categories=json.loads(meta.get("categories") or "[]"),
            sizes=json.loads(meta.get("sizes") or "[]"),
            image_url=meta.get("image_url") or None,
            product_url=meta.get("product_url") or None,
        )

    # -- legacy notebook format ---------------------------------------------
    @classmethod
    def from_legacy(cls, raw: dict[str, Any]) -> Product:
        """Convert a record produced by the original notebook scraper.

        Legacy records are flat string dicts with dashed keys, e.g.
        ``{"product-final-price": "1,295", "product-config-sku": '{"sizeM":{"sku":"..."}}'}``.
        """
        sizes: list[SizeVariant] = []
        config = raw.get("product-config-sku")
        if config and config != "None":
            for label, data in json.loads(config).items():
                sizes.append(SizeVariant(size=label.removeprefix("size").strip(), sku=data["sku"]))

        return cls(
            sku=raw["product-sku"],
            name=raw["product-name"],
            price=parse_price(raw["product-final-price"]),
            original_price=parse_price(raw["product-original-price"]),
            categories=raw.get("product-categories", ""),
            sizes=sizes,
            image_url=raw.get("product-image"),
        )

    @classmethod
    def from_any(cls, raw: dict[str, Any]) -> Product:
        return cls.from_legacy(raw) if "product-sku" in raw else cls.model_validate(raw)
