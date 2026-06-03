"""
stage2_keywords.py — Keyword Expansion via Alphabet Soup

For each surviving category, runs all 26 letters through Amazon's
autocomplete endpoint to surface real buyer search phrases.

Amazon autocomplete endpoint (no auth, no credits consumed):
  https://completion.amazon.com/api/2017/suggestions
  ?mid=ATVPDKIKX0ER&alias=stripbooks&prefix=KEYWORD&nb=10&lop=en_US

Strategy:
  - Each category generates a handful of "seed terms" based on its label.
  - Each seed term is expanded with letters a-z as the next word.
  - Results are deduplicated globally to avoid scraping the same phrase twice.
  - Maximum S2_MAX_CANDIDATES keywords forwarded to Stage 3.
"""

from __future__ import annotations
import string
import time
from urllib.parse import quote_plus

import config
from src.api_client import fetch_json_direct
from src.state_manager import StateManager
from src.logger import log


AUTOCOMPLETE_URL = (
    "https://completion.amazon.com/api/2017/suggestions"
    "?mid=ATVPDKIKX0DER"
    "&alias=stripbooks"
    "&prefix={prefix}"
    "&nb=10"
    "&lop=en_US"
    "&site-variant=desktop"
)

# How many seed terms to generate per category label
SEEDS_PER_CATEGORY = 3


def _category_seeds(label: str) -> list[str]:
    """
    Turn a category label into starting search phrases.
    These become the roots for alphabet soup expansion.

    Example: "Health, Fitness & Dieting" →
      ["health", "fitness guide", "diet"]
    """
    word_map = {
        "Health, Fitness & Dieting":     ["health guide", "fitness for", "lose weight"],
        "Self-Help":                      ["self help for", "overcome", "stop"],
        "Business & Money":               ["business for", "make money", "entrepreneur"],
        "Parenting & Relationships":      ["parenting guide", "raising", "toddler"],
        "Religion & Spirituality":        ["christian living", "prayer", "faith"],
        "Science & Math":                 ["science explained", "beginner", "introduction to"],
        "Sports & Outdoors":              ["training guide", "running", "strength"],
        "Cookbooks, Food & Wine":         ["cookbook for", "recipes for", "easy"],
        "Politics & Social Sciences":     ["psychology of", "social skills", "behavior"],
        "Education & Teaching":           ["study guide", "learning", "skills"],
        "Medical Books":                  ["medical guide", "condition", "treatment"],
        "Law":                            ["law for", "legal guide", "rights"],
        "History":                        ["history of", "world war", "ancient"],
        "Biographies & Memoirs":          ["memoir", "life of", "story of"],
        "Computers & Technology":         ["python for", "coding for", "tech"],
        "Crafts, Hobbies & Home":         ["beginners guide", "how to make", "diy"],
        "Travel":                         ["travel guide", "backpacking", "solo travel"],
        "Psychology & Counseling":        ["anxiety", "trauma", "mental health"],
        "Christian Books & Bibles":       ["devotional", "bible study", "christian"],
        "Business Communication":         ["communication skills", "public speaking", "writing"],
    }
    # Normalise the label for lookup
    for key, seeds in word_map.items():
        if key.lower() in label.lower() or label.lower() in key.lower():
            return seeds[:SEEDS_PER_CATEGORY]

    # Generic fallback: lowercase first word of the label
    first_word = label.split(",")[0].split("&")[0].strip().lower()
    return [first_word, f"{first_word} for", f"best {first_word}"]


def _autocomplete(prefix: str) -> list[str]:
    """
    Calls Amazon autocomplete for a given prefix string.
    Returns a list of suggested keyword phrases.
    """
    url = AUTOCOMPLETE_URL.format(prefix=quote_plus(prefix))
    data = fetch_json_direct(url)
    if not data:
        return []

    suggestions = data.get("suggestions", [])
    return [s.get("value", "").strip() for s in suggestions if s.get("value")]


def run(state: StateManager) -> None:
    """Execute Stage 2. Idempotent."""
    log.info("=== STAGE 2 — Keyword Expansion ===")

    pending_cats   = state.get("stage2", "pending_categories", default=[])
    done_cats      = state.get("stage2", "done_categories", default=[])
    candidates     = state.get("stage2", "candidate_keywords", default=[])
    seen_keywords  = {kw for kw in candidates}

    done_labels = {c["label"] for c in done_cats}
    pending_cats = [c for c in pending_cats if c["label"] not in done_labels]

    if not pending_cats:
        log.info("Stage 2: no pending categories — already complete.")
        _advance(state, candidates)
        return

    log.info(
        f"Stage 2: expanding keywords for {len(pending_cats)} categories. "
        f"{len(candidates)} candidates so far."
    )

    for cat in list(pending_cats):
        if len(candidates) >= config.S2_MAX_CANDIDATES:
            log.info(f"Reached S2_MAX_CANDIDATES ({config.S2_MAX_CANDIDATES}). Stopping expansion.")
            break

        label = cat["label"]
        log.info(f"  Category: {label}")
        seeds = _category_seeds(label)

        for seed in seeds:
            log.info(f"    Seed: '{seed}'")
            for letter in string.ascii_lowercase:
                prefix = f"{seed} {letter}"
                suggestions = _autocomplete(prefix)
                new_count = 0
                for kw in suggestions:
                    kw_lower = kw.lower().strip()
                    if kw_lower and kw_lower not in seen_keywords:
                        seen_keywords.add(kw_lower)
                        candidates.append(kw_lower)
                        new_count += 1
                if new_count:
                    log.debug(f"      '{prefix}' → +{new_count} keywords")

                # Save after each letter (each autocomplete call)
                state.set(candidates, "stage2", "candidate_keywords")

                if len(candidates) >= config.S2_MAX_CANDIDATES:
                    break
            if len(candidates) >= config.S2_MAX_CANDIDATES:
                break

        # Mark category done
        done_cats_updated = state.get("stage2", "done_categories", default=[])
        done_cats_updated.append(cat)
        state.set(done_cats_updated, "stage2", "done_categories")
        log.info(f"  Done {label}. Total candidates: {len(candidates)}")

    log.info(f"Stage 2 complete. {len(candidates)} keyword candidates.")
    _advance(state, candidates)


def _advance(state: StateManager, candidates: list[str]) -> None:
    state.set(candidates, "stage3", "pending_keywords")
    state.advance_stage(3)
