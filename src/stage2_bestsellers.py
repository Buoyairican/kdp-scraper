"""
stage2_bestsellers.py — Bestseller List Scan + Classification

For each category node from Stage 1:
  - Fetch top 100 books (2 pages of 50)
  - Classify each book using rank + review count
  - Compute verdict: GO / WATCH / SKIP

Classification rules (bestseller list):
  WINNING:      rank <= 50 AND review_count < 75
  AUTHORITY:    review_count >= 500
  INCONCLUSIVE: everything else
  DEAD:         n/a (on the list = selling)
"""

from __future__ import annotations
import time

import config
from src.api_client import fetch_html
from src.parsers import is_blocked
from src.state_manager import StateManager
from src.logger import log
from src.parsers_bestseller import parse_bestseller_list


LOW_CONTENT_KEYWORDS = [
    "journal", "log", "workbook", "planner", "notebook", "tracker",
    "diary", "organizer", "checklist", "logbook", "record book",
    "activity book", "coloring", "puzzle", "word search", "sudoku",
    "lined pages", "dot grid", "ledger", "ledger book", "form book",
    "estimate form", "columnar pad", "invoice book", "receipt book",
]


def _is_low_content(title: str) -> bool:
    title_lower = title.lower()
    return any(kw in title_lower for kw in LOW_CONTENT_KEYWORDS)


def _bestseller_url(node_id: str, page: int = 1) -> str:
    return f"https://www.amazon.com/best-sellers-books-Amazon/zgbs/books/{node_id}?pg={page}"


def _classify_book(rank: int, review_count: int | None) -> str:
    if review_count is None:
        return "INCONCLUSIVE"
    if review_count >= 500:
        return "AUTHORITY"
    if rank <= 50 and review_count < 75:
        return "WINNING"
    return "INCONCLUSIVE"


def _compute_verdict(winning_count: int, authority_count: int) -> str:
    if winning_count >= config.GO_WINNING and authority_count <= config.GO_MAX_AUTHORITY:
        return "GO"
    elif winning_count >= config.WATCH_WINNING:
        return "WATCH"
    return "SKIP"


def run(state: StateManager) -> None:
    """Execute Stage 2: scan bestseller lists and classify."""
    log.info("=== STAGE 2 — Bestseller List Scan ===")

    nodes = state.get("stage1", "nodes", default=[])
    if not nodes:
        raise SystemExit("No nodes found. Run Stage 1 first.")

    results = state.get("stage2", "results", default=[])
    done_node_ids = {r["node_id"] for r in results}
    pending = [n for n in nodes if n["node_id"] not in done_node_ids]

    if not pending:
        log.info("Stage 2 already complete.")
        state.advance_stage(3)
        return

    log.info(f"Stage 2: scanning {len(pending)} category nodes.")

    for node in pending:
        node_id = node["node_id"]
        label = node["label"]

        if node_id in getattr(config, "SKIP_NODES", []):
            log.info(f"  Node: {label} ({node_id}) — in SKIP_NODES, skipping.")
            results.append({
                "node_id": node_id, "label": label, "verdict": "SKIP",
                "total_books": 0, "winning_count": 0, "authority_count": 0,
                "inconclusive_count": 0, "winning_books": [],
            })
            state.set(results, "stage2", "results")
            continue

        log.info(f"  Node: {label} ({node_id})")

        all_books = []

        for page in range(1, 3):  # 2 pages of ~30 each ≈ 60 books
            url = _bestseller_url(node_id, page)
            log.info(f"    Fetching page {page}...")
            html = fetch_html(url, js=config.JS_RENDER, state_mgr=state)

            if not html:
                log.warning(f"    Failed to fetch page {page} for node {node_id}")
                continue

            if is_blocked(html):
                log.error("    CAPTCHA detected. Saving state and stopping.")
                raise SystemExit("CAPTCHA on bestseller page.")

            books = parse_bestseller_list(html, page_offset=(page - 1) * 30)
            log.info(f"    Page {page}: parsed {len(books)} books")
            all_books.extend(books)

            if page < 2:
                time.sleep(3)

        if not all_books:
            log.warning(f"    Node {node_id} returned 0 books — FETCH_FAILED")
            results.append({
                "node_id": node_id, "label": label, "verdict": "FETCH_FAILED",
                "total_books": 0, "winning_count": 0, "authority_count": 0,
                "inconclusive_count": 0, "winning_books": [],
            })
            state.set(results, "stage2", "results")
            continue

        # Classify
        winning_count = 0
        authority_count = 0
        inconclusive_count = 0
        winning_books = []

        for book in all_books:
            title = book.get("title", "")
            if _is_low_content(title):
                log.info(f"    Excluded low-content: {title[:60]}")
                continue

            classification = _classify_book(book["rank"], book.get("review_count"))
            book["classification"] = classification

            if classification == "WINNING":
                winning_count += 1
                winning_books.append(book)
            elif classification == "AUTHORITY":
                authority_count += 1
            else:
                inconclusive_count += 1

        verdict = _compute_verdict(winning_count, authority_count)
        if verdict == "WATCH" and winning_count >= 8:
            verdict = "WATCH (high-win)"

        result = {
            "node_id": node_id,
            "label": label,
            "verdict": verdict,
            "total_books": len(all_books),
            "winning_count": winning_count,
            "authority_count": authority_count,
            "inconclusive_count": inconclusive_count,
            "winning_books": winning_books,
        }

        results.append(result)
        state.set(results, "stage2", "results")

        log.info(
            f"  → {verdict} | winning={winning_count}, "
            f"authority={authority_count}, inconclusive={inconclusive_count}"
        )

    log.info("Stage 2 complete.")
    for r in results:
        log.info(f"  {r['label']}: {r['verdict']} (winning={r['winning_count']})")

    state.advance_stage(3)
