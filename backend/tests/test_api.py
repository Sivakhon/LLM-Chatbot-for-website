import json

from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.llm.fake import FakeLLMClient
from app.main import create_app
from app.repositories.product_repository import ProductRepository


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "products_indexed": None,
        "llm_provider": None,
        "llm_model": None,
        "detail": None,
    }


def test_ready_reports_catalog_and_model(client: TestClient) -> None:
    body = client.get("/ready").json()
    assert body["status"] == "ok" and body["products_indexed"] == 5
    assert body["llm_model"] == "fake-extractive"


def test_request_id_is_propagated(client: TestClient) -> None:
    resp = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert resp.headers["X-Request-ID"] == "abc123"


def test_list_products_paginates_and_filters(client: TestClient) -> None:
    page = client.get("/api/v1/products", params={"limit": 2}).json()
    assert page["total"] == 5 and len(page["items"]) == 2
    cheap = client.get("/api/v1/products", params={"max_price": 1000}).json()
    assert {p["sku"] for p in cheap["items"]} == {"SKU-2", "SKU-3"}


def test_product_detail_and_404(client: TestClient) -> None:
    assert client.get("/api/v1/products/SKU-1").json()["discount_percent"] == 35
    resp = client.get("/api/v1/products/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_search(client: TestClient) -> None:
    results = client.get("/api/v1/products/search", params={"q": "bomber jacket", "k": 2}).json()
    assert results[0]["product"]["sku"] == "SKU-4"


def test_invalid_filters_rejected(client: TestClient) -> None:
    resp = client.get("/api/v1/products", params={"min_price": 2000, "max_price": 100})
    assert resp.status_code == 422


def test_chat(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/chat", json={"messages": [{"role": "user", "content": "bomber jacket"}]}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "SKU-4" in body["answer"]
    assert body["model"] == "fake-extractive"
    assert body["sources"][0]["product"]["sku"] == "SKU-4"


def test_chat_returns_only_cited_products_as_recommended(client: TestClient) -> None:
    msg = {"role": "user", "content": "ขอดูเสื้อผู้ชายราคาไม่เกิน 2000"}
    body = client.post("/api/v1/chat", json={"messages": [msg]}).json()
    assert body["applied_filters"] == {
        "gender": "men",
        "product_types": ["tops"],
        "min_price": None,
        "max_price": 2000,
    }
    assert [s["product"]["sku"] for s in body["sources"]] == ["SKU-4"]
    assert body["recommended_skus"] == ["SKU-4"]


def test_chat_enforces_price_from_message(client: TestClient) -> None:
    msg = {"role": "user", "content": "ขอดูของราคาไม่เกิน 1000 หน่อย"}
    body = client.post("/api/v1/chat", json={"messages": [msg]}).json()
    assert body["applied_filters"]["max_price"] == 1000
    assert body["sources"] and all(s["product"]["price"] <= 1000 for s in body["sources"])


def test_chat_stream_sse(client: TestClient) -> None:
    payload = {"messages": [{"role": "user", "content": "jeans"}], "filters": {"gender": "women"}}
    with client.stream("POST", "/api/v1/chat/stream", json=payload) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        raw = "".join(resp.iter_text())

    events = [
        (block.split("\n")[0].removeprefix("event: "), json.loads(block.split("\n")[1][6:]))
        for block in raw.strip().split("\n\n")
    ]
    assert events[0] == ("filters", {"gender": "women", "product_types": ["bottoms"]})
    assert events[1][0] == "sources"
    assert {s["product"]["gender"] for s in events[1][1]} <= {"women", "unisex"}
    assert events[-2][0] == "recommended"
    assert set(events[-2][1]) <= {s["product"]["sku"] for s in events[1][1]}
    assert events[-1] == ("done", {"model": "fake-extractive"})
    answer = "".join(data for name, data in events if name == "token")
    assert answer.startswith("Here are some products")


def test_chat_validation_error(client: TestClient) -> None:
    resp = client.post("/api/v1/chat", json={"messages": []})
    assert resp.status_code == 422


def test_api_key_enforced_when_configured(
    settings: Settings, repository: ProductRepository
) -> None:
    secured = settings.model_copy(update={"api_key": SecretStr("s3cret")})
    with TestClient(create_app(secured, repository=repository, llm=FakeLLMClient())) as c:
        assert c.get("/api/v1/products").status_code == 401
        assert c.get("/api/v1/products", headers={"X-API-Key": "wrong"}).status_code == 401
        assert c.get("/api/v1/products", headers={"X-API-Key": "s3cret"}).status_code == 200
        assert c.get("/health").status_code == 200  # probes stay public


def test_chat_returns_503_when_llm_not_configured(
    settings: Settings, repository: ProductRepository
) -> None:
    no_key = settings.model_copy(update={"llm_provider": "gemini", "gemini_api_key": None})
    with TestClient(create_app(no_key, repository=repository)) as c:
        resp = c.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 503
        assert "GEMINI_API_KEY" in resp.json()["detail"]
        assert c.get("/api/v1/products/search", params={"q": "jeans"}).status_code == 200
        assert c.get("/ready").status_code == 503
