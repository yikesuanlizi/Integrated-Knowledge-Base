"""Wiki 卡片浏览 API。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from app.compiler.wiki_md import card_to_markdown
from app.core.log import logger
from app.services.wiki_pg_service import get_pg_wiki_card, list_pg_wiki_cards

router = APIRouter(tags=["wiki"])

_list_pg_cards = list_pg_wiki_cards
_get_pg_card = get_pg_wiki_card


@router.get("/")
async def list_wiki_cards(
    page: int = 1,
    page_size: int = 20,
    card_type: Optional[str] = None,
    status: Optional[str] = None,
):
    """列出 PG Wiki 卡片（按 page/page_size 分页）。"""
    try:
        page_items, total = await _list_pg_cards(page, page_size, card_type=card_type, status=status)
    except Exception as e:
        logger.warning(f"List cards failed: {e}")
        page_items = []
        total = 0

    return {
        "cards": page_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{card_id}")
async def get_wiki_card(card_id: str):
    """获取单张卡片详情。"""
    try:
        card = await _get_pg_card(card_id)
    except Exception as e:
        logger.warning(f"Get card {card_id} failed: {e}")
        card = None

    if not card:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")
    return card


@router.get("/{card_id}/markdown")
async def get_wiki_card_markdown(card_id: str):
    """获取卡片 Markdown 渲染。"""
    try:
        card_data = await _get_pg_card(card_id)
    except Exception as e:
        card_data = None
        logger.warning(f"Get card data {card_id} failed: {e}")

    if not card_data:
        raise HTTPException(status_code=404, detail=f"Card not found: {card_id}")

    try:
        from app.compiler.wiki_cards import json_to_card
        card = json_to_card(card_data)
        markdown = card_to_markdown(card)
    except Exception as e:
        logger.error(f"Render markdown failed: {e}")
        markdown = f"# {card_data.get('title', 'Unknown')}\n\n{card_data.get('content', '')}"

    return {"card_id": card_id, "markdown": markdown, "title": card_data.get("title", "")}


@router.get("/search/fulltext")
async def search_wiki(keyword: str = "", top_k: int = 10, card_type: Optional[str] = None, status: Optional[str] = None):
    """全文搜索 PG Wiki 卡片。"""
    try:
        results, _ = await _list_pg_cards(1, top_k, card_type=card_type, status=status, keyword=keyword)
    except Exception as e:
        logger.warning(f"Search failed: {e}")
        results = []

    return results


@router.get("/types/list")
async def list_card_types():
    """支持的卡片类型。"""
    return {
        "types": [
            {"type": "definition", "description": "定义卡片 - 术语、缩写、规范定义"},
            {"type": "concept", "description": "概念卡片 - 系统、部件、机制说明"},
            {"type": "procedure", "description": "程序卡片 - 维护步骤、检查流程"},
            {"type": "faq", "description": "问答卡片 - 差异、边界、常见问题"},
            {"type": "fault", "description": "故障卡片 - 异常、告警、排故说明"},
        ],
    }
