"""Orphan page detection."""
from __future__ import annotations

from app.compiler.deps import extract_wikilinks


def find_orphans(pages: dict[str, str], *, roots: set[str] | None = None) -> list[str]:
    roots = roots or set()
    linked: set[str] = set()
    for body in pages.values():
        linked.update(extract_wikilinks(body))
    return sorted(title for title in pages if title not in linked and title not in roots)
