import pytest

from app.domain.product import Product, infer_gender, parse_price

LEGACY = {
    "product-name": "Jacket Bomber Men Black",
    "product-sku": "MKP1869699",
    "product-final-price": "1,595",
    "product-original-price": "2695",
    "product-discount-bath": "1100",
    "product-discount-percent": "40",
    "product-categories": "Men,Men Clothing,Men Jackets &amp; Coats,Men Jackets",
    "product-config-sku": '{"sizeM":{"sku":"MKP1869693"},"sizeS":{"sku":"MKP1869697"}}',
    "product-image": "https://assets.central.co.th/x?$JPEG$&amp;wid=199",
}


@pytest.mark.parametrize(
    ("raw", "expected"), [("1,295", 1295.0), ("฿2,195", 2195.0), (755, 755.0), ("99.50", 99.5)]
)
def test_parse_price(raw: object, expected: float) -> None:
    assert parse_price(raw) == expected


def test_parse_price_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_price("free")


def test_from_legacy_normalises_everything() -> None:
    p = Product.from_legacy(LEGACY)
    assert p.price == 1595 and p.original_price == 2695
    assert p.discount_amount == 1100 and p.discount_percent == 41
    assert "Men Jackets & Coats" in p.categories  # HTML entity decoded
    assert [s.size for s in p.sizes] == ["M", "S"]
    assert p.image_url == "https://assets.central.co.th/x?$JPEG$&wid=199"
    assert p.gender == "men"


def test_from_legacy_without_sizes() -> None:
    p = Product.from_legacy({**LEGACY, "product-config-sku": "None"})
    assert p.sizes == []


@pytest.mark.parametrize(
    ("cats", "gender"),
    [(["Men", "Men Jeans"], "men"), (["Women"], "women"), (["Men", "Women"], "unisex"), ([], None)],
)
def test_infer_gender(cats: list[str], gender: str | None) -> None:
    assert infer_gender(cats) == gender


def test_metadata_roundtrip() -> None:
    p = Product.from_legacy(LEGACY)
    assert Product.from_metadata(p.to_metadata()) == p


def test_from_any_accepts_clean_schema() -> None:
    p = Product.from_legacy(LEGACY)
    assert Product.from_any(p.model_dump(mode="json")) == p


def test_whole_legacy_dataset_loads() -> None:
    from pathlib import Path

    from app.ingest import load_products

    path = Path(__file__).parents[2] / "data" / "raw" / "mc_jeans_products.json"
    products = load_products(path)
    assert len(products) == 105
    assert all(p.price <= p.original_price for p in products)
