"""
api_client.py — Provider-agnostic scraping interface.

All pipeline stages call this module only. The concrete provider
is resolved from config.SCRAPER_PROVIDER — one line in config.py.
"""

from __future__ import annotations
from functools import lru_cache
from typing import Optional
import time

import requests

import config
from src.logger import log
from src.providers import (
    BaseProvider,
    ProviderError,
    ScrapingAntProvider,
    ScraperAPIProvider,
    OxylabsProvider,
    ScrapingBeeProvider,
)


@lru_cache(maxsize=1)
def _get_provider() -> BaseProvider:
    """
    Instantiate the provider selected in config.py.
    Cached — one instance for the whole run.
    """
    provider_map = {
        "scrapingant":  ScrapingAntProvider,
        "scraperapi":   ScraperAPIProvider,
        "oxylabs":      OxylabsProvider,
        "scrapingbee":  ScrapingBeeProvider,
    }
    key = config.SCRAPER_PROVIDER.lower()
    if key not in provider_map:
        raise ProviderError(
            f"Unknown SCRAPER_PROVIDER '{config.SCRAPER_PROVIDER}'. "
            f"Valid values: {list(provider_map)}"
        )
    log.info(f"Scraping provider: {key}")
    return provider_map[key]()


def fetch_html(
    url: str,
    js: bool = None,
    state_mgr=None,
) -> Optional[str]:
    """
    Fetch a URL via the configured provider.
    Updates credit counter in state if state_mgr is provided.
    Returns HTML string, or None if the request fails after retries.

    Parameters
    ----------
    url       : target URL
    js        : True = headless browser render (costs more credits)
    state_mgr : StateManager instance — used to track credits
    """
    if js is None:
        js = config.JS_RENDER
    provider = _get_provider()
    try:
        html, credits_remaining = provider.fetch(url, js=js)
        if state_mgr is not None:
            state_mgr.update_credits(credits_remaining)
        log.debug(f"Fetched ({credits_remaining} credits left): {url[:80]}")
        return html
    except ProviderError as e:
        log.error(f"Provider error fetching {url}: {e}")
        if "401" in str(e) or "403" in str(e):
            raise SystemExit(f"API credentials exhausted or invalid: {e}")
        return None
    except requests.RequestException as e:
        log.error(f"Network error fetching {url}: {e}")
        return None


def fetch_json_direct(url: str, timeout: int = 10) -> Optional[dict | list]:
    """
    For endpoints that return JSON directly (Amazon autocomplete API).
    Does NOT use a scraping provider — no credits consumed.
    """
    try:
        time.sleep(config.DELAY_BETWEEN_CALLS)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.debug(f"fetch_json_direct failed for {url}: {e}")
        return None
