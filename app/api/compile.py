"""知识编译 API：从 chunks 生成结构化 Wiki 卡片。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.compiler.pipeline import run_pipeline, to_wiki_cards
from app.compiler.wiki_md import compile_wiki_markdown
from app.core.log import logger
from app.models.schemas import CompileRequest, CompileResult
from app.services.compile_service import apply_review_policy_to_cards
from app.services.wiki_pg_service import count_pg_rows as _count_pg_rows
from app.services.wiki_pg_service import fetch_chunks_for_build, persist_wiki_cards_to_pg

router = APIRouter(tags=["compile"])


@router.post("/")
async def compile_knowledge(request: CompileRequest, background_tasks: BackgroundTasks):
    """触发编译 pipeline。"""
    build_id = request.build_id or str(uuid.uuid4())[:16]

    chunks = await _fetch_chunks(build_id)
    if not chunks:
        raise HTTPException(status_code=404, detail=f"No chunks for build_id: {build_id}")

    # 异步执行 pipeline
    try:
        result = await run_pipeline(chunks, build_id, source_ref=build_id)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {e}")

    if not result.pages:
        raise HTTPException(status_code=422, detail="Pipeline produced no pages")

    cards = apply_review_policy_to_cards(to_wiki_cards(result.pages, build_id=build_id, source_ref=build_id))

    # 持久化（后台）
    background_tasks.add_task(_persist_cards, cards, build_id)

    # 写 Markdown
    output_dir = _get_wiki_output_dir(build_id)
    background_tasks.add_task(compile_wiki_markdown, cards, output_dir)

    return CompileResult(
        build_id=build_id,
        status="completed",
        wiki_card_count=len(cards),
        linked_chunks=len(chunks),
    )


@router.get("/{build_id}")
async def get_compile_status(build_id: str):
    """查询编译状态。"""
    try:
        count = await _count_pg_rows("wiki_cards", "build_id = :build_id", {"build_id": build_id})
    except Exception:
        count = 0

    return {
        "build_id": build_id,
        "status": "completed" if count > 0 else "pending",
        "card_count": count,
        "timestamp": datetime.now().isoformat(),
    }


async def _fetch_chunks(build_id: str) -> list:
    """从 PG 真相源拉取指定 build 的 chunks。"""
    try:
        return await fetch_chunks_for_build(build_id)
    except Exception as e:
        logger.warning(f"Fetch PG chunks failed: {e}")
        return []


async def _persist_cards(cards: list, build_id: str) -> None:
    """后台任务：Wiki 只写 PG。"""
    try:
        await persist_wiki_cards_to_pg(cards, build_id)
    except Exception as e:
        logger.warning(f"Persist wiki cards to PG failed: {e}", exc_info=True)


def _get_wiki_output_dir(build_id: str) -> Path:
    output_dir = Path(f"wiki_output/{build_id}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir
