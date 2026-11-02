from typing import Annotated

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

from app.api.deps import RepositoryDep
from app.core.errors import NotFoundError
from app.domain.chat import ProductFilters, ScoredProduct
from app.domain.pagination import Page
from app.domain.product import Product

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=Page[Product], summary="List products")
async def list_products(
    repo: RepositoryDep,
    filters: Annotated[ProductFilters, Query()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[Product]:
    items, total = await run_in_threadpool(repo.find, filters, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/search", response_model=list[ScoredProduct], summary="Semantic product search")
async def search_products(
    repo: RepositoryDep,
    filters: Annotated[ProductFilters, Query()],
    q: Annotated[str, Query(min_length=1, max_length=500, description="Natural-language query")],
    k: Annotated[int, Query(ge=1, le=20)] = 5,
) -> list[ScoredProduct]:
    return await run_in_threadpool(repo.search, q, k, filters)


@router.get("/{sku}", response_model=Product, summary="Get a product by SKU")
async def get_product(sku: str, repo: RepositoryDep) -> Product:
    product = await run_in_threadpool(repo.get, sku)
    if product is None:
        raise NotFoundError(f"Product '{sku}' not found")
    return product
