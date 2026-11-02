"""Headless-browser fetching (the listing is rendered client-side by Algolia)."""

from __future__ import annotations

import asyncio
import logging

from app.scraper.parser import CARD_SELECTOR

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


async def fetch_pages(
    urls: list[str], *, delay_s: float = 2.0, timeout_ms: int = 30_000
) -> dict[str, str]:
    """Render each URL and return its HTML. Waits for product cards instead of sleeping."""
    from playwright.async_api import TimeoutError as PWTimeout
    from playwright.async_api import async_playwright

    html_by_url: dict[str, str] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context(user_agent=USER_AGENT)).new_page()
        for i, url in enumerate(urls):
            if i:
                await asyncio.sleep(delay_s)  # be polite to the site
            logger.info("fetching %s", url)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                await page.wait_for_selector(CARD_SELECTOR, timeout=timeout_ms)
                html_by_url[url] = await page.content()
            except PWTimeout:
                logger.warning("timed out waiting for products on %s", url)
        await browser.close()
    return html_by_url
