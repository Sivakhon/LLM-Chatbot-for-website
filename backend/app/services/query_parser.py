"""Extract structured filters (price range, gender) from free-text questions.

Semantic search alone can't enforce "under 1,000 baht": embeddings don't do
arithmetic. So hard constraints are pulled out of the text and applied as
metadata filters in the vector store. Rules are deterministic (no extra LLM call),
cover Thai and English, and are unit-tested.

Examples:
    "ขอดูของราคาไม่เกิน 1000 หน่อย"     -> max_price=1000
    "jeans for men between 500 and 1.5k" -> gender=men, min_price=500, max_price=1500
    "กางเกงผู้หญิง 1000 บาทขึ้นไป"         -> gender=women, product_types=[bottoms], min_price=1000
    "ขอดูเสื้อผู้ชายราคาไม่เกิน 1000"       -> gender=men, product_types=[tops], max_price=1000
"""

from __future__ import annotations

import re

from pydantic import ValidationError

from app.domain.chat import ProductFilters
from app.domain.product import ProductType

_NUM = r"(\d[\d,]*(?:\.\d+)?\s*k?)"
_PREFIX = r"\s*(?:ราคา|price|of)?\s*(?:฿|thb)?\s*"
_PRICE_CONTEXT = re.compile(r"฿|บาท|baht|thb|ราคา|price|งบ|budget", re.I)

_RANGE = re.compile(
    rf"(?:ระหว่าง|between|from|ตั้งแต่)?{_PREFIX}{_NUM}\s*(?:-|–|to|and|ถึง|และ)\s*(?:฿)?\s*{_NUM}",
    re.I,
)
_MAX = re.compile(
    r"(?:ไม่เกิน|ไม่แพงเกิน|ไม่ถึง|ต่ำกว่า|น้อยกว่า|ถูกกว่า|ภายใน|งบ|under|below|less than|"
    r"cheaper than|at most|up to|no more than|max(?:imum)?|within|budget|<=?)"
    rf"{_PREFIX}{_NUM}",
    re.I,
)
_MIN = re.compile(
    r"(?:(?<!ไม่)(?<!แพง)เกิน|มากกว่า|สูงกว่า|แพงกว่า|ตั้งแต่|over|above|more than|"
    rf"at least|min(?:imum)?|>=?){_PREFIX}{_NUM}",
    re.I,
)
_MIN_SUFFIX = re.compile(rf"{_NUM}\s*(?:฿|บาท|baht)?\s*(?:ขึ้นไป|\+|or more|and up)", re.I)

_MEN = re.compile(r"ผู้ชาย|สุภาพบุรุษ|\b(?:men|man|male|mens|men's|guys?)\b", re.I)
_PRODUCT_TYPES: dict[ProductType, re.Pattern[str]] = {
    "tops": re.compile(
        r"เสื้อ|แจ็[คก]เก็ต|ฮู้ด|สเวตเตอร์|"
        r"\b(?:t-?shirts?|tees?|shirts?|hoodies?|sweaters?|jackets?|coats?|polos?)\b",
        re.I,
    ),
    "bottoms": re.compile(
        r"กางเกง|ยีนส์|ยีน|ขาสั้น|ขายาว|กระโปรง|\b(?:pants?|jeans?|shorts|trousers?|skirts?|chinos?)\b",
        re.I,
    ),
    "footwear": re.compile(
        r"รองเท้า|แตะ|สนีก[เก]อร์|\b(?:shoes?|sneakers?|sandals?|flip-?flops?|slippers?|boots?)\b",
        re.I,
    ),
    "accessories": re.compile(
        r"หมวก|เข็มขัด|กระเป๋า|\b(?:hats?|caps?|belts?|bags?|wallets?|accessor(?:y|ies))\b", re.I
    ),
}

_WOMEN = re.compile(r"ผู้หญิง|สุภาพสตรี|สาว|\b(?:women|woman|female|womens|women's|ladies)\b", re.I)


def _to_number(raw: str) -> float:
    raw = raw.replace(",", "").strip().lower()
    return float(raw[:-1].strip()) * 1000 if raw.endswith("k") else float(raw)


def extract_filters(text: str) -> ProductFilters:
    """Best-effort parse of one message. Unrecognised text yields empty filters."""
    found: dict[str, object] = {}

    if _PRICE_CONTEXT.search(text) and (m := _RANGE.search(text)):
        low, high = sorted((_to_number(m[1]), _to_number(m[2])))
        found.update(min_price=low, max_price=high)
        text = text[: m.start()] + text[m.end() :]
    if m := _MAX.search(text):
        found["max_price"] = _to_number(m[1])
    if m := (_MIN.search(text) or _MIN_SUFFIX.search(text)):
        found["min_price"] = _to_number(m[1])

    men, women = bool(_MEN.search(text)), bool(_WOMEN.search(text))
    if men != women:  # both or neither -> no gender constraint
        found["gender"] = "men" if men else "women"

    types = [t for t, pattern in _PRODUCT_TYPES.items() if pattern.search(text)]
    # "เสื้อยีนส์" (denim jacket) mentions both: keep both rather than guess.
    if types:
        found["product_types"] = types

    try:
        return ProductFilters.model_validate(found)
    except ValidationError:  # e.g. contradictory "over 2000 under 500"
        return ProductFilters()


def resolve_filters(explicit: ProductFilters, messages: list[str]) -> ProductFilters:
    """Combine filters from the UI with those stated in the conversation.

    `messages` are user turns, oldest first; later turns override earlier ones,
    so "under 1000" stays active for a follow-up like "any in black?".
    Explicit (UI/API) filters always win over extracted ones.
    """
    merged: dict[str, object] = {}
    for text in messages:
        merged.update(extract_filters(text).model_dump(exclude_none=True))
    merged.update(explicit.model_dump(exclude_none=True))
    try:
        return ProductFilters.model_validate(merged)
    except ValidationError:
        return explicit
