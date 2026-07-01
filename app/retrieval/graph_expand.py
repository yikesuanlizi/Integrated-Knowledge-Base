from __future__ import annotations

import re
from typing import List, Set


WIKILINK_REGEX = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


def extract_wikilinks(text: str) -> List[str]:
    links: List[str] = []
    for match in WIKILINK_REGEX.finditer(text):
        link_text = match.group(1).strip()
        if link_text:
            links.append(link_text)
    return links


def build_wikilink_graph(cards: List[dict]) -> dict[str, List[str]]:
    graph: dict[str, List[str]] = {}

    for card in cards:
        title = card.get("title", "")
        content = card.get("content", "") or ""
        links = extract_wikilinks(content)
        graph[title] = links

    return graph


def expand_graph(
    seed_titles: List[str],
    cards: List[dict],
    hops: int = 2,
) -> List[dict]:
    graph = build_wikilink_graph(cards)

    visited: Set[str] = set(seed_titles)
    frontier = list(seed_titles)

    for _ in range(hops):
        new_frontier: List[str] = []
        for title in frontier:
            if title in graph:
                for linked_title in graph[title]:
                    if linked_title not in visited:
                        visited.add(linked_title)
                        new_frontier.append(linked_title)
        frontier = new_frontier

    expanded_cards: List[dict] = []
    card_by_title: dict[str, dict] = {card.get("title"): card for card in cards}

    for title in visited:
        if title in card_by_title:
            expanded_cards.append(card_by_title[title])

    return expanded_cards


def _keyword_overlap(
    title: str,
    content: str,
    query_text: str,
    query_terms: List[str] | None = None,
) -> float:
    if query_terms is None:
        query_terms = _extract_query_terms(query_text)
    if not query_terms:
        return 0.0
    haystack = f"{title or ''} {content or ''}".lower()
    hit = 0
    for t in query_terms:
        if not t:
            continue
        if t in haystack:
            hit += 1
    return hit / len(query_terms)


def _extract_query_terms(query_text: str, max_terms: int = 8) -> List[str]:
    if not query_text:
        return []
    tokens = [t.strip().strip(".,;:!?\"'()[]{}") for t in query_text.lower().split()]
    tokens = [t for t in tokens if t]
    return tokens[:max_terms]


def _score_card(
    card: dict,
    hop_depth: int,
    query_terms: List[str],
    min_keyword_threshold: float,
) -> tuple[float, float, bool]:
    title = card.get("title", "") or ""
    content = card.get("content", "") or ""
    base_score = float(card.get("score", 1.0) or 1.0)
    keyword_score = _keyword_overlap(title, content, "", query_terms=query_terms)
    depth_decay = 1.0 / (1.0 + float(hop_depth))
    final_score = base_score * depth_decay * (0.5 + keyword_score)
    kept = keyword_score >= min_keyword_threshold
    return final_score, keyword_score, kept


def expand_from_recalled(
    recalled_cards: List[dict],
    all_cards: List[dict],
    query: str = "",
    hops: int = 2,
    max_expand: int = 20,
    min_keyword_threshold: float = 0.1,
) -> List[dict]:
    seed_titles = [card.get("title") for card in recalled_cards if card.get("title")]

    query_terms = _extract_query_terms(query)

    graph = build_wikilink_graph(all_cards)
    card_by_title: dict[str, dict] = {
        card.get("title"): card for card in all_cards if card.get("title")
    }

    title_to_depth: dict[str, int] = {}
    for card in recalled_cards:
        title = card.get("title")
        if title:
            title_to_depth[title] = 0

    frontier: List[str] = []
    visited: Set[str] = set(title_to_depth.keys())
    for title in seed_titles:
        if title in graph:
            for linked_title in graph[title]:
                if linked_title not in visited:
                    visited.add(linked_title)
                    title_to_depth[linked_title] = 1
                    frontier.append(linked_title)

    current_depth = 1
    while frontier and current_depth < hops:
        new_frontier: List[str] = []
        for title in frontier:
            if title not in graph:
                continue
            for linked_title in graph[title]:
                if linked_title in visited:
                    continue
                visited.add(linked_title)
                title_to_depth[linked_title] = current_depth + 1
                new_frontier.append(linked_title)
        frontier = new_frontier
        current_depth += 1

    scored: list[tuple[dict, float, float, int]] = []

    for card in recalled_cards:
        title = card.get("title", "")
        hop_depth = 0
        final_score, keyword_score, kept = _score_card(
            card, hop_depth, query_terms, min_keyword_threshold
        )
        if kept:
            enriched = dict(card)
            enriched["hop_depth"] = hop_depth
            enriched["keyword_overlap"] = keyword_score
            enriched["final_score"] = final_score
            scored.append((enriched, final_score, keyword_score, hop_depth))

    for title, hop_depth in title_to_depth.items():
        if hop_depth == 0:
            continue
        if hop_depth > hops:
            continue
        card = card_by_title.get(title)
        if card is None:
            continue
        final_score, keyword_score, kept = _score_card(
            card, hop_depth, query_terms, min_keyword_threshold
        )
        if not kept:
            continue
        enriched = dict(card)
        enriched["hop_depth"] = hop_depth
        enriched["keyword_overlap"] = keyword_score
        enriched["final_score"] = final_score
        scored.append((enriched, final_score, keyword_score, hop_depth))

    scored.sort(key=lambda x: x[1], reverse=True)
    scored = scored[:max_expand]

    seen: Set[str] = set()
    combined: List[dict] = []
    for enriched, _, _, _ in scored:
        cid = enriched.get("card_id") or enriched.get("title")
        if cid in seen:
            continue
        seen.add(cid)
        combined.append(enriched)

    return combined


def calculate_graph_depth(
    start_title: str,
    target_title: str,
    cards: List[dict],
    max_depth: int = 5,
) -> int:
    graph = build_wikilink_graph(cards)

    if start_title == target_title:
        return 0

    visited: Set[str] = {start_title}
    frontier = [(start_title, 0)]

    while frontier:
        title, depth = frontier.pop(0)
        if depth >= max_depth:
            continue

        if title in graph:
            for linked_title in graph[title]:
                if linked_title == target_title:
                    return depth + 1
                if linked_title not in visited:
                    visited.add(linked_title)
                    frontier.append((linked_title, depth + 1))

    return -1


def find_related_cards(
    card: dict,
    all_cards: List[dict],
    max_hops: int = 2,
    max_results: int = 10,
) -> List[dict]:
    title = card.get("title", "")
    if not title:
        return []

    related = expand_graph([title], all_cards, max_hops)

    related = [c for c in related if c.get("title") != title]

    related.sort(key=lambda x: calculate_graph_depth(title, x.get("title", ""), all_cards))

    return related[:max_results]


def prune_graph(
    cards: List[dict],
    max_nodes: int = 50,
) -> List[dict]:
    if len(cards) <= max_nodes:
        return cards

    card_scores = []
    for card in cards:
        content_length = len(card.get("content", ""))
        link_count = len(extract_wikilinks(card.get("content", "")))
        score = content_length + link_count * 100
        card_scores.append((card, score))

    card_scores.sort(key=lambda x: x[1], reverse=True)

    return [card for card, _ in card_scores[:max_nodes]]
