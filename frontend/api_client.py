"""Thin HTTP client for the ShopBot API (keeps Streamlit code free of transport details)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class SSEEvent:
    event: str
    data: Any


class ShopBotClient:
    def __init__(self, base_url: str, api_key: str | None = None, timeout: float = 60.0) -> None:
        headers = {"X-API-Key": api_key} if api_key else {}
        self._http = httpx.Client(base_url=base_url, headers=headers, timeout=timeout)

    def ready(self) -> dict[str, Any]:
        return self._http.get("/ready").json()

    def stream_chat(self, messages: list[dict[str, str]]) -> Iterator[SSEEvent]:
        """Filters (price, gender) are inferred server-side from the conversation."""
        payload = {"messages": messages}
        with self._http.stream("POST", "/api/v1/chat/stream", json=payload) as resp:
            if resp.status_code != 200:
                resp.read()
                detail = resp.json().get("detail") or resp.json().get("error", {}).get("message")
                yield SSEEvent("error", {"message": detail or f"HTTP {resp.status_code}"})
                return
            event, data_lines = "message", []
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].strip())
                elif line == "" and data_lines:
                    yield SSEEvent(event, json.loads("\n".join(data_lines)))
                    event, data_lines = "message", []
