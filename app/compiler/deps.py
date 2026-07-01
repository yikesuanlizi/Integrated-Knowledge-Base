"""Wiki link dependency helpers."""
from __future__ import annotations

import re
from collections import defaultdict, deque

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def extract_wikilinks(text: str) -> list[str]:
    return [match.strip() for match in WIKILINK_RE.findall(text or "") if match.strip()]


def dependency_graph(pages: dict[str, str]) -> dict[str, list[str]]:
    return {title: extract_wikilinks(body) for title, body in pages.items()}


def dependency_order(pages: dict[str, str]) -> list[str]:
    graph = dependency_graph(pages)
    indegree = {title: 0 for title in pages}
    reverse: dict[str, list[str]] = defaultdict(list)
    for title, deps in graph.items():
        for dep in deps:
            if dep in pages:
                indegree[title] += 1
                reverse[dep].append(title)

    queue = deque([title for title, degree in indegree.items() if degree == 0])
    ordered: list[str] = []
    while queue:
        title = queue.popleft()
        ordered.append(title)
        for child in reverse.get(title, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    return ordered + [title for title in pages if title not in ordered]
