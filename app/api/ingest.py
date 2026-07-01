"""知识摄入 API：上传文件 / 目录批量摄入。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.core.log import logger
from app.ingest.parsers import discover_files
from app.models.schemas import IngestPathRequest, IngestResult
from app.retrieval.es_repo import ElasticsearchRepository
from app.retrieval.milvus_repo import MilvusRepository
from app.services.ingest_service import IngestService
from app.services.wiki_pg_service import count_pg_rows

router = APIRouter(tags=["ingest"])


@router.post("/file")
async def ingest_file(file: UploadFile = File(...), manual_type: str = "", aircraft_model: str = ""):
    """单文件上传摄入。"""
    try:
        contents = await file.read()
        from app.models.schemas import DocumentMetadata

        metadata = DocumentMetadata(manual_type=manual_type or None, aircraft_model=aircraft_model or None)
        result = await IngestService().ingest_file(contents, file.filename or "upload.bin", metadata)
        if result.get("failed"):
            raise HTTPException(status_code=500, detail=result["documents"][0].get("error", "Ingest failed"))
        return IngestResult(path=file.filename or "", **result)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"ingest_file failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")


@router.post("/path")
async def ingest_path(request: IngestPathRequest):
    """目录批量摄入。"""
    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {request.path}")

    files = discover_files(path)
    if not files:
        raise HTTPException(status_code=400, detail=f"No supported files in: {request.path}")
    result = await IngestService().ingest_directory(str(path), force=request.force, metadata=request.metadata, build_id=request.build_id)
    return IngestResult(path=str(path), **result)


@router.get("/status")
async def get_ingest_status():
    """摄入状态查询。"""
    milvus_count = 0
    es_count = 0
    documents = 0
    pg_chunks = 0
    approved_chunks = 0
    review_chunks = 0
    rejected_chunks = 0

    try:
        milvus_repo = MilvusRepository()
        milvus_count = milvus_repo.count()
    except Exception as e:
        logger.debug(f"Milvus count failed: {e}")

    try:
        es_repo = ElasticsearchRepository()
        es_count = await es_repo.count()
    except Exception as e:
        logger.debug(f"ES count failed: {e}")

    try:
        documents = await count_pg_rows("documents")
        pg_chunks = await count_pg_rows("chunks")
        approved_chunks = await count_pg_rows("chunks", "status = 'approved'")
        review_chunks = await count_pg_rows("chunks", "status = 'review'")
        rejected_chunks = await count_pg_rows("chunks", "status = 'rejected'")
    except Exception as e:
        logger.debug(f"PG ingest status count failed: {e}")

    return {
        "milvus_chunks": milvus_count,
        "elasticsearch_chunks": es_count,
        "documents": documents,
        "pg_chunks": pg_chunks,
        "approved_chunks": approved_chunks,
        "review_chunks": review_chunks,
        "rejected_chunks": rejected_chunks,
    }
