"""
stage5_score.py — Scoring and CSV Output

Applies GO / WATCH / SKIP verdict to each enriched keyword.
Writes results.csv sorted by verdict then winning_count descending.

GO   : winning_count >= 3 AND authority_count <= 1
WATCH: winning_count >= 1
SKIP : everything else
"""

from __future__ import annotations
import csv
import os
from datetime import datetime

import config
from src.models import KeywordResult
from src.state_manager import StateManager
from src.logger import log

CSV_COLUMNS = [
    "verdict",
    "keyword",
    "winning_count",
    "authority_count",
    "dead_count",
    "inconclusive_count",
    "unknown_count",
    "avg_bsr_top3",
]

VERDICT_SORT_ORDER = {"GO": 0, "WATCH": 1, "SKIP": 2}


def run(state: StateManager) -> None:
    """Execute Stage 5. Idempotent."""
    log.info("=== STAGE 5 — Scoring and Output ===")

    enriched = state.get("stage4", "enriched_keywords", default=[])

    if not enriched:
        log.warning("Stage 5: no enriched keywords to score. Nothing to output.")
        return

    results: list[KeywordResult] = []

    for entry in enriched:
        kr = KeywordResult(
            keyword           = entry["keyword"],
            winning_count     = entry.get("winning_count", 0),
            authority_count   = entry.get("authority_count", 0),
            dead_count        = entry.get("dead_count", 0),
            inconclusive_count= entry.get("inconclusive_count", 0),
            unknown_count     = entry.get("unknown_count", 0),
            avg_bsr_top3      = entry.get("avg_bsr_top3"),
            books             = entry.get("books", []),
        )
        kr.score()
        results.append(kr)

    # Sort: GO first, then WATCH, then SKIP; within each group by winning_count desc
    results.sort(
        key=lambda r: (VERDICT_SORT_ORDER.get(r.verdict, 99), -r.winning_count)
    )

    # Ensure output directory exists
    os.makedirs(os.path.dirname(config.OUTPUT_CSV), exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_path = config.OUTPUT_CSV.replace(".csv", f"_{timestamp}.csv")

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r.to_csv_row())

    # Summary
    go_count    = sum(1 for r in results if r.verdict == "GO")
    watch_count = sum(1 for r in results if r.verdict == "WATCH")
    skip_count  = sum(1 for r in results if r.verdict == "SKIP")

    log.info(
        f"Stage 5 complete.\n"
        f"  GO:    {go_count}\n"
        f"  WATCH: {watch_count}\n"
        f"  SKIP:  {skip_count}\n"
        f"  Output: {output_path}"
    )
    _print_top_go(results)

    state.set(True,        "stage5", "complete")
    state.set(output_path, "stage5", "output_path")


def _print_top_go(results: list[KeywordResult]) -> None:
    """Print top GO opportunities to stdout."""
    go = [r for r in results if r.verdict == "GO"]
    if not go:
        print("\nNo GO opportunities found this run.")
        return

    print(f"\n{'='*60}")
    print(f"  TOP GO OPPORTUNITIES ({len(go)} total)")
    print(f"{'='*60}")
    for r in go[:15]:
        print(
            f"  [{r.verdict}] {r.keyword:<40} "
            f"W={r.winning_count}  A={r.authority_count}  "
            f"BSR={int(r.avg_bsr_top3) if r.avg_bsr_top3 else 'n/a'}"
        )
    print(f"{'='*60}\n")
    print(f"Full results: {config.OUTPUT_CSV}")
