"""PG-backed Wiki storage helpers.

Wiki is the knowledge-base body. It lives in PostgreSQL and filesystem
markdown output; ES and Milvus only index approved source chunks.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.compiler.wiki_cards import WikiCard as CompiledWikiCard
from app.core.database import AsyncSessionLocal, init_database
from app.models.documents import Chunk as DbChunk
from app.models.documents import Document, WikiCard, WikiCardChunk, WikiClaim, WikiReview
from app.models.schemas import Chunk, ChunkMetadata


def _value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _fact_to_dict(fact: Any) -> dict[str, Any]:
    if isinstance(fact, dict):
        return {
            "statement": fact.get("statement") or fact.get("fact") or "",
            "source_ref": fact.get("source_ref") or "",
            "confidence": fact.get("confidence", 1.0),
            "page_no": fact.get("page_no"),
        }
    return {
        "statement": getattr(fact, "statement", ""),
        "source_ref": getattr(fact, "source_ref", ""),
        "confidence": getattr(fact, "confidence", 1.0),
        "page_no": getattr(fact, "page_no", None),
    }


async def count_pg_rows(table_name: str, where: str = "", params: dict[str, Any] | None = None) -> int:
    await init_database()
    query = f"SELECT COUNT(*) FROM {table_name}"
    if where:
        query += f" WHERE {where}"
    async with AsyncSessionLocal() as session:
        return await session.scalar(text(query), params or {}) or 0


async def count_wiki_cards_by_status(status: str) -> int:
    return await count_pg_rows("wiki_cards", "status = :status", {"status": status})


async def list_pg_wiki_reviews(
    page: int,
    page_size: int,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    await init_database()
    offset = max(0, (page - 1) * page_size)
    where = []
    params: dict[str, Any] = {"limit": page_size, "offset": offset}
    if status:
        where.append("wr.status = :status")
        params["status"] = status

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    count_sql = text(f"SELECT COUNT(*) FROM wiki_reviews wr {where_sql}")
    data_sql = text(
        f"""
        SELECT
            wr.review_id,
            wr.card_id,
            wc.title AS card_title,
            wc.card_type,
            wc.text AS card_content,
            wc.source_ref,
            wc.confidence,
            wr.status,
            wr.reviewer,
            wr.notes,
            wr.created_at,
            COALESCE(
                array_agg(wcc.chunk_id ORDER BY wcc.position)
                FILTER (WHERE wcc.chunk_id IS NOT NULL),
                ARRAY[]::varchar[]
            ) AS linked_chunks
        FROM wiki_reviews wr
        LEFT JOIN wiki_cards wc ON wc.card_id = wr.card_id
        LEFT JOIN wiki_card_chunks wcc ON wcc.card_id = wr.card_id
        {where_sql}
        GROUP BY wr.review_id, wr.card_id, wc.title, wc.card_type, wc.text, wc.source_ref, wc.confidence, wr.status, wr.reviewer, wr.notes, wr.created_at
        ORDER BY wr.created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )

    async with AsyncSessionLocal() as session:
        total = await session.scalar(count_sql, params) or 0
        rows = (await session.execute(data_sql, params)).mappings().all()

    items = []
    for row in rows:
        items.append(
            {
                "review_id": row.get("review_id") or "",
                "card_id": row.get("card_id") or "",
                "card_title": row.get("card_title") or "",
                "card_type": row.get("card_type") or "",
                "card_content": row.get("card_content") or "",
                "source_ref": row.get("source_ref") or "",
                "confidence": float(row.get("confidence") or 0),
                "linked_chunks": row.get("linked_chunks") or [],
                "status": row.get("status") or "review",
                "reviewer": row.get("reviewer") or "",
                "notes": row.get("notes") or "",
                "created_at": row.get("created_at") or "",
            }
        )
    return items, total


async def get_pg_wiki_review_stats() -> dict[str, int]:
    await init_database()
    async with AsyncSessionLocal() as session:
        total = await session.scalar(text("SELECT COUNT(*) FROM wiki_reviews")) or 0
        pending_review = await session.scalar(text("SELECT COUNT(*) FROM wiki_reviews WHERE status = 'review'")) or 0
        approved = await session.scalar(text("SELECT COUNT(*) FROM wiki_reviews WHERE status = 'approved'")) or 0
        rejected = await session.scalar(text("SELECT COUNT(*) FROM wiki_reviews WHERE status = 'rejected'")) or 0
    return {
        "total": int(total),
        "pending_review": int(pending_review),
        "approved": int(approved),
        "rejected": int(rejected),
    }


