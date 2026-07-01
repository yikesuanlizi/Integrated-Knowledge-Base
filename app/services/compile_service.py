"""知识编译服务：封装 compile API 的业务逻辑。"""
from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Optional

from app.compiler.pipeline import run_pipeline, to_wiki_cards
from app.compiler.wiki_cards import WikiCard
from app.core.log import logger
from app.models.schemas import Chunk
from app.quality.review_policy import apply_review_policy
from app.services.wiki_pg_service import count_pg_rows, fetch_chunks_for_build, persist_wiki_cards_to_pg


def apply_review_policy_to_cards(cards: list[WikiCard]) -> list[WikiCard]:
    """Apply review policy before cards enter retrievable indexes."""
    reviewed: list[WikiCard] = []
    for card in cards:
        policy = apply_review_policy(card)
        metadata = {
            **(card.metadata or {}),
            "review_policy": {
                "should_hold": policy.should_hold,
                "reasons": policy.reasons,
                "issues": policy.issues,
            },
        }
        reviewed.append(replace(card, status=policy.suggested_status, metadata=metadata))
    return reviewed


async def sync_held_card_chunk_statuses(cards: list[WikiCard]) -> list[dict]:
    """Compatibility no-op.

    Wiki review status belongs to PG Wiki records. It must not mutate ES/Milvus
    chunk indexes; those are controlled by chunk approval.
    """
    return []


class CompileService:
    """知识编译服务，封装两阶段 LLM 编译 pipeline。"""

    def __init__(self):
        pass

    async def compile(self, build_id: Optional[str] = None, force: bool = False) -> dict:
        """触发编译 pipeline，将 chunks 转换为 WikiCards。

        Args:
            build_id: 可选的 build ID。
            force: 是否强制重新编译。

        Returns:
            编译结果 dict。
        """
        build_id = build_id or str(uuid.uuid4())[:16]

        chunks = await self._fetch_chunks(build_id)
        if not chunks:
            return {
                "build_id": build_id,
                "status": "no_chunks",
                "wiki_card_count": 0,
                "linked_chunks": 0,
                "error": f"No chunks for build_id: {build_id}",
            }

        try:
            result = await run_pipeline(chunks, build_id, source_ref=build_id)
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return {
                "build_id": build_id,
                "status": "failed",
                "wiki_card_count": 0,
                "linked_chunks": len(chunks),
                "error": str(e),
            }

        if not result.pages:
            return {
                "build_id": build_id,
                "status": "no_pages",
                "wiki_card_count": 0,
                "linked_chunks": len(chunks),
                "warnings": result.warnings,
            }

        cards = apply_review_policy_to_cards(to_wiki_cards(result.pages, build_id=build_id, source_ref=build_id))

        await self._persist_cards(cards)
        chunk_review_sync = await sync_held_card_chunk_statuses(cards)

        return {
            "build_id": build_id,
            "status": "completed",
            "wiki_card_count": len(cards),
            "linked_chunks": len(chunks),
            "pages": len(result.pages),
            "concepts": len(result.concepts),
            "warnings": result.warnings,
            "errors": result.errors,
            "chunk_review_sync": chunk_review_sync,
        }

    async def get_status(self, build_id: str) -> dict:
        """查询编译状态。

        Args:
            build_id: Build ID。

        Returns:
            状态 dict。
        """
        try:
            count = await count_pg_rows("wiki_cards", "build_id = :build_id", {"build_id": build_id})
        except Exception as e:
            logger.debug(f"PG wiki card count failed: {e}")
            count = 0

        return {
            "build_id": build_id,
            "status": "completed" if count > 0 else "pending",
            "card_count": count,
            "timestamp": datetime.now().isoformat(),
        }

    async def _fetch_chunks(self, build_id: str) -> list[Chunk]:
        """从 PG 真相源拉取指定 build 的 chunks。"""
        try:
            return await fetch_chunks_for_build(build_id)
        except Exception as e:
            logger.warning(f"Fetch PG chunks failed: {e}")
            return []

    async def _persist_cards(self, cards: list[WikiCard]) -> None:
        """Wiki 只写 PG。"""
        build_id = cards[0].source_ref if cards else ""
        await persist_wiki_cards_to_pg(cards, build_id)
