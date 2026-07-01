"""审核 API：Wiki 卡片人工审核流程。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.log import logger
from app.services.review_service import apply_card_status_to_indexes, apply_card_statuses_to_indexes
from app.services.wiki_pg_service import get_pg_wiki_review_stats, list_pg_wiki_reviews

router = APIRouter(tags=["review"])


class ReviewActionRequest(BaseModel):
    reviewer: str = ""
    notes: str = ""


class BatchReviewActionRequest(ReviewActionRequest):
    review_ids: list[str]


@router.get("/")
async def list_review_queue(
    page: int = 1,
    page_size: int = 20,
    status: str = "review",
):
    """列出审核队列。"""
    reviews, total = await list_pg_wiki_reviews(page, page_size, status=status or None)
    return {"reviews": reviews, "total": total, "page": page, "page_size": page_size}


@router.post("/batch/approve")
async def approve_reviews(body: BatchReviewActionRequest):
    """批量批准审核。"""
    card_ids = [review_id.split(":review")[0] for review_id in body.review_ids]
    result = await apply_card_statuses_to_indexes(card_ids, "approved")
    return {
        "status": "approved",
        "reviewer": body.reviewer or "system",
        "notes": body.notes,
        "updated_at": datetime.now().isoformat(),
        **result,
    }


@router.post("/batch/reject")
async def reject_reviews(body: BatchReviewActionRequest):
    """批量驳回审核。"""
    card_ids = [review_id.split(":review")[0] for review_id in body.review_ids]
    result = await apply_card_statuses_to_indexes(card_ids, "rejected")
    return {
        "status": "rejected",
        "reviewer": body.reviewer or "system",
        "notes": body.notes,
        "updated_at": datetime.now().isoformat(),
        **result,
    }


@router.post("/{review_id}/approve")
async def approve_review(review_id: str, body: ReviewActionRequest):
    """批准审核。"""
    card_id = review_id.split(":review")[0]
    result = await apply_card_status_to_indexes(card_id, "approved")
    return {
        "review_id": review_id,
        "card_id": card_id,
        "status": "approved",
        "reviewer": body.reviewer or "system",
        "notes": body.notes,
        "updated_at": datetime.now().isoformat(),
        "index_sync": result,
    }


@router.post("/{review_id}/reject")
async def reject_review(review_id: str, body: ReviewActionRequest):
    """驳回审核。"""
    card_id = review_id.split(":review")[0]
    result = await apply_card_status_to_indexes(card_id, "rejected")
    return {
        "review_id": review_id,
        "card_id": card_id,
        "status": "rejected",
        "reviewer": body.reviewer or "system",
        "notes": body.notes,
        "updated_at": datetime.now().isoformat(),
        "index_sync": result,
    }


@router.get("/stats/overview")
async def get_review_stats():
    """审核统计。"""
    return await get_pg_wiki_review_stats()
