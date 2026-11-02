from app.domain.chat import ProductFilters
from app.repositories.product_repository import ProductRepository, build_where


def test_build_where() -> None:
    assert build_where(None) is None
    assert build_where(ProductFilters()) is None
    assert build_where(ProductFilters(max_price=1000)) == {"price": {"$lte": 1000}}
    assert build_where(ProductFilters(product_types=["tops", "footwear"])) == {
        "product_type": {"$in": ["tops", "footwear"]}
    }
    assert build_where(ProductFilters(gender="men", min_price=500)) == {
        "$and": [{"gender": {"$in": ["men", "unisex"]}}, {"price": {"$gte": 500}}]
    }


def test_search_ranks_relevant_products_first(repository: ProductRepository) -> None:
    results = repository.search("bomber jacket", k=3)
    assert results[0].product.sku == "SKU-4"
    assert all(0 <= r.score <= 1 for r in results)
    assert results == sorted(results, key=lambda r: r.score, reverse=True)


def test_search_applies_filters(repository: ProductRepository) -> None:
    results = repository.search(
        "jeans", k=5, filters=ProductFilters(gender="women", max_price=1000)
    )
    assert {r.product.sku for r in results} == {"SKU-2", "SKU-3"}


def test_unisex_products_match_gender_filters(repository: ProductRepository) -> None:
    results = repository.search("selvedge", k=5, filters=ProductFilters(gender="women"))
    assert "SKU-5" in {r.product.sku for r in results}


def test_search_deduplicates_variants_by_name(repository: ProductRepository) -> None:
    variant = repository.get("SKU-4")
    assert variant is not None
    repository.upsert([variant.model_copy(update={"sku": "SKU-4-B"})])
    results = repository.search("bomber jacket", k=3)
    names = [r.product.name for r in results]
    assert len(names) == len(set(names)) == 3


def test_get_list_count(repository: ProductRepository) -> None:
    assert repository.count() == 5
    assert repository.get("SKU-1").name == "Men's Slim Jeans Blue"  # type: ignore[union-attr]
    assert repository.get("missing") is None
    items, total = repository.find(limit=2, offset=0)
    assert total == 5 and len(items) == 2


def test_upsert_is_idempotent(repository: ProductRepository) -> None:
    product = repository.get("SKU-1")
    assert product is not None
    repository.upsert([product.model_copy(update={"price": 999})])
    assert repository.count() == 5
    assert repository.get("SKU-1").price == 999  # type: ignore[union-attr]
