"""Prompt budgeting helpers."""
from __future__ import annotations


def trim_to_budget(text: str, max_chars: int, *, marker: str = "\n\n[TRUNCATED_FOR_PROMPT_BUDGET]\n") -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    marker_budget = min(len(marker), max_chars)
    keep = max_chars - marker_budget
    if keep <= 0:
        return marker[:max_chars]
    head = keep // 2
    tail = keep - head
    return f"{text[:head]}{marker[:marker_budget]}{text[-tail:]}"
