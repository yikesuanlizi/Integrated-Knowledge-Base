"""Corpus-backed fixed eval fixtures for the current knowledge base."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, init_database


async def load_eval_fixtures(build_id: str = "") -> dict[str, Any]:
    """Build a stable eval set from currently approved cards/chunks.

    We prefer the current corpus over old hard-coded sample filenames so the
    frontend always reflects the fixed documents that are actually loaded now.
    """
    await init_database()

    cards = await _load_candidate_cards(build_id, limit=5)
    cases: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row in cards:
        title = str(row.get("title") or "").strip()
        content = str(row.get("text") or "").strip()
        question = _build_question(title, row.get("card_type"), content)
        expected_card_ids = [str(row.get("card_id"))] if row.get("card_id") else []
        expected_doc_ids = [str(row.get("doc_id"))] if row.get("doc_id") else []
        linked_chunks = [chunk_id for chunk_id in (row.get("linked_chunks") or []) if chunk_id]

        if not question:
            continue

        cases.append(
            {
                "question": question,
                "expected_doc_ids": expected_doc_ids,
                "expected_chunk_ids": linked_chunks,
                "expected_card_ids": expected_card_ids,
                "intent": _intent_for_type(str(row.get("card_type") or "")),
                "tags": ["corpus", str(row.get("card_type") or "unknown")],
                "source_doc_hint": str(row.get("file_name") or row.get("doc_id") or ""),
                "source_file_name": str(row.get("file_name") or ""),
            }
        )

    if not cases:
        warnings.append("当前知识库里没有可用于固定测评的已通过 Wiki 卡片。")

    return {
        "source": "corpus" if cases else "fallback",
        "questions": [case["question"] for case in cases],
        "retrieval_cases": cases,
        "warnings": warnings,
    }


async def _load_candidate_cards(build_id: str, limit: int = 5) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"limit": limit}
    build_clause = ""
    if build_id:
        build_clause = "AND wc.build_id = :build_id"
        params["build_id"] = build_id

    query = text(
        f"""
        SELECT
            wc.card_id,
            wc.doc_id,
            wc.card_type,
            wc.title,
            wc.text,
            d.file_name,
            COALESCE(
                array_agg(wcc.chunk_id ORDER BY wcc.position)
                FILTER (WHERE wcc.chunk_id IS NOT NULL),
                ARRAY[]::varchar[]
            ) AS linked_chunks
        FROM wiki_cards wc
        LEFT JOIN documents d ON d.doc_id = wc.doc_id
        LEFT JOIN wiki_card_chunks wcc ON wcc.card_id = wc.card_id
        WHERE wc.status = 'approved'
        {build_clause}
        GROUP BY wc.card_id, wc.doc_id, wc.card_type, wc.title, wc.text, d.file_name
        ORDER BY wc.created_at DESC
        LIMIT :limit
        """
    )

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(query, params)).mappings().all()
    return [dict(row) for row in rows]


def _build_question(title: str, card_type: Any, content: str) -> str:
    normalized_title = title.strip().strip("：:。")
    card_type_text = str(card_type or "")
    if not normalized_title:
        return ""
    if card_type_text == "procedure":
        return f"{normalized_title}的步骤是什么？"
    if card_type_text == "fault":
        return f"{normalized_title}应该如何处理？"
    if card_type_text == "definition":
        return f"{normalized_title}是什么意思？"
    if card_type_text == "faq":
        return f"{normalized_title}的关键结论是什么？"
    if "## 关键事实" in content or "## 概述" in content:
        return f"{normalized_title}是什么？"
    return f"请介绍一下{normalized_title}。"


def _intent_for_type(card_type: str) -> str:
    if card_type == "procedure":
        return "procedure"
    if card_type == "fault":
        return "fault"
    if card_type in {"definition", "concept"}:
        return "concept"
    return "general"
