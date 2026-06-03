"""
stage1_nodes.py — Seed Title → Node Discovery

Takes a seed book title, searches Amazon for it, then uses ScrapingBee's
Amazon Product API to get BSR category nodes from the sales_rank field.

Output: list of {node_id, label} stored in state.
"""

from __future__ import annotations
import re
import time
from urllib.parse import quote_plus

import requests

import config
from src.api_client import fetch_html
from src.parsers import _soup, is_blocked
from src.state_manager import StateManager
from src.logger import log


SCRAPINGBEE_PRODUCT_URL = "https://app.scrapingbee.com/api/v1/amazon/product"


def _search_url(title: str) -> str:
    words = title.split(":")[:1][0].strip().split()[:8]
    query = " ".join(words)
    return f"https://www.amazon.com/s?k={quote_plus(query)}&i=stripbooks"


def _find_seed_asin(html: str) -> str | None:
    """Extract the first organic ASIN from search results."""
    soup = _soup(html)
    for item in soup.select('[data-component-type="s-search-result"]'):
        asin = item.get("data-asin", "").strip()
        if asin:
            return asin

    asins = re.findall(r"/dp/([A-Z0-9]{10})", html)
    log.debug(f"Regex fallback found {len(asins)} ASINs in {len(html)} bytes of HTML")
    if asins:
        return asins[0]

    log.warning(f"No ASINs found. HTML length={len(html)}, first 200 chars: {html[:200]}")
    return None


def _fetch_product_data(asin: str) -> dict | None:
    """Fetch product data via ScrapingBee Amazon Product API."""
    params = {
        "api_key": config.SCRAPINGBEE_API_KEY,
        "query": asin,
        "light_request": "true",
        "domain": "com",
    }
    try:
        time.sleep(config.DELAY_BETWEEN_CALLS)
        resp = requests.get(
            SCRAPINGBEE_PRODUCT_URL,
            params=params,
            timeout=config.REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            log.error(f"ScrapingBee Product API returned {resp.status_code}")
            return None
        return resp.json()
    except Exception as e:
        log.error(f"ScrapingBee Product API error: {e}")
        return None


def _clean_label(name: str) -> str:
    """Strip '#1 Best Seller' prefix from category names."""
    if "Best Seller" in name:
        name = name.split("Best Seller", 1)[1]
    return name.strip()


def _extract_nodes_from_sales_rank(data: dict) -> list[dict]:
    """Extract category nodes from sales_rank field in API response."""
    sales_rank = data.get("sales_rank", [])
    if not sales_rank:
        log.warning("No sales_rank field in product data.")
        return []

    nodes = []
    seen_ids = set()

    for entry in sales_rank:
        ladder = entry.get("ladder", [])
        for step in ladder:
            url = step.get("url", "")
            name = _clean_label(step.get("name", ""))
            m = re.search(r"/(?:gp/bestsellers|zgbs)/books/(\d+)", url)
            if m:
                node_id = m.group(1)
                if node_id not in seen_ids and name:
                    seen_ids.add(node_id)
                    nodes.append({"node_id": node_id, "label": name})

    return nodes


def run(state: StateManager) -> None:
    """Execute Stage 1: find seed book and extract category nodes."""
    log.info("=== STAGE 1 — Seed → Node Discovery ===")

    existing_nodes = state.get("stage1", "nodes", default=[])
    if existing_nodes:
        log.info(f"Stage 1 already complete. {len(existing_nodes)} nodes found.")
        state.advance_stage(2)
        return

    seed_title = state.get("seed_title", default="")
    if not seed_title:
        raise SystemExit("No seed title provided. Use --title flag.")

    # Step 1: Search for the seed title
    log.info(f"Searching Amazon for: {seed_title[:80]}...")
    search_html = fetch_html(_search_url(seed_title), js=False, state_mgr=state)
    if not search_html:
        raise SystemExit("Failed to fetch search results for seed title.")

    seed_asin = _find_seed_asin(search_html)
    if not seed_asin:
        raise SystemExit("Could not find seed book on Amazon.")

    log.info(f"Found seed ASIN: {seed_asin}")
    state.set(seed_asin, "stage1", "seed_asin")

    # Step 2: Get product data via ScrapingBee Amazon Product API
    log.info(f"Fetching product data for {seed_asin} via Product API...")
    product_data = _fetch_product_data(seed_asin)
    if not product_data:
        raise SystemExit(f"Failed to fetch product data for ASIN {seed_asin}.")

    nodes = _extract_nodes_from_sales_rank(product_data)
    if not nodes:
        raise SystemExit(
            f"No BSR subcategory nodes found for {seed_asin}. "
            "The book may not have a BSR section."
        )

    state.set(nodes, "stage1", "nodes")
    log.info(f"Stage 1 complete. Found {len(nodes)} category nodes:")
    for n in nodes:
        log.info(f"  - {n['label']} (node {n['node_id']})")

    state.advance_stage(2)
