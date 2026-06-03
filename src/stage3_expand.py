"""
stage3_expand.py — Keyword Expansion from Winning Titles + CSV Output

For nodes with GO or WATCH verdict:
  - Extract niche phrases from WINNING book titles
  - Run alphabet soup on each phrase via Amazon autocomplete
  - Write final output: node verdicts + winning titles + keyword variations
"""

from __future__ import annotations
import csv
import os
import re
import string
from datetime import datetime
from urllib.parse import quote_plus

import config
from src.api_client import fetch_json_direct
from src.state_manager import StateManager
from src.logger import log


AUTOCOMPLETE_URL = (
    "https://completion.amazon.com/api/2017/suggestions"
    "?mid=ATVPDKIKX0DER"
    "&alias=stripbooks"
    "&node=283155"
    "&prefix={prefix}"
    "&nb=10"
    "&lop=en_US"
    "&site-variant=desktop"
)


def _autocomplete(prefix: str) -> list[str]:
    url = AUTOCOMPLETE_URL.format(prefix=quote_plus(prefix))
    data = fetch_json_direct(url)
    if not data:
        return []
    suggestions = data.get("suggestions", [])
    return [s.get("value", "").strip() for s in suggestions if s.get("value")]


STOP_WORDS = {"the", "and", "for", "in", "a", "to", "of", "with", "an", "by",
              "is", "are", "on", "at", "how", "step", "guide", "complete",
              "ultimate", "beginners", "book", "handbook", "manual", "edition",
              "updated", "new", "your", "from"}


def _extract_seeds(titles: list[str], category_label: str = "", top_n: int = 5) -> list[str]:
    """Extract top n-grams from winning titles as soup seeds."""
    from collections import Counter

    ngram_counts = Counter()
    category_lower = category_label.lower()

    for title in titles:
        clean = re.sub(r"[^a-z\s]", "", title.lower())
        tokens = [t for t in clean.split() if t not in STOP_WORDS and len(t) > 2]

        for n in (2, 3):
            for i in range(len(tokens) - n + 1):
                ngram = " ".join(tokens[i:i+n])
                ngram_counts[ngram] += 1

    filtered = [
        (ngram, count) for ngram, count in ngram_counts.most_common(20)
        if ngram not in category_lower
    ]

    return [ngram for ngram, _ in filtered[:top_n]]


def _expand_phrase(phrase: str) -> list[str]:
    """Run alphabet soup on a phrase: phrase + letter for a-z."""
    keywords = set()
    for letter in string.ascii_lowercase:
        prefix = f"{phrase} {letter}"
        suggestions = _autocomplete(prefix)
        for kw in suggestions:
            kw_lower = kw.lower().strip()
            if kw_lower:
                keywords.add(kw_lower)
    return sorted(keywords)


def _write_output(results: list[dict], keywords: list[str], state: StateManager) -> str:
    """Write final CSV output."""
    output_dir = getattr(state, "_output_dir", "output")
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = f"{output_dir}/results_{timestamp}.csv"

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        # Section 1: Node verdicts
        writer.writerow(["=== NODE VERDICTS ==="])
        writer.writerow(["node_id", "category", "verdict", "winning_count", "authority_count", "total_books"])
        for r in results:
            writer.writerow([
                r["node_id"], r["label"], r["verdict"],
                r["winning_count"], r["authority_count"], r["total_books"],
            ])

        writer.writerow([])

        # Section 2: Winning books
        writer.writerow(["=== WINNING BOOKS ==="])
        writer.writerow(["category", "rank", "title", "review_count", "asin"])
        for r in results:
            if r["verdict"] in ("GO", "WATCH", "WATCH (high-win)"):
                for book in r.get("winning_books", []):
                    writer.writerow([
                        r["label"], book.get("rank", ""),
                        book.get("title", ""), book.get("review_count", ""),
                        book.get("asin", ""),
                    ])

        writer.writerow([])

        # Section 3: Keyword variations
        writer.writerow(["=== KEYWORD VARIATIONS ==="])
        writer.writerow(["keyword"])
        for kw in keywords:
            writer.writerow([kw])

    return output_path


def run(state: StateManager) -> None:
    """Execute Stage 3: expand keywords from winning titles and output."""
    log.info("=== STAGE 3 — Keyword Expansion + Output ===")

    results = state.get("stage2", "results", default=[])
    if not results:
        raise SystemExit("No Stage 2 results. Run Stage 2 first.")

    # Check if already done
    if state.get("stage3", "complete", default=False):
        output = state.get("stage3", "output_path")
        log.info(f"Stage 3 already complete. Output: {output}")
        return

    # Find GO and WATCH nodes
    go_watch = [r for r in results if r["verdict"] in ("GO", "WATCH")]

    if not go_watch:
        log.info("No GO or WATCH nodes found. Writing SKIP-only output.")
        output_path = _write_output(results, [], state)
        state.set(True, "stage3", "complete")
        state.set(output_path, "stage3", "output_path")
        print(f"\nPipeline complete. All nodes SKIP. Results: {output_path}")
        return

    # Collect winning book titles and expand
    all_keywords = state.get("stage3", "keyword_variations", default=[])
    seen = set(all_keywords)

    if not all_keywords:
        log.info(f"Expanding keywords from {len(go_watch)} GO/WATCH nodes...")

        for r in go_watch:
            titles = [book["title"] for book in r.get("winning_books", []) if book.get("title")]
            seeds = _extract_seeds(titles, category_label=r["label"])
            log.info(f"  Node '{r['label']}' — soup seeds: {seeds}")

            for seed in seeds:
                log.info(f"    Expanding: '{seed}'")
                new_keywords = _expand_phrase(seed)
                for kw in new_keywords:
                    if kw not in seen:
                        seen.add(kw)
                        all_keywords.append(kw)

                state.set(all_keywords, "stage3", "keyword_variations")

        log.info(f"Expansion complete. {len(all_keywords)} keyword variations found.")

    # Write output
    output_path = _write_output(results, all_keywords, state)
    state.set(True, "stage3", "complete")
    state.set(output_path, "stage3", "output_path")

    # Print summary
    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE")
    print(f"{'='*60}")
    for r in results:
        print(f"  {r['verdict']:5s} | {r['label']} (winning={r['winning_count']}, authority={r['authority_count']})")
    print(f"\n  Keyword variations: {len(all_keywords)}")
    print(f"  Output: {output_path}")
    print(f"{'='*60}")
