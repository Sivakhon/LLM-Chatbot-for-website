import pytest

from app.domain.chat import ProductFilters
from app.services.query_parser import extract_filters, resolve_filters


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Thai
        ("ขอดูของราคาไม่เกิน 1000 หน่อย", {"max_price": 1000}),
        ("มีกางเกงต่ำกว่า 800 บาทไหม", {"product_types": ["bottoms"], "max_price": 800}),
        ("งบ 1,500 บาท", {"max_price": 1500}),
        ("ราคาไม่แพงเกิน ฿2,000", {"max_price": 2000}),
        ("เสื้อราคาเกิน 1500", {"product_types": ["tops"], "min_price": 1500}),
        (
            "กางเกงผู้หญิง 1000 บาทขึ้นไป",
            {"gender": "women", "product_types": ["bottoms"], "min_price": 1000},
        ),
        (
            "ยีนส์ผู้ชายราคา 500-1000 บาท",
            {"gender": "men", "product_types": ["bottoms"], "min_price": 500, "max_price": 1000},
        ),
        ("ราคาระหว่าง 1000 ถึง 2000", {"min_price": 1000, "max_price": 2000}),
        # English
        (
            "black jeans for men under 1500 baht",
            {"gender": "men", "product_types": ["bottoms"], "max_price": 1500},
        ),
        ("anything below ฿999?", {"max_price": 999}),
        (
            "women's shorts between 500 and 1.5k baht",
            {"gender": "women", "product_types": ["bottoms"], "min_price": 500, "max_price": 1500},
        ),
        ("jackets over 2000", {"product_types": ["tops"], "min_price": 2000}),
        ("at least 1,000 and at most 2,000", {"min_price": 1000, "max_price": 2000}),
        # nothing to extract
        # the reported case
        (
            "ขอดูเสื้อผู้ชายราคาไม่เกิน 1000",
            {"gender": "men", "product_types": ["tops"], "max_price": 1000},
        ),
        ("มีรองเท้าแตะไหม", {"product_types": ["footwear"]}),
        ("หมวกสีดำ", {"product_types": ["accessories"]}),
        ("t-shirt or hoodie", {"product_types": ["tops"]}),
        ("เสื้อกับกางเกง", {"product_types": ["tops", "bottoms"]}),
        # nothing to extract
        ("show me something black", {}),
        ("for men and women", {}),
        ("size 32 slim fit", {}),
    ],
)
def test_extract_filters(text: str, expected: dict[str, object]) -> None:
    assert extract_filters(text).model_dump(exclude_none=True) == expected


def test_contradictory_constraints_are_dropped() -> None:
    assert extract_filters("over 2000 but under 500") == ProductFilters()


def test_resolve_merges_turns_and_explicit_wins() -> None:
    turns = ["ขอดูของราคาไม่เกิน 1000", "มีสีดำไหม for men"]
    assert resolve_filters(ProductFilters(), turns).model_dump(exclude_none=True) == {
        "gender": "men",
        "max_price": 1000,
    }
    explicit = ProductFilters(max_price=700)
    assert resolve_filters(explicit, turns).max_price == 700


def test_resolve_falls_back_to_explicit_on_conflict() -> None:
    explicit = ProductFilters(max_price=500)
    assert resolve_filters(explicit, ["over 2000"]) == explicit
