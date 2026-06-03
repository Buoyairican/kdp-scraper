"""
stage3_serp.py — SERP Filter

For each candidate keyword:
  1. Fetch the Amazon Books search results page
  2. Parse top organic results (sponsored excluded)
  3. Quick-classify each book from SERP data (review count only, no BSR yet)
  4. Drop keyword if too many high-review books dominate page 1
  5. Pass keyword + top ASINs to Stage 4 for BSR confirmation

Quick-classification at this stage:
  - "strong" = review_count >= REVIEWS_AUTHORITY_MIN  (blocks new entrants)
  - "weak"   = review_count <= REVIEWS_WINNING_MAX    (door is open)
  - "mid"    = everything else

A keyword PASSES Stage 3 if:
  - authority_count (strong) <= S3_MAX_AUTHORITY_ON_PAGE1
  - weak_count >= S3_MIN_WINNING_ON_PAGE1
"""

from __future__ import annotations
from urllib.parse import quote_plus

import config
from src.api_client import fetch_html
from src.parsers import parse_serp, is_blocked
from src.state_manager import StateManager
from src.logger import log


def _serp_url(keyword: str) -> str:
    return (
        f"https://www.amazon.com/s"
        f"?k={quote_plus(keyword)}"
        f"&i=stripbooks"
        f"&bbn=283155"   # Books root node
    )


def _quick_classify(review_count) -> str:
    if review_count is None:
        return "unknown"
    if review_count >= config.REVIEWS_AUTHORITY_MIN:
        return "authority"
    if review_count <= config.REVIEWS_WINNING_MAX:
        return "weak"
    return "mid"


def run(state: StateManager) -> None:
    """Execute Stage 3. Idempotent."""
    log.info("=== STAGE 3 — SERP Filter ===")

    pending  = state.get("stage3", "pending_keywords", default=[])
    passed   = state.get("stage3", "passed_keywords", default=[])
    done_kws = set(state.get("stage3", "done_keywords", default=[]))

    pending = [kw for kw in pending if kw not in done_kws]

    if not pending:
        log.info("Stage 3: no pending keywords — already complete.")
        _advance(state, passed)
        return

    log.info(f"Stage 3: {len(pending)} keywords to filter.")

    for keyword in list(pending):
        if keyword in done_kws:
            continue

        log.info(f"  SERP check: '{keyword}'")
        url  = _serp_url(keyword)
        html = fetch_html(url, js=False, state_mgr=state)

        if html is None:
            log.warning(f"  Skipping '{keyword}' — fetch failed.")
            _mark_done(state, keyword, passed_asins=None)
            done_kws.add(keyword)
            continue

        if is_blocked(html):
            log.error("  CAPTCHA / block detected. Saving state and stopping.")
            _mark_done(state, keyword, passed_asins=None)
            raise SystemExit("Stage 3 stopped: Amazon CAPTCHA. Resume later.")

        results = parse_serp(html)
        organic = [r for r in results if not r["is_sponsored"]]
        top     = organic[: config.S3_ORGANIC_RESULTS]

        authority_count = sum(1 for r in top if _quick_classify(r["review_count"]) == "authority")
        weak_count      = sum(1 for r in top if _quick_classify(r["review_count"]) == "weak")

        passes = (
            authority_count <= config.S3_MAX_AUTHORITY_ON_PAGE1
            and weak_count  >= config.S3_MIN_WINNING_ON_PAGE1
        )

        if passes:
            asins = [r["asin"] for r in top if r["asin"]]
            log.info(
                f"  ✓ PASS  '{keyword}' — "
                f"weak={weak_count} authority={authority_count} "
                f"asins={asins}"
            )
            _mark_done(state, keyword, passed_asins=asins)
            passed = state.get("stage3", "passed_keywords", default=[])
        else:
            log.info(
                f"  ✗ FAIL  '{keyword}' — "
                f"weak={weak_count} authority={authority_count}"
            )
            _mark_done(state, keyword, passed_asins=None)

        done_kws.add(keyword)

    passed = state.get("stage3", "passed_keywords", default=[])
    log.info(f"Stage 3 complete. {len(passed)} keywords passed.")
    _advance(state, passed)


def _mark_done(state: StateManager, keyword: str, passed_asins) -> None:
    done = state.get("stage3", "done_keywords", default=[])
    if keyword not in done:
        done.append(keyword)
        state.set(done, "stage3", "done_keywords")

    if passed_asins is not None:
        passed = state.get("stage3", "passed_keywords", default=[])
        entry = {"keyword": keyword, "asins": passed_asins}
        # Dedup
        existing_kws = {p["keyword"] for p in passed}
        if keyword not in existing_kws:
            passed.append(entry)
            state.set(passed, "stage3", "passed_keywords")


def _advance(state: StateManager, passed: list) -> None:
    state.set(passed, "stage4", "pending_keywords")
    state.advance_stage(4)
