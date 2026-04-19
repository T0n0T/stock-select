from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from stock_select.reviewers import review_b1_symbol_history, review_b2_symbol_history, review_symbol_history

ReviewHistoryFn = Callable[..., dict[str, Any]]

_REFERENCE_DIR = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "stock-select" / "references"
DEFAULT_PROMPT_PATH = str(_REFERENCE_DIR / "prompt.md")
B1_PROMPT_PATH = str(_REFERENCE_DIR / "prompt-b1.md")
B2_PROMPT_PATH = str(_REFERENCE_DIR / "prompt-b2.md")


@dataclass(frozen=True)
class ReviewResolver:
    name: str
    prompt_path: str
    review_history: ReviewHistoryFn


def get_review_resolver(method: str) -> ReviewResolver:
    normalized = method.strip().lower()
    if normalized == "b1":
        return ReviewResolver(
            name="b1",
            prompt_path=B1_PROMPT_PATH,
            review_history=review_b1_symbol_history,
        )
    if normalized == "b2":
        return ReviewResolver(
            name="b2",
            prompt_path=B2_PROMPT_PATH,
            review_history=review_b2_symbol_history,
        )
    return ReviewResolver(
        name="default",
        prompt_path=DEFAULT_PROMPT_PATH,
        review_history=lambda **kwargs: review_symbol_history(method=normalized or "default", **kwargs),
    )
