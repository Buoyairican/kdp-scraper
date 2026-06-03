"""
stage4_bsr.py — BSR + Publication Date Confirmation

For each keyword that passed Stage 3:
  1. Pull top S4_BOOKS_PER_KEYWORD ASINs
  2. Fetch each product page (with ASIN-level caching to avoid repeat calls)
  3. Parse BSR (root "in Books" rank), review count, publication date
  4. Fully classify each book using models.Book.classify()
  5. Aggregate per-keyword classification counts

ASIN cache:
  Stored in state['stage4']['asin_cache'] — a dict of ASIN → Book dict.
  Any ASIN already in the cache skips the network call.
  Cached entries older than 14 days are re-fetched.
"""

from __future__ import annotations
from datetime import datetime, timedelta

import config
from src.api_client import fetch_html
from src.models import Book
from src.parsers import parse_product_page, is_blocked
from src.state_manager import StateManager
from src.logger import log


CACHE_TTL_DAYS = 14


def _product_url(asin: str) -> str:
    return f"https://www.amazon.com/dp/{asin}"


def _is_cache_fresh(book_dict: dict) -> bool:
    scrape_date_str = book_dict.get("scrape_date")
    if not scrape_date_str:
        return False
    try:
        scrape_date = datetime.fromisoformat(scrape_date_str).date()
        return (datetime.utcnow().date() - scrape_date) < timedelta(days=CACHE_TTL_DAYS)
    except ValueError:
        return False


def _fetch_and_classify(asin: str, state: StateManager) -> Book | None:
    """
    Fetch a product page, parse it, classify the book.
    Returns a Book object, or None on hard failure.
    """
    url  = _product_url(asin)
    html = fetch_html(url, js=config.JS_RENDER, state_mgr=state)

    if html is None:
        log.warning(f"    BSR fetch failed for ASIN {asin}")
        return None

    if is_blocked(html):
        log.error("    CAPTCHA / block detected. Saving state and stopping.")
        raise SystemExit("Stage 4 stopped: Amazon CAPTCHA. Resume later.")

    raw = parse_product_page(html, asin)
    if "error" in raw:
        return None

    book = Book(
        asin         = asin,
        title        = raw.get("title", ""),
        bsr_books    = raw.get("bsr_books"),
        bsr_sub      = raw.get("bsr_sub"),
        review_count = raw.get("review_count"),
        pub_date     = raw.get("pub_date"),
        format       = raw.get("format", "paperback"),
    )
    book.classify()
    return book


def run(state: StateManager) -> None:
    """Execute Stage 4. Idempotent."""
    log.info("=== STAGE 4 — BSR Confirmation ===")

    pending          = state.get("stage4", "pending_keywords", default=[])
    enriched         = state.get("stage4", "enriched_keywords", default=[])
    asin_cache       = state.get("stage4", "asin_cache", default={})
    done_kws         = {e["keyword"] for e in enriched}

    pending = [p for p in pending if p["keyword"] not in done_kws]

    if not pending:
        log.info("Stage 4: no pending keywords — already complete.")
        _advance(state)
        return

    log.info(f"Stage 4: {len(pending)} keywords to confirm via BSR.")

    for entry in list(pending):
        keyword = entry["keyword"]
        asins   = entry.get("asins", [])[:config.S4_BOOKS_PER_KEYWORD]

        if keyword in done_kws:
            continue

        log.info(f"  Keyword: '{keyword}' — checking {len(asins)} ASINs")
        books_for_keyword = []

        for asin in asins:
            # Check ASIN cache first
            if asin in asin_cache and _is_cache_fresh(asin_cache[asin]):
                log.debug(f"    Cache hit: {asin}")
                cached_dict = asin_cache[asin]
                # Reconstruct Book from cache dict
                book = Book(**{
                    k: cached_dict.get(k)
                    for k in [
                        "asin", "title", "bsr_books", "bsr_sub",
                        "review_count", "pub_date", "format", "scrape_date"
                    ]
                })
                book.classification = cached_dict.get("classification", "UNKNOWN")
            else:
                log.debug(f"    Fetching ASIN: {asin}")
                book = _fetch_and_classify(asin, state)
                if book is None:
                    continue
                # Store in ASIN cache
                asin_cache[asin] = book.to_dict()
                state.set(asin_cache, "stage4", "asin_cache")

            books_for_keyword.append(book)
            log.info(
                f"    {asin} → {book.classification} "
                f"(BSR={book.bsr_books}, reviews={book.review_count}, "
                f"pub={book.pub_date})"
            )

        # Compute averages
        bsr_values = [b.bsr_books for b in books_for_keyword if b.bsr_books]
        avg_bsr    = sum(bsr_values) / len(bsr_values) if bsr_values else None

        result = {
            "keyword":            keyword,
            "winning_count":      sum(1 for b in books_for_keyword if b.classification == "WINNING"),
            "authority_count":    sum(1 for b in books_for_keyword if b.classification == "AUTHORITY"),
            "dead_count":         sum(1 for b in books_for_keyword if b.classification == "DEAD"),
            "inconclusive_count": sum(1 for b in books_for_keyword if b.classification == "INCONCLUSIVE"),
            "unknown_count":      sum(1 for b in books_for_keyword if b.classification == "UNKNOWN"),
            "avg_bsr_top3":       avg_bsr,
            "books":              [b.to_dict() for b in books_for_keyword],
        }

        enriched_updated = state.get("stage4", "enriched_keywords", default=[])
        enriched_updated.append(result)
        state.set(enriched_updated, "stage4", "enriched_keywords")
        done_kws.add(keyword)

        log.info(
            f"  → winning={result['winning_count']} "
            f"authority={result['authority_count']} "
            f"avg_bsr={int(avg_bsr) if avg_bsr else 'n/a'}"
        )

    enriched_final = state.get("stage4", "enriched_keywords", default=[])
    log.info(f"Stage 4 complete. {len(enriched_final)} keywords enriched.")
    _advance(state)


def _advance(state: StateManager) -> None:
    state.advance_stage(5)
