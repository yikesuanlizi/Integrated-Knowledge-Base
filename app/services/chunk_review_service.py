from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, init_database
from app.core.log import logger
from app.models.schemas import Chunk, ChunkMetadata, DocumentMetadata
from app.services.compile_service import CompileService
from app.services.ingest_service import IngestService


async def approve_chunk(chunk_id: str, reviewer: str = "", notes: str = "") -> dict:
    chunk_info = await _mark_chunk_status(chunk_id, "approved", reviewer, notes)
    index_result = await _index_single_chunk(chunk_id)
    compile_result = None
    build_id = chunk_info.get("build_id")
    if build_id:
        compile_result = await _auto_compile_build(build_id)
    return {
        **chunk_info,
        "index_result": index_result,
        "compile_result": compile_result,
    }


async def reject_chunk(chunk_id: str, reviewer: str = "", notes: str = "") -> dict:
    return await _mark_chunk_status(chunk_id, "rejected", reviewer, notes)


async def approve_chunks(chunk_ids: list[str], reviewer: str = "", notes: str = "") -> dict:
    unique_chunk_ids = _dedupe_values(chunk_ids)
    results: list[dict] = []
    build_ids: list[str] = []

    for chunk_id in unique_chunk_ids:
        try:
            chunk_info = await _mark_chunk_status(chunk_id, "approved", reviewer, notes)
            index_result = await _index_single_chunk(chunk_id)
            build_id = str(chunk_info.get("build_id") or "").strip()
            if build_id:
                build_ids.append(build_id)
            results.append(
                {
                    **chunk_info,
                    "index_result": index_result,
                    "ok": True,
                }
            )
        except Exception as exc:
            logger.error(f"Batch approve chunk failed for {chunk_id}: {exc}", exc_info=True)
            results.append(
                {
                    "chunk_id": chunk_id,
                    "status": "failed",
                    "ok": False,
                    "error": str(exc),
                }
            )

    compile_results: list[dict] = []
    for build_id in _dedupe_values(build_ids):
        compile_results.append(await _auto_compile_build(build_id))

    approved_count = sum(1 for item in results if item.get("ok"))
    failed_count = len(results) - approved_count
    return {
        "total": len(unique_chunk_ids),
        "approved_count": approved_count,
        "failed_count": failed_count,
        "results": results,
        "compile_results": compile_results,
    }


async def reject_chunks(chunk_ids: list[str], reviewer: str = "", notes: str = "") -> dict:
    unique_chunk_ids = _dedupe_values(chunk_ids)
    results: list[dict] = []

    for chunk_id in unique_chunk_ids:
        try:
            results.append(
                {
                    **(await _mark_chunk_status(chunk_id, "rejected", reviewer, notes)),
                    "ok": True,
                }
            )
        except Exception as exc:
            logger.error(f"Batch reject chunk failed for {chunk_id}: {exc}", exc_info=True)
            results.append(
                {
                    "chunk_id": chunk_id,
                    "status": "failed",
                    "ok": False,
                    "error": str(exc),
                }
            )

    rejected_count = sum(1 for item in results if item.get("ok"))
    failed_count = len(results) - rejected_count
    return {
        "total": len(unique_chunk_ids),
        "rejected_count": rejected_count,
        "failed_count": failed_count,
        "results": results,
        "compile_results": [],
    }


async def _mark_chunk_status(chunk_id: str, status: str, reviewer: str, notes: str = "") -> dict:
    await init_database()
    reviewed_at = datetime.utcnow().isoformat()

    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                text(
                    """
                    UPDATE chunks
                    SET status = :status,
                        reviewer = :reviewer,
                        reviewed_at = :reviewed_at
                    WHERE chunk_id = :chunk_id
                    RETURNING chunk_id, build_id, doc_id, status, reviewer, reviewed_at
                    """
                ),
                {
                    "chunk_id": chunk_id,
                    "status": status,
                    "reviewer": reviewer,
                    "reviewed_at": reviewed_at,
                },
            )
        ).mappings().first()

        if not row:
            raise ValueError(f"Chunk not found: {chunk_id}")

        await session.commit()

    return {
        "chunk_id": row["chunk_id"],
        "build_id": row["build_id"],
        "doc_id": row["doc_id"],
        "status": row["status"],
        "reviewer": row["reviewer"] or "",
        "reviewed_at": row["reviewed_at"],
        "notes": notes,
    }


async def _index_single_chunk(chunk_id: str) -> dict:
    await init_database()
    sql = text(
        """
        SELECT
            c.chunk_id,
            c.build_id,
            c.doc_id,
            c.chunk_index,
            c.raw_content,
            c.search_content,
            c.embedding_content,
            c.page_start,
            c.page_end,
            c.section_path,
            c.block_type,
            c.status,
            d.file_name,
            d.manual_type,
            d.aircraft_model,
            d.engine_model,
            d.ata_chapter,
            d.manual_revision,
            d.effective_date,
            d.applicability,
            d.language,
            d.confidentiality
        FROM chunks c
        LEFT JOIN documents d ON d.doc_id = c.doc_id
        WHERE c.chunk_id = :chunk_id
        LIMIT 1
        """
    )

    async with AsyncSessionLocal() as session:
        row = (await session.execute(sql, {"chunk_id": chunk_id})).mappings().first()

    if not row:
        raise ValueError(f"Chunk not found: {chunk_id}")
    if row.get("status") != "approved":
        return {
            "chunk_id": chunk_id,
            "status": row.get("status") or "unknown",
            "indexed": False,
            "reason": "chunk_not_approved",
        }

    page_numbers: list[int] = []
    if row.get("page_start") is not None:
        page_numbers.append(int(row["page_start"]))
    if row.get("page_end") is not None and row.get("page_end") != row.get("page_start"):
        page_numbers.append(int(row["page_end"]))

    chunk = Chunk(
        chunk_id=row["chunk_id"],
        doc_id=row["doc_id"] or row["build_id"] or "",
        raw_content=row.get("raw_content") or "",
        search_content=row.get("search_content") or row.get("raw_content") or "",
        embedding_content=row.get("embedding_content") or row.get("search_content") or row.get("raw_content") or "",
        source_file=row.get("file_name") or "",
        chunk_index=row.get("chunk_index") or 0,
        metadata=ChunkMetadata(
            block_type=row.get("block_type"),
            section_path=row.get("section_path"),
            page_numbers=page_numbers,
        ),
    )
    metadata = DocumentMetadata(
        manual_type=row.get("manual_type"),
        aircraft_model=row.get("aircraft_model"),
        engine_model=row.get("engine_model"),
        ata_chapter=row.get("ata_chapter"),
        manual_revision=row.get("manual_revision"),
        effective_date=row.get("effective_date"),
        applicability=row.get("applicability"),
        language=row.get("language"),
        confidentiality=row.get("confidentiality"),
    )

    ingest_service = IngestService()
    await ingest_service._store_chunks(
        [chunk],
        row.get("build_id") or chunk.doc_id,
        metadata,
        {chunk.chunk_id: {"status": "approved", "reviewer": "manual", "reviewed_at": datetime.utcnow().isoformat()}},
    )

    return {
        "chunk_id": chunk_id,
        "build_id": row.get("build_id"),
        "status": "approved",
        "indexed": True,
    }


async def _auto_compile_build(build_id: str) -> dict:
    try:
        return await CompileService().compile(build_id=build_id)
    except Exception as e:  # pragma: no cover - defensive path
        logger.warning(f"Auto compile after chunk approval failed for build {build_id}: {e}", exc_info=True)
        return {
            "status": "failed",
            "build_id": build_id,
            "error": str(e),
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
