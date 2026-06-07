from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import yaml
from google.adk.tools import ToolContext

_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "attacks" / "attack_library.yaml"

_library_cache: dict[str, list[dict[str, str]]] | None = None


def _load_library() -> dict[str, list[dict[str, str]]]:
    global _library_cache
    if _library_cache is None:
        with open(_LIBRARY_PATH, encoding="utf-8") as f:
            _library_cache = yaml.safe_load(f)
    return _library_cache


def _available_categories() -> list[str]:
    return list(_load_library().keys())


async def generate_attack(
    category: str,
    prior_successes: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """Return a batch of attack prompts for the given category.

    In Phase 5 the orchestrator passes prior_successes (newline-separated list
    of prompts that already worked in past rounds).  This function filters them
    OUT of the returned batch so each round tries fresh prompts.  When the full
    category has been exhausted it returns the complete set so the orchestrator
    can decide to pivot categories.

    Args:
      category: Attack family — one of: jailbreak, injection, disclosure,
                excessive_agency, system_prompt_leakage, misinformation,
                output_manipulation.  Pass "random" to pick at random.
      prior_successes: Newline-separated successful attack prompts from
                       get_successful_attack_prompts().  Pass "" for round 1.
      tool_context: ADK tool context.

    Returns:
      {
        "category": str,
        "attacks": [{"attack_prompt": str, "rationale": str}],
        "count": int,
        "fresh_count": int,       # prompts not yet in prior_successes
        "already_tried": int,     # prompts filtered out
        "available_categories": [str],
      }
    """
    library = _load_library()
    categories = _available_categories()

    if category == "random":
        category = random.choice(categories)

    if category not in library:
        return {
            "category": category,
            "attacks": [],
            "count": 0,
            "fresh_count": 0,
            "already_tried": 0,
            "available_categories": categories,
            "error": (
                f"Unknown category '{category}'. "
                f"Available: {', '.join(categories)}"
            ),
        }

    all_attacks: list[dict[str, str]] = library[category]

    # Build set of already-tried prompts from prior_successes string.
    tried: set[str] = set()
    if prior_successes.strip():
        for line in prior_successes.strip().splitlines():
            stripped = line.strip()
            if stripped:
                tried.add(stripped)

    # Partition into fresh (not yet tried) and already tried.
    fresh = [a for a in all_attacks if a["attack_prompt"].strip() not in tried]
    already_tried_count = len(all_attacks) - len(fresh)

    # Return fresh prompts if any; fall back to full set when exhausted.
    attacks_to_return = fresh if fresh else all_attacks

    return {
        "category": category,
        "attacks": attacks_to_return,
        "count": len(attacks_to_return),
        "fresh_count": len(fresh),
        "already_tried": already_tried_count,
        "available_categories": categories,
    }
