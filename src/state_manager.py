"""
state_manager.py — Atomic JSON state.

Writes after every API call. On restart, the pipeline reads this file
and resumes from the exact point it stopped.

Structure
---------
{
  "current_stage": 1,
  "credits_remaining": 840,
  "stage1": {
    "pending":   [...category dicts...],
    "done":      [...category dicts...],
    "surviving": [...category dicts...]
  },
  "stage2": {
    "pending_categories": [...],
    "done_categories":    [...],
    "candidate_keywords": [...]
  },
  "stage3": {
    "pending_keywords":   [...],
    "passed_keywords":    [...],
    "done_keywords":      [...]
  },
  "stage4": {
    "pending_keywords":   [...],
    "enriched_keywords":  [...],   # list of KeywordResult dicts
    "asin_cache":         {...}     # ASIN -> Book dict
  },
  "stage5": {
    "complete": false,
    "output_path": null
  }
}
"""

from __future__ import annotations
import json
import os
import sys
import time
from typing import Any

import config
from src.logger import log


_EMPTY_STATE: dict = {
    "current_stage": 1,
    "credits_remaining": None,
    "stage1": {
        "pending":   [],
        "done":      [],
        "surviving": [],
    },
    "stage2": {
        "pending_categories": [],
        "done_categories":    [],
        "candidate_keywords": [],
    },
    "stage3": {
        "pending_keywords":   [],
        "passed_keywords":    [],
        "done_keywords":      [],
    },
    "stage4": {
        "pending_keywords":  [],
        "enriched_keywords": [],
        "asin_cache":        {},
    },
    "stage5": {
        "complete":    False,
        "output_path": None,
    },
}


class StateManager:
    def __init__(self, path: str = config.STATE_FILE):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._state = self._load()

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> dict:
        return self._state

    def get(self, *keys: str, default: Any = None) -> Any:
        """Deep-get: state.get('stage1', 'pending') → state['stage1']['pending']"""
        node = self._state
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node

    def set(self, value: Any, *keys: str) -> None:
        """Deep-set and immediately persist to disk."""
        node = self._state
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        self._save()

    def append(self, value: Any, *keys: str) -> None:
        """Append to a list at the given key path and persist."""
        lst = self.get(*keys, default=[])
        if not isinstance(lst, list):
            raise TypeError(f"State at {keys} is not a list")
        lst.append(value)
        self.set(lst, *keys)

    def update_credits(self, remaining: int | None) -> None:
        if remaining is not None:
            self._state["credits_remaining"] = remaining
            self._save()
            if remaining <= config.CREDIT_RESERVE:
                log.warning(
                    f"Credits critically low: {remaining} remaining "
                    f"(reserve threshold: {config.CREDIT_RESERVE}). "
                    "Saving state and exiting."
                )
                self._save()
                sys.exit(0)

    def advance_stage(self, stage: int) -> None:
        self._state["current_stage"] = stage
        self._save()
        log.info(f"Advanced to stage {stage}")

    def reset(self) -> None:
        """Wipe state and start fresh. Prompts for confirmation."""
        ans = input("Reset all pipeline state? This cannot be undone. [y/N] ")
        if ans.strip().lower() != "y":
            print("Reset cancelled.")
            return
        self._state = json.loads(json.dumps(_EMPTY_STATE))
        self._save()
        log.info("State reset to empty.")

    # ------------------------------------------------------------------ #
    # Internal                                                            #
    # ------------------------------------------------------------------ #

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                log.info(
                    f"Resuming from state file. "
                    f"Current stage: {data.get('current_stage', '?')}  "
                    f"Credits: {data.get('credits_remaining', '?')}"
                )
                return data
            except (json.JSONDecodeError, OSError) as e:
                log.warning(f"State file unreadable ({e}). Starting fresh.")
        return json.loads(json.dumps(_EMPTY_STATE))

    def _save(self) -> None:
        """Atomic write: temp file → rename to avoid corruption on interrupt."""
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
            os.replace(tmp, self.path)
        except OSError as e:
            log.error(f"Failed to save state: {e}")
