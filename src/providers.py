"""
providers.py — One class per scraping API provider.

Each class must implement:
    fetch(url: str, js: bool = False) -> tuple[str, int | None]
    Returns (html_content, credits_remaining_or_None)

To add a new provider: add a class here + one entry in api_client.py's
_get_provider() switch.
"""

from __future__ import annotations
import base64
import time
from typing import Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

import config
from src.logger import log


# ------------------------------------------------------------------ #
# Base / interface                                                     #
# ------------------------------------------------------------------ #

class ProviderError(Exception):
    pass


class BaseProvider:
    def fetch(self, url: str, js: bool = False) -> tuple[str, Optional[int]]:
        raise NotImplementedError


# ------------------------------------------------------------------ #
# ScrapingAnt                                                          #
# ------------------------------------------------------------------ #

class ScrapingAntProvider(BaseProvider):
    """
    Docs: https://docs.scrapingant.com/request-response-format
    Credits header: Ant-Credits-Remaining
    """

    BASE_URL = "https://api.scrapingant.com/v2/general"

    def __init__(self):
        self.api_key = config.SCRAPINGANT_API_KEY
        if not self.api_key or "your_" in self.api_key.lower():
            raise ProviderError(
                "SCRAPINGANT_API_KEY not configured. Copy .env.example to .env and add your key."
            )

    @retry(
        stop=stop_after_attempt(config.RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=config.RETRY_BACKOFF_BASE, min=2, max=30),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def fetch(self, url: str, js: bool = False) -> tuple[str, Optional[int]]:
        time.sleep(config.DELAY_BETWEEN_CALLS)
        if "/dp/" in url or "/gp/product/" in url:
            wait_sel = "#productTitle"
        else:
            wait_sel = '[data-component-type="s-search-result"]'

        params = {
            "url":        url,
            "x-api-key":  self.api_key,
            "browser":    "true" if js else "false",
            "proxy_country": "US",
            "wait_for_selector": wait_sel,
        }
        resp = requests.get(
            self.BASE_URL,
            params=params,
            timeout=config.REQUEST_TIMEOUT,
        )
        credits_remaining = self._parse_credits(resp)

        if resp.status_code == 422:
            raise ProviderError(f"ScrapingAnt 422 — bad request for URL: {url}")
        if resp.status_code == 403:
            raise ProviderError("ScrapingAnt 403 — check your API key.")
        if resp.status_code != 200:
            log.warning(f"ScrapingAnt returned {resp.status_code} for {url}")
            resp.raise_for_status()

        return resp.text, credits_remaining

    @staticmethod
    def _parse_credits(resp: requests.Response) -> Optional[int]:
        val = resp.headers.get("Ant-Credits-Remaining")
        if val is not None:
            try:
                return int(val)
            except ValueError:
                pass
        return None


# ------------------------------------------------------------------ #
# ScraperAPI                                                           #
# ------------------------------------------------------------------ #

class ScraperAPIProvider(BaseProvider):
    """
    Docs: https://www.scraperapi.com/documentation/
    Credits (requests remaining): not exposed per-call; track separately.
    """

    BASE_URL = "http://api.scraperapi.com"

    def __init__(self):
        self.api_key = config.SCRAPERAPI_API_KEY
        if not self.api_key or "your_" in self.api_key.lower():
            raise ProviderError(
                "SCRAPERAPI_API_KEY not configured. Copy .env.example to .env and add your key."
            )

    @retry(
        stop=stop_after_attempt(config.RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=config.RETRY_BACKOFF_BASE, min=2, max=30),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def fetch(self, url: str, js: bool = False) -> tuple[str, Optional[int]]:
        time.sleep(config.DELAY_BETWEEN_CALLS)
        params = {
            "api_key": self.api_key,
            "url":     url,
            "render":  "true" if js else "false",
        }
        resp = requests.get(
            self.BASE_URL,
            params=params,
            timeout=config.REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            log.warning(f"ScraperAPI returned {resp.status_code} for {url}")
            resp.raise_for_status()

        # ScraperAPI doesn't return credits in headers; return None
        return resp.text, None


# ------------------------------------------------------------------ #
# Oxylabs                                                              #
# ------------------------------------------------------------------ #

class OxylabsProvider(BaseProvider):
    """
    Docs: https://developers.oxylabs.io/scraper-apis/e-commerce-scraper-api
    Uses the Amazon-specific source for better parsing accuracy.
    """

    BASE_URL = "https://realtime.oxylabs.io/v1/queries"

    def __init__(self):
        self.user = config.OXYLABS_USERNAME
        self.pwd  = config.OXYLABS_PASSWORD
        if not self.user or not self.pwd or "your_" in self.user.lower():
            raise ProviderError(
                "OXYLABS credentials not configured. Copy .env.example to .env and add your username/password."
            )

    @retry(
        stop=stop_after_attempt(config.RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=config.RETRY_BACKOFF_BASE, min=2, max=30),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def fetch(self, url: str, js: bool = False) -> tuple[str, Optional[int]]:
        time.sleep(config.DELAY_BETWEEN_CALLS)

        # Determine Oxylabs source type from URL
        if "/dp/" in url or "/gp/product/" in url:
            source = "amazon_product"
        elif "/s?" in url or "/s/" in url:
            source = "amazon_search"
        else:
            source = "universal"

        payload = {
            "source":     source,
            "url":        url,
            "render":     "html" if js else None,
            "parse":      False,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        resp = requests.post(
            self.BASE_URL,
            auth=(self.user, self.pwd),
            json=payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            log.warning(f"Oxylabs returned {resp.status_code} for {url}")
            resp.raise_for_status()

        try:
            data = resp.json()
        except (ValueError, TypeError) as e:
            log.error(f"Oxylabs JSON decode error for {url}: {e}")
            return "", f"JSON decode error: {e}"
        results = data.get("results")
        if not isinstance(results, list) or not results:
            log.warning(f"Oxylabs returned empty/invalid results for {url}")
            return "", "No results in response"
        html = results[0].get("content", "")
        return html, None


# ------------------------------------------------------------------ #
# ScrapingBee                                                          #
# ------------------------------------------------------------------ #

class ScrapingBeeProvider(BaseProvider):
    """
    Docs: https://www.scrapingbee.com/documentation/
    Credits header: Spb-Credits
    """

    BASE_URL = "https://app.scrapingbee.com/api/v1/"

    def __init__(self):
        self.api_key = config.SCRAPINGBEE_API_KEY
        if not self.api_key or "your_" in self.api_key.lower():
            raise ProviderError(
                "SCRAPINGBEE_API_KEY not configured. Copy .env.example to .env and add your key."
            )

    @retry(
        stop=stop_after_attempt(config.RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=config.RETRY_BACKOFF_BASE, min=2, max=30),
        retry=retry_if_exception_type(requests.RequestException),
        reraise=True,
    )
    def fetch(self, url: str, js: bool = False) -> tuple[str, Optional[int]]:
        time.sleep(config.DELAY_BETWEEN_CALLS)
        params = {
            "api_key":        self.api_key,
            "url":            url,
            "render_js":      "true" if js else "false",
            "premium_proxy":  "true",
            "country_code":   "us",
        }
        if js and "/zgbs/" in url:
            params["block_ads"] = "true"
            params["block_resources"] = "true"
        resp = requests.get(
            self.BASE_URL,
            params=params,
            timeout=config.REQUEST_TIMEOUT,
        )
        credits_remaining = self._parse_credits(resp)

        if resp.status_code == 401:
            raise ProviderError("ScrapingBee 401 — check your API key.")
        if resp.status_code != 200:
            log.warning(f"ScrapingBee returned {resp.status_code} for {url}")
            resp.raise_for_status()

        return resp.text, credits_remaining

    @staticmethod
    def _parse_credits(resp: requests.Response) -> Optional[int]:
        val = resp.headers.get("Spb-Credits")
        if val is not None:
            try:
                return int(val)
            except ValueError:
                pass
        return None