async def fetch_chunks_for_build(build_id: str) -> list[Chunk]:
    """Load source chunks for wiki compilation from PG truth tables."""
    await init_database()
    sql = text(
        """
        SELECT
            c.chunk_id,
            c.doc_id,
            c.chunk_index,
            c.raw_content,
            c.search_content,
            c.embedding_content,
            c.page_start,
            c.page_end,
            c.section_path,
            c.block_type,
            d.file_name
        FROM chunks c
        LEFT JOIN documents d ON d.doc_id = c.doc_id
        WHERE c.build_id = :build_id
          AND c.status = 'approved'
        ORDER BY c.doc_id, c.chunk_index
        """
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(sql, {"build_id": build_id})).mappings().all()

    chunks: list[Chunk] = []
    for row in rows:
        page_numbers: list[int] = []
        if row.get("page_start") is not None:
            page_numbers.append(row["page_start"])
        if row.get("page_end") is not None and row.get("page_end") != row.get("page_start"):
            page_numbers.append(row["page_end"])
        chunks.append(
            Chunk(
                chunk_id=row.get("chunk_id") or "",
                doc_id=row.get("doc_id") or "",
                raw_content=row.get("raw_content") or "",
                search_content=row.get("search_content") or row.get("raw_content") or "",
                embedding_content=row.get("embedding_content") or row.get("search_content") or row.get("raw_content") or "",
                source_file=row.get("file_name") or "",
                chunk_index=row.get("chunk_index") or 0,
                metadata=ChunkMetadata(
                    section_path=row.get("section_path"),
                    block_type=row.get("block_type"),
                    page_numbers=page_numbers,
                ),
            )
        )
    return chunks


async def _resolve_doc_id(session, card: CompiledWikiCard, build_id: str) -> str | None:
    source_doc_id = (card.metadata or {}).get("source_doc_id")
    if source_doc_id:
        return str(source_doc_id)
    if card.linked_chunks:
        row = await session.scalar(
            text("SELECT doc_id FROM chunks WHERE chunk_id = ANY(:chunk_ids) LIMIT 1"),
            {"chunk_ids": list(card.linked_chunks)},
        )
        if row:
            return str(row)
    row = await session.scalar(
        text("SELECT doc_id FROM documents WHERE build_id = :build_id ORDER BY doc_id LIMIT 1"),
        {"build_id": build_id},
    )
    return str(row) if row else None


async def persist_wiki_cards_to_pg(cards: list[CompiledWikiCard], build_id: str) -> None:
    """Persist compiled Wiki cards to PG only."""
    if not cards:
        return

    await init_database()
    now = datetime.utcnow().isoformat()

    async with AsyncSessionLocal() as session:
        for card in cards:
            doc_id = await _resolve_doc_id(session, card, build_id)
            if not doc_id:
                continue

            facts = [_fact_to_dict(fact) for fact in card.facts]
            metadata = card.metadata or {}
            status = _value(card.status)

            card_stmt = insert(WikiCard).values(
                card_id=card.card_id,
                build_id=build_id,
                card_type=_value(card.card_type),
                doc_id=doc_id,
                title=card.title,
                text=card.content,
                source_ref=card.source_ref,
                confidence=card.confidence,
                facts_json=facts,
                linked_entities_json=metadata.get("linked_entities", []),
                status=status,
                created_at=card.created_at or now,
            ).on_conflict_do_update(
                index_elements=["card_id"],
                set_={
                    "card_type": _value(card.card_type),
                    "title": card.title,
                    "text": card.content,
                    "source_ref": card.source_ref,
                    "confidence": card.confidence,
                    "facts_json": facts,
                    "linked_entities_json": metadata.get("linked_entities", []),
                    "status": status,
                },
            )
            await session.execute(card_stmt)

            for position, chunk_id in enumerate(card.linked_chunks or []):
                exists = await session.scalar(
                    text("SELECT chunk_id FROM chunks WHERE chunk_id = :chunk_id"),
                    {"chunk_id": chunk_id},
                )
                if not exists:
                    continue
                link_stmt = insert(WikiCardChunk).values(
                    card_id=card.card_id,
                    chunk_id=chunk_id,
                    position=position,
                ).on_conflict_do_update(
                    index_elements=["card_id", "chunk_id"],
                    set_={"position": position},
                )
                await session.execute(link_stmt)

            for index, fact in enumerate(facts):
                statement = str(fact.get("statement") or "").strip()
                if not statement:
                    continue
                linked_chunk = (card.linked_chunks or [None])[0]
                claim_stmt = insert(WikiClaim).values(
                    claim_id=f"{card.card_id}:claim:{index}",
                    build_id=build_id,
                    card_id=card.card_id,
                    doc_id=doc_id,
                    claim_type="fact",
                    claim_text=statement,
                    source_ref=fact.get("source_ref") or card.source_ref,
                    source_chunk_id=linked_chunk,
                    confidence=float(fact.get("confidence") or card.confidence or 0.6),
                    created_at=now,
                ).on_conflict_do_update(
                    index_elements=["claim_id"],
                    set_={
                        "claim_text": statement,
                        "source_ref": fact.get("source_ref") or card.source_ref,
                        "confidence": float(fact.get("confidence") or card.confidence or 0.6),
                    },
                )
                await session.execute(claim_stmt)

            review_stmt = insert(WikiReview).values(
                review_id=f"{card.card_id}:review",
                build_id=build_id,
                card_id=card.card_id,
                status=status,
                reviewer="system",
                notes="; ".join((metadata.get("review_policy") or {}).get("reasons", [])),
                created_at=now,
            ).on_conflict_do_update(
                index_elements=["review_id"],
                set_={"status": status, "notes": "; ".join((metadata.get("review_policy") or {}).get("reasons", []))},
            )
            await session.execute(review_stmt)

        await session.execute(
            text(
                """
                UPDATE builds
                SET wiki_card_count = (
                    SELECT COUNT(*) FROM wiki_cards WHERE build_id = :build_id
                )
                WHERE build_id = :build_id
                """
            ),
            {"build_id": build_id},
        )
        await session.commit()


