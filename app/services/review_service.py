from __future__ import annotations

from app.core.log import logger
from app.core.database import AsyncSessionLocal, init_database


async def apply_card_status_to_indexes(card_id: str, status: str) -> dict:
    """Update PG Wiki review status.

    Wiki cards are not stored in ES/Milvus. Source chunk indexes are governed by
    chunk approval, so card review must not mutate chunk retrieval indexes.
    """
    errors: list[str] = []

    try:
        from sqlalchemy import text

        await init_database()
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("UPDATE wiki_cards SET status = :status WHERE card_id = :card_id"),
                {"status": status, "card_id": card_id},
            )
            await session.execute(
                text("UPDATE wiki_reviews SET status = :status WHERE card_id = :card_id"),
                {"status": status, "card_id": card_id},
            )
            linked_rows = await session.execute(
                text("SELECT chunk_id FROM wiki_card_chunks WHERE card_id = :card_id ORDER BY position"),
                {"card_id": card_id},
            )
            linked_chunks = [str(row[0]) for row in linked_rows]
            await session.commit()
    except Exception as exc:  # pragma: no cover - defensive sync path
        linked_chunks = []
        message = f"PG wiki review status update failed for {card_id}: {exc}"
        errors.append(message)
        logger.warning(message)

    return {
        "card_id": card_id,
        "status": status,
        "linked_chunks": linked_chunks,
        "errors": errors,
    }


async def apply_card_statuses_to_indexes(card_ids: list[str], status: str) -> dict:
    unique_card_ids = _dedupe_values(card_ids)
    results: list[dict] = []

    for card_id in unique_card_ids:
        try:
            result = await apply_card_status_to_indexes(card_id, status)
            results.append({**result, "ok": len(result.get("errors", [])) == 0})
        except Exception as exc:
            logger.error(f"Batch apply wiki card status failed for {card_id}: {exc}", exc_info=True)
            results.append(
                {
                    "card_id": card_id,
                    "status": "failed",
                    "linked_chunks": [],
                    "errors": [str(exc)],
                    "ok": False,
                }
            )

    success_count = sum(1 for item in results if item.get("ok"))
    failed_count = len(results) - success_count
    return {
        "total": len(unique_card_ids),
        "status": status,
        "updated_count": success_count,
        "failed_count": failed_count,
        "results": results,
    }


def _dedupe_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
