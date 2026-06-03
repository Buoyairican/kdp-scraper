"""
stage1_categories.py — Category Discovery

For each seed category:
  1. Fetch top results sorted by review rank (proxy for bestsellers)
  2. Check if any book looks like a WINNING pattern (BSR proxy via review count)
  3. Categories with at least one "active" signal survive and feed Stage 2

We don't pull full product pages here — that's Stage 4.
Here we use review count from SERP as a fast proxy for category health.
A category "survives" if its top results include at least one book with
a low review count (≤ config.REVIEWS_WINNING_MAX) in its top positions,
signalling the door is open for new entrants.
"""

from __future__ import annotations

import config
from src.api_client import fetch_html
from src.models import NONFICTION_SEED_CATEGORIES
from src.parsers import parse_serp, is_blocked
from src.state_manager import StateManager
from src.logger import log

_debug_saved = False


# Amazon Books browse URL for a category node, sorted by review rank
def _category_url(node_id: str) -> str:
    return (
        f"https://www.amazon.com/s"
        f"?i=stripbooks"
        f"&bbn={node_id}"
        f"&rh=n%3A{node_id}"
        f"&s=review-rank"
    )


def _has_buying_signal(results: list[dict]) -> bool:
    """
    Returns True if at least one of the top results has a low review count,
    indicating new entrants can compete in this category.
    """
    organic = [r for r in results if not r["is_sponsored"]]
    low_review_count = 0
    for book in organic[: config.S1_RESULTS_PER_CATEGORY]:
        rc = book.get("review_count")
        if rc is not None and rc < config.REVIEWS_WINNING_MAX:
            low_review_count += 1
    # At least 1 low-review book in top organic results = signal
    return low_review_count >= 1


def run(state: StateManager) -> None:
    """
    Execute Stage 1. Idempotent — skips categories already in state.
    """
    log.info("=== STAGE 1 — Category Discovery ===")

    # Initialise pending list if empty (first run)
    if not state.get("stage1", "pending") and not state.get("stage1", "done"):
        state.set(list(NONFICTION_SEED_CATEGORIES), "stage1", "pending")
        log.info(f"Loaded {len(NONFICTION_SEED_CATEGORIES)} seed categories.")

    pending    = state.get("stage1", "pending", default=[])
    surviving  = state.get("stage1", "surviving", default=[])

    if not pending:
        log.info("Stage 1: no pending categories — already complete.")
        return

    log.info(f"Stage 1: {len(pending)} categories to check.")

    while pending:
        cat = pending[0]
        node  = cat["node"]
        label = cat["label"]

        log.info(f"  Checking category: {label} (node {node})")
        url  = _category_url(node)
        html = fetch_html(url, js=False, state_mgr=state)

        if html is None:
            log.warning(f"  Skipping {label} — fetch returned None.")
            # Move to done without surviving
            _mark_done(state, cat, survived=False)
            pending = state.get("stage1", "pending", default=[])
            continue

        if is_blocked(html):
            log.error("  CAPTCHA / block detected. Saving state and stopping.")
            _mark_done(state, cat, survived=False)
            raise SystemExit("Stage 1 stopped: Amazon CAPTCHA. Resume later.")

        results = parse_serp(html)

        # DEBUG: show what parser found
        organic = [r for r in results if not r["is_sponsored"]]
        log.debug(f"  Parsed {len(results)} results ({len(organic)} organic)")
        for r in organic[:5]:
            log.debug(f"    ASIN={r['asin']} reviews={r['review_count']} title={r['title'][:50]}")
        if not results:
            log.warning(f"  Parser returned 0 results — dumping first 500 chars of HTML:")
            log.warning(html[:500])
        # Save first successful HTML for selector debugging
        global _debug_saved
        if results and not _debug_saved:
            with open("debug_serp.html", "w", encoding="utf-8") as f:
                f.write(html)
            log.info("  [DEBUG] Saved sample HTML to debug_serp.html")
            _debug_saved = True

        survived = _has_buying_signal(results)

        if survived:
            log.info(f"  ✓ SURVIVING: {label}")
            surviving = state.get("stage1", "surviving", default=[])
            surviving.append(cat)
            state.set(surviving, "stage1", "surviving")
        else:
            log.info(f"  ✗ dropped: {label}")

        _mark_done(state, cat, survived=survived)
        pending = state.get("stage1", "pending", default=[])

    surviving = state.get("stage1", "surviving", default=[])
    log.info(
        f"Stage 1 complete. {len(surviving)} categories survived."
    )

    if len(surviving) < config.S1_MIN_SURVIVING:
        log.warning(
            f"Only {len(surviving)} categories survived "
            f"(minimum: {config.S1_MIN_SURVIVING}). "
            "Check your API key and proxy — results may be blocked."
        )

    # Seed Stage 2 pending list from surviving categories
    state.set(list(surviving), "stage2", "pending_categories")
    state.advance_stage(2)


def _mark_done(state: StateManager, cat: dict, survived: bool) -> None:
    """Remove from pending, add to done."""
    pending = state.get("stage1", "pending", default=[])
    pending = [c for c in pending if c["node"] != cat["node"]]
    state.set(pending, "stage1", "pending")

    done = state.get("stage1", "done", default=[])
    done.append({**cat, "survived": survived})
    state.set(done, "stage1", "done")
