from pathlib import Path

from app.scraper.parser import parse_categories, parse_listing, parse_sizes

HTML = (Path(__file__).parent / "fixtures" / "listing.html").read_text(encoding="utf-8")


def test_parse_listing_extracts_valid_cards_and_skips_broken() -> None:
    products = parse_listing(HTML)
    assert [p.sku for p in products] == ["MKP0366150", "MKP1459728"]

    jeans = products[0]
    assert jeans.name == "Women's Jeans slim MBDP18520 Black"
    assert (jeans.price, jeans.original_price, jeans.discount_percent) == (1295, 2195, 41)
    assert jeans.categories == ["Women", "Women Clothing", "Women Pants", "Women Skinny Pants"]
    assert {s.size: s.sku for s in jeans.sizes} == {"28 EU": "MKP0366163", "27 EU": "MKP0366150"}
    assert jeans.image_url == "https://assets.central.co.th/MCJEANS-1?$JPEG$&wid=199"
    assert jeans.product_url == "https://www.central.co.th/en/womens-jeans-slim-mkp0366150"


def test_card_without_discount_uses_single_price() -> None:
    shorts = parse_listing(HTML)[1]
    assert shorts.price == shorts.original_price == 1395
    assert shorts.sizes == []
    assert shorts.gender == "men"


def test_parse_categories_handles_multiple_trees() -> None:
    raw = (
        '{"lvl2":["Men /// Men Clothing /// Men Pants","Women /// Women Clothing /// Women Pants"]}'
    )
    assert parse_categories(raw) == [
        "Men",
        "Men Clothing",
        "Men Pants",
        "Women",
        "Women Clothing",
        "Women Pants",
    ]


def test_parse_helpers_tolerate_missing_values() -> None:
    assert parse_categories(None) == []
    assert parse_sizes(None) == []
    assert parse_sizes("not json") == []
