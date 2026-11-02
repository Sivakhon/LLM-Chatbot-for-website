"""Streamlit chat UI for ShopBot. All logic lives in the API; this is just a client."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import httpx
import streamlit as st

from api_client import ShopBotClient

API_URL = os.getenv("SHOPBOT_API_URL", "http://localhost:8000")
API_KEY = os.getenv("SHOPBOT_API_KEY") or None

st.set_page_config(page_title="ShopBot · MC Jeans", page_icon="👖", layout="wide")


@st.cache_resource
def get_client() -> ShopBotClient:
    return ShopBotClient(API_URL, API_KEY)


def render_filters(applied: dict[str, Any]) -> None:
    parts = []
    if applied.get("gender"):
        parts.append(f"for {applied['gender']}")
    if applied.get("min_price") is not None:
        parts.append(f"≥ ฿{applied['min_price']:,.0f}")
    if applied.get("max_price") is not None:
        parts.append(f"≤ ฿{applied['max_price']:,.0f}")
    if parts:
        st.caption("🎯 Filters applied: " + " · ".join(parts))


def render_products(sources: list[dict[str, Any]]) -> None:
    if not sources:
        return
    with st.expander(f"🔎 {len(sources)} products used to answer", expanded=False):
        cols = st.columns(min(len(sources), 3))
        for i, item in enumerate(sources):
            p = item["product"]
            with cols[i % len(cols)]:
                if p.get("image_url"):
                    st.image(p["image_url"], width="stretch")
                st.markdown(f"**{p['name']}**")
                price = f"฿{p['price']:,.0f}"
                if p["discount_percent"]:
                    price += f" ~~฿{p['original_price']:,.0f}~~ `-{p['discount_percent']}%`"
                st.markdown(price)
                sizes = ", ".join(s["size"] for s in p["sizes"]) or "—"
                st.caption(f"SKU {p['sku']} · sizes: {sizes} · relevance {item['score']:.2f}")


# --- Sidebar ---------------------------------------------------------------
with st.sidebar:
    st.header("👖 ShopBot")
    st.caption("RAG shopping assistant over the MC Jeans catalog")
    try:
        status = get_client().ready()
        if status.get("status") == "ok":
            st.success(f"API ready · {status.get('products_indexed')} products")
        else:
            st.warning(status.get("detail") or "API degraded")
        if status.get("llm_model"):
            st.caption(f"Model: `{status['llm_provider']}/{status['llm_model']}`")
    except httpx.HTTPError:
        st.error(f"API unreachable at {API_URL}")

    st.caption(
        "💡 Just ask naturally: price and gender are understood from your message, "
        "e.g. *ไม่เกิน 1000 บาท*, *for men under 1,500*."
    )
    if st.button("🗑️ Clear chat", width="stretch"):
        st.session_state.messages = []
        st.rerun()

# --- Chat ----------------------------------------------------------------
st.session_state.setdefault("messages", [])

if not st.session_state.messages:
    st.info("Try: *“Black slim jeans for men under 1,500 baht?”* or *“มีกางเกงขาสั้นผู้หญิงไหม”*")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        render_filters(msg.get("filters", {}))
        render_products(msg.get("sources", []))

if prompt := st.chat_input("Ask about products, sizes, prices…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
    sources: list[dict[str, Any]] = []
    applied: dict[str, Any] = {}
    errors: list[str] = []

    def token_stream() -> Iterator[str]:
        for ev in get_client().stream_chat(history):
            if ev.event == "filters":
                applied.update(ev.data)
            elif ev.event == "sources":
                sources.extend(ev.data)
            elif ev.event == "token":
                yield ev.data
            elif ev.event == "error":
                errors.append(ev.data.get("message", "Unknown error"))

    with st.chat_message("assistant"):
        try:
            answer = st.write_stream(token_stream())
        except httpx.HTTPError as exc:
            answer = ""
            errors.append(f"Could not reach the API: {exc}")
        for err in errors:
            st.error(err)
        render_filters(applied)
        render_products(sources)

    if answer and not errors:
        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "sources": sources, "filters": applied}
        )
