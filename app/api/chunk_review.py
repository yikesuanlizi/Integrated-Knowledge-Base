from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.database import AsyncSessionLocal
from app.core.log import logger
from app.services.chunk_review_service import approve_chunk, approve_chunks, reject_chunk, reject_chunks

router = APIRouter(tags=["chunk-review"])


class ChunkReviewActionRequest(BaseModel):
    reviewer: str = ""
    notes: str = ""


class ChunkBatchReviewActionRequest(ChunkReviewActionRequest):
    chunk_ids: list[str]


@router.get("/")
async def list_chunk_review_queue(
    page: int = 1,
    page_size: int = 20,
    status: str = "review",
):
    try:
        from sqlalchemy import text

        offset = max(0, (page - 1) * page_size)
        params = {"limit": page_size, "offset": offset}
        where_sql = ""
        if status:
            where_sql = "WHERE c.status = :status"
            params["status"] = status

        async with AsyncSessionLocal() as session:
            total = await session.scalar(
                text(f"SELECT COUNT(*) FROM chunks c {where_sql}"),
                params,
            ) or 0
            rows = (
                await session.execute(
                    text(
                        f"""
                        SELECT
                            c.chunk_id AS review_id,
                            c.chunk_id,
                            c.build_id,
                            c.doc_id,
                            c.status,
                            c.reviewer,
                            c.reviewed_at AS created_at,
                            c.section_path,
                            c.block_type,
                            c.raw_content AS content,
                            d.file_name
                        FROM chunks c
                        LEFT JOIN documents d ON d.doc_id = c.doc_id
                        {where_sql}
                        ORDER BY c.reviewed_at DESC NULLS LAST, c.chunk_index ASC
                        LIMIT :limit OFFSET :offset
                        """
                    ),
                    params,
                )
            ).mappings().all()
    except Exception as e:
        logger.error(f"list_chunk_review_queue failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"List chunk review queue failed: {e}")

    reviews = []
    for row in rows:
        reviews.append(
            {
                "review_id": row.get("review_id") or "",
                "chunk_id": row.get("chunk_id") or "",
                "card_id": row.get("chunk_id") or "",
                "build_id": row.get("build_id") or "",
                "doc_id": row.get("doc_id") or "",
                "file_name": row.get("file_name") or "",
                "status": row.get("status") or "review",
                "reviewer": row.get("reviewer") or "",
                "notes": "",
                "created_at": row.get("created_at") or "",
                "section_path": row.get("section_path") or "",
                "block_type": row.get("block_type") or "",
                "content": row.get("content") or "",
            }
        )

    return {
        "reviews": reviews,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/batch/approve")
async def approve_chunk_reviews(body: ChunkBatchReviewActionRequest):
    try:
        return await approve_chunks(body.chunk_ids, reviewer=body.reviewer, notes=body.notes)
    except Exception as e:
        logger.error(f"approve_chunk_reviews failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch approve chunks failed: {e}")


@router.post("/batch/reject")
async def reject_chunk_reviews(body: ChunkBatchReviewActionRequest):
    try:
        return await reject_chunks(body.chunk_ids, reviewer=body.reviewer, notes=body.notes)
    except Exception as e:
        logger.error(f"reject_chunk_reviews failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch reject chunks failed: {e}")


@router.post("/{chunk_id}/approve")
async def approve_chunk_review(chunk_id: str, body: ChunkReviewActionRequest):
    try:
        return await approve_chunk(chunk_id, reviewer=body.reviewer, notes=body.notes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"approve_chunk_review failed for {chunk_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Approve chunk failed: {e}")


@router.post("/{chunk_id}/reject")
async def reject_chunk_review(chunk_id: str, body: ChunkReviewActionRequest):
    try:
        return await reject_chunk(chunk_id, reviewer=body.reviewer, notes=body.notes)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"reject_chunk_review failed for {chunk_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Reject chunk failed: {e}")


@router.get("/stats/overview")
async def get_chunk_review_stats():
    try:
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            total = await session.scalar(text("SELECT COUNT(*) FROM chunks")) or 0
            pending_review = await session.scalar(text("SELECT COUNT(*) FROM chunks WHERE status = 'review'")) or 0
            approved = await session.scalar(text("SELECT COUNT(*) FROM chunks WHERE status = 'approved'")) or 0
            rejected = await session.scalar(text("SELECT COUNT(*) FROM chunks WHERE status = 'rejected'")) or 0
        return {
            "total": total,
            "pending_review": pending_review,
            "approved": approved,
            "rejected": rejected,
        }
    except Exception as e:
        logger.error(f"get_chunk_review_stats failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chunk review stats failed: {e}")
