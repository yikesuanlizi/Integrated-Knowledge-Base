"""Helpers for corpus-aware evaluation query selection."""
from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.log import logger


def _normalize_query(value: str) -> str:
    text_value = re.sub(r"\s+", " ", (value or "")).strip()
    text_value = re.sub(r"^[#*\-\d\.\)\s]+", "", text_value)
    return text_value[:48].strip()


def _dedupe_keep_order(values: Iterable[str], limit: int) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for raw in values:
        value = _normalize_query(raw)
        if len(value) < 4 or value in seen:
            continue
        seen.add(value)
        items.append(value)
        if len(items) >= limit:
            break
    return items


async def load_eval_queries(build_id: str = "", limit: int = 5, fallback: list[str] | None = None) -> list[str]:
    """Load smoke-eval queries from the current corpus when possible.

    Priority:
    1. Approved wiki card titles for the given build/current corpus
    2. Approved chunk section paths
    3. Approved chunk raw content prefixes
    4. Provided fallback queries
    """
    fallback = fallback or []

    try:
        async with AsyncSessionLocal() as session:
            params = {"limit": max(limit * 2, 10)}
            build_clause = ""
            if build_id:
                build_clause = "AND build_id = :build_id"
                params["build_id"] = build_id

            card_rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT title
                        FROM wiki_cards
                        WHERE status = 'approved'
                        {build_clause}
                        ORDER BY created_at DESC
                        LIMIT :limit
                        """
                    ),
                    params,
                )
            ).scalars().all()
            queries = _dedupe_keep_order(card_rows, limit)
            if len(queries) >= limit:
                return queries

            chunk_rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT COALESCE(section_path, ''), COALESCE(raw_content, '')
                        FROM chunks
                        WHERE status = 'approved'
                        {build_clause}
                        ORDER BY created_at DESC NULLS LAST, chunk_index DESC
                        LIMIT :limit
                        """
                    ),
                    params,
                )
            ).all()

            section_queries = _dedupe_keep_order([row[0] for row in chunk_rows if row[0]], limit)
            content_queries = _dedupe_keep_order([row[1] for row in chunk_rows if row[1]], limit)
            merged = _dedupe_keep_order([*queries, *section_queries, *content_queries, *fallback], limit)
            return merged or _dedupe_keep_order(fallback, limit)
    except Exception as exc:
        logger.debug(f"Load eval queries failed: {exc}")
        return _dedupe_keep_order(fallback, limit)
