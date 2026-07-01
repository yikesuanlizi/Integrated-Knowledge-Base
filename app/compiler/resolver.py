"""Wiki reference resolver."""
from __future__ import annotations

from dataclasses import dataclass

from app.compiler.deps import extract_wikilinks


@dataclass(frozen=True)
class ResolveResult:
    title: str
    links: list[str]
    missing: list[str]


def resolve_wikilinks(pages: dict[str, str]) -> list[ResolveResult]:
    titles = set(pages)
    results: list[ResolveResult] = []
    for title, body in pages.items():
        links = extract_wikilinks(body)
        missing = [link for link in links if link not in titles]
        results.append(ResolveResult(title=title, links=links, missing=missing))
    return results