def _row_to_card_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_id": row.get("card_id") or "",
        "build_id": row.get("build_id") or "",
        "card_type": row.get("card_type") or "",
        "title": row.get("title") or "",
        "content": row.get("text") or "",
        "text": row.get("text") or "",
        "source_ref": row.get("source_ref") or "",
        "confidence": float(row.get("confidence") or 0),
        "status": row.get("status") or "",
        "facts": row.get("facts_json") or [],
        "linked_chunks": row.get("linked_chunks") or [],
        "metadata": {},
        "created_at": row.get("created_at") or "",
        "score": float(row.get("score") or 1.0),
    }


async def list_pg_wiki_cards(
    page: int,
    page_size: int,
    card_type: str | None = None,
    status: str | None = None,
    keyword: str = "",
) -> tuple[list[dict[str, Any]], int]:
    await init_database()
    offset = max(0, (page - 1) * page_size)
    where: list[str] = []
    params: dict[str, Any] = {"limit": page_size, "offset": offset}
    if card_type:
        where.append("wc.card_type = :card_type")
        params["card_type"] = card_type
    if status:
        where.append("wc.status = :status")
        params["status"] = status
    if keyword:
        where.append("(wc.title ILIKE :keyword OR wc.text ILIKE :keyword OR wc.card_type ILIKE :keyword)")
        params["keyword"] = f"%{keyword}%"

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    count_sql = text(f"SELECT COUNT(*) FROM wiki_cards wc {where_sql}")
    data_sql = text(
        f"""
        SELECT
            wc.*,
            COALESCE(
                array_agg(wcc.chunk_id ORDER BY wcc.position)
                FILTER (WHERE wcc.chunk_id IS NOT NULL),
                ARRAY[]::varchar[]
            ) AS linked_chunks
        FROM wiki_cards wc
        LEFT JOIN wiki_card_chunks wcc ON wcc.card_id = wc.card_id
        {where_sql}
        GROUP BY wc.card_id
        ORDER BY wc.created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    async with AsyncSessionLocal() as session:
        total = await session.scalar(count_sql, params) or 0
        rows = (await session.execute(data_sql, params)).mappings().all()

    return [_row_to_card_dict(dict(row)) for row in rows], total


async def get_pg_wiki_card(card_id: str) -> dict[str, Any] | None:
    await init_database()
    sql = text(
        """
        SELECT
            wc.*,
            COALESCE(
                array_agg(wcc.chunk_id ORDER BY wcc.position)
                FILTER (WHERE wcc.chunk_id IS NOT NULL),
                ARRAY[]::varchar[]
            ) AS linked_chunks
        FROM wiki_cards wc
        LEFT JOIN wiki_card_chunks wcc ON wcc.card_id = wc.card_id
        WHERE wc.card_id = :card_id
        GROUP BY wc.card_id
        """
    )
    async with AsyncSessionLocal() as session:
        row = (await session.execute(sql, {"card_id": card_id})).mappings().first()
    return _row_to_card_dict(dict(row)) if row else None
