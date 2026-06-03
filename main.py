#!/usr/bin/env python3
"""
KDP Niche Research Pipeline — Bestseller List Approach
======================================================
Takes a seed book title, finds its category nodes, scans
bestseller lists, and outputs GO/WATCH/SKIP verdicts with
keyword variations for content planning.

Usage:
    python main.py --title "Book Title Here"
    python main.py --title "Book Title Here" --demo
    python main.py --resume       # Resume from last checkpoint
    python main.py --status       # Print pipeline status
    python main.py --reset        # Wipe state and start fresh
"""

from __future__ import annotations
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

import config
from src.state_manager import StateManager
from src.logger import log


def run_demo(seed_title: str) -> None:
    """Print a no-network demo run that mirrors the real completion output."""
    results = [
        {
            "verdict": "GO",
            "label": "Assisted Living Facility Guides",
            "winning_count": 5,
            "authority_count": 2,
        },
        {
            "verdict": "WATCH",
            "label": "Senior Care Business",
            "winning_count": 3,
            "authority_count": 6,
        },
        {
            "verdict": "SKIP",
            "label": "Entrepreneurship",
            "winning_count": 0,
            "authority_count": 18,
        },
    ]
    keywords = [
        "assisted living facility startup",
        "assisted living business plan",
        "assisted living policies and procedures",
        "residential care home business",
        "senior care business startup",
        "how to open an assisted living home",
        "non medical home care business",
        "elder care business guide",
        "group home business startup",
    ]

    print(f"\nKDP Bestseller Pipeline")
    print(f"  Provider : demo")
    print(f"  Seed     : {seed_title[:70]}")
    print(f"  State    : demo (no API calls)")
    print()

    print(f"\n{'='*60}")
    print("PIPELINE COMPLETE")
    print(f"{'='*60}")
    for r in results:
        print(
            f"  {r['verdict']:5s} | {r['label']} "
            f"(winning={r['winning_count']}, authority={r['authority_count']})"
        )
    print(f"\n  Keyword variations: 42")
    print("  Top keywords:")
    for kw in keywords:
        print(f"    - {kw}")
    print("  Output: output/results_demo.csv")
    print(f"{'='*60}")


def run_pipeline(state: StateManager) -> None:
    from src import stage1_nodes, stage2_bestsellers, stage3_expand

    STAGE_MAP = {
        1: stage1_nodes.run,
        2: stage2_bestsellers.run,
        3: stage3_expand.run,
    }

    while True:
        current = state.get("current_stage", default=1)

        if current not in STAGE_MAP:
            log.info("All stages complete.")
            break

        if current == 3 and state.get("stage3", "complete", default=False):
            output = state.get("stage3", "output_path")
            print(f"\nPipeline already complete. Results: {output}")
            break

        log.info(f"Dispatching stage {current}...")

        try:
            STAGE_MAP[current](state)
        except SystemExit as e:
            print(f"\n[STOP] {e}")
            print("State saved. Re-run 'python main.py --resume' to continue.")
            sys.exit(0)
        except KeyboardInterrupt:
            print("\n[INTERRUPTED] State saved. Re-run to resume.")
            sys.exit(0)

        if current >= 3:
            break


def print_status(state: StateManager) -> None:
    s = state.state
    current = s.get("current_stage", 1)
    credits = s.get("credits_remaining", "unknown")
    seed = s.get("seed_title", "not set")

    print(f"\nKDP Bestseller Pipeline — Status")
    print(f"  Seed title   : {seed[:60]}...")
    print(f"  Current stage: {current}")
    print(f"  Credits left : {credits}")
    print()

    s1 = s.get("stage1", {})
    nodes = s1.get("nodes", [])
    print(f"  Stage 1 — Node Discovery")
    print(f"    Seed ASIN: {s1.get('seed_asin', 'pending')}")
    print(f"    Nodes    : {len(nodes)}")
    for n in nodes:
        print(f"      - {n['label']} ({n['node_id']})")

    s2 = s.get("stage2", {})
    results = s2.get("results", [])
    print(f"  Stage 2 — Bestseller Scan")
    print(f"    Completed: {len(results)}/{len(nodes)} nodes")
    for r in results:
        print(f"      - {r['label']}: {r['verdict']} (winning={r['winning_count']})")

    s3 = s.get("stage3", {})
    print(f"  Stage 3 — Keywords + Output")
    print(f"    Complete : {s3.get('complete', False)}")
    keywords = s3.get("keyword_variations", [])
    print(f"    Keywords : {len(keywords)}")
    if s3.get("output_path"):
        print(f"    File     : {s3['output_path']}")
    print()


def _session_paths(session: str | None) -> tuple[str, str]:
    """Return (state_file, output_dir) for the given session name."""
    if session:
        return f"state/{session}.json", f"output/{session}"
    return config.STATE_FILE, "output"


def main() -> None:
    parser = argparse.ArgumentParser(description="KDP Bestseller Niche Pipeline")
    parser.add_argument("--title", type=str, help="Seed book title to analyze")
    parser.add_argument("--session", type=str, help="Session name (allows parallel runs)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--status", action="store_true", help="Show pipeline status")
    parser.add_argument("--reset", action="store_true", help="Wipe state and restart")
    parser.add_argument("--demo", action="store_true", help="Run with hardcoded demo output and no API calls")
    args = parser.parse_args()

    if args.demo:
        run_demo(args.title or "How To Start An Assisted Living Facility")
        return

    state_file, output_dir = _session_paths(args.session)
    state = StateManager(state_file)
    state._output_dir = output_dir

    if args.reset:
        state.reset()
        print("State reset. Use --title to start a new analysis.")
        return

    if args.status:
        print_status(state)
        return

    if args.title:
        # New run with a seed title
        state._state = {
            "current_stage": 1,
            "credits_remaining": None,
            "seed_title": args.title,
            "stage1": {},
            "stage2": {},
            "stage3": {},
        }
        state._save()
        log.info(f"New analysis: {args.title[:80]}")
    elif not args.resume:
        # Check if there's existing state to resume
        if not state.get("seed_title"):
            print("Usage: python main.py --title \"Your Seed Book Title Here\"")
            print("       python main.py --resume  (to continue a previous run)")
            return

    print(f"\nKDP Bestseller Pipeline")
    print(f"  Provider : {config.SCRAPER_PROVIDER}")
    print(f"  Seed     : {state.get('seed_title', default='')[:70]}")
    print(f"  State    : {config.STATE_FILE}")
    print()

    run_pipeline(state)


if __name__ == "__main__":
    main()
