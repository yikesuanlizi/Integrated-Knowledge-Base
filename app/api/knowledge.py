"""知识库总览 API：提供文档/chunk/card/entity/索引状态的全景统计。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.clients.es_client import es_client_manager
from app.clients.minio_client import minio_client_manager
from app.core.database import AsyncSessionLocal
from app.core.log import logger
from app.retrieval.es_repo import ElasticsearchRepository, EntityESRepository, WikiCardESRepository
from app.retrieval.milvus_repo import MilvusRepository, WikiCardMilvusRepository
from app.services.wiki_pg_service import count_wiki_cards_by_status

router = APIRouter(tags=["knowledge"])


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------


class ReviewCounts(BaseModel):
    pending: int = 0
    approved: int = 0
    rejected: int = 0


class IndexCounts(BaseModel):
    milvus_chunks: int = 0
    es_chunks: int = 0
    es_entities: int = 0


class QaReady(BaseModel):
    approved_cards: int = 0
    approved_chunks: int = 0


class KnowledgeOverview(BaseModel):
    """知识库全景统计。"""

    documents: int = 0
    chunks: int = 0
    wiki_cards: int = 0
    entities: int = 0
    reviews: ReviewCounts = ReviewCounts()
    indexes: IndexCounts = IndexCounts()
    qa_ready: QaReady = QaReady()


class ChunkItem(BaseModel):
    """单个原文切块。"""

    chunk_id: str
    doc_id: str
    content: str
    source_file: str = ""
    section_path: str = ""
    block_type: str = ""
    page_numbers: list[int] | None = None
    status: str = ""
    score: float = 0.0


class ChunkListResponse(BaseModel):
    chunks: list[ChunkItem]
    total: int
    page: int
    page_size: int


class EntityItem(BaseModel):
    """单个实体。"""

    entity_type: str
    value: str
    chunk_ids: list[str] = []
    doc_ids: list[str] = []
    source_files: list[str] = []
    count: int = 0
    score: float = 0.0


class EntityListResponse(BaseModel):
    entities: list[EntityItem]
    total: int
    page: int
    page_size: int


class DocumentItem(BaseModel):
    """单个文档。"""

    doc_id: str
    file_name: str
    source_path: str
    manual_type: str = ""
    aircraft_model: str = ""
    engine_model: str = ""
    ata_chapter: str = ""
    manual_revision: str = ""
    effective_date: str = ""
    applicability: str = ""
    language: str = ""
    confidentiality: str = ""
    parser_name: str = ""
    parser_version: str = ""
    created_at: str = ""
    chunk_count: int = 0
    card_count: int = 0


class DocumentListResponse(BaseModel):
    documents: list[DocumentItem]
    total: int
    page: int
    page_size: int


class IndexStatus(BaseModel):
    """索引健康状态。"""

    milvus: dict | None = None
    elasticsearch: dict | None = None
    postgres: dict | None = None
    nl2sql: dict | None = None


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _load_review_counts() -> ReviewCounts:
    """从 PG Wiki 卡片加载审核统计。"""
    try:
        return ReviewCounts(
            pending=await _count_pg_by_status("wiki_cards", "review"),
            approved=await _count_pg_by_status("wiki_cards", "approved"),
            rejected=await _count_pg_by_status("wiki_cards", "rejected"),
        )
    except Exception as e:
        logger.debug(f"Review stats failed: {e}")
    return ReviewCounts()


async def _load_index_counts() -> tuple[int, int, int]:
    """加载检索索引数量。返回 (milvus_chunks, es_chunks, es_entities)。"""
    milvus_chunks = es_chunks = es_entities = 0

    try:
        milvus_repo = MilvusRepository()
        milvus_chunks = milvus_repo.count()
    except Exception as e:
        logger.debug(f"Milvus chunk count failed: {e}")

    try:
        es_repo = ElasticsearchRepository()
        es_chunks = await es_repo.count()
    except Exception as e:
        logger.debug(f"ES chunk count failed: {e}")

    try:
        entity_repo = EntityESRepository()
        await entity_repo.create_index()
        es_entities = await entity_repo.count()
    except Exception as e:
        logger.debug(f"ES entities count failed: {e}")

    return milvus_chunks, es_chunks, es_entities


async def _count_pg_table(table_name: str) -> int:
    try:
        if not await _table_exists_raw(table_name):
            return 0
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            return await session.scalar(text(f"SELECT COUNT(*) FROM {table_name}")) or 0
    except Exception as e:
        logger.debug(f"PG count failed for {table_name}: {e}")
        return 0


async def _count_pg_by_status(table_name: str, status: str) -> int:
    try:
        if table_name == "wiki_cards":
            return await count_wiki_cards_by_status(status)
        if not await _table_exists_raw(table_name):
            return 0
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            return await session.scalar(text(f"SELECT COUNT(*) FROM {table_name} WHERE status = :status"), {"status": status}) or 0
    except Exception as e:
        logger.debug(f"PG status count failed for {table_name}/{status}: {e}")
        return 0


async def _count_documents_from_es() -> int:
    try:
        es_repo = ElasticsearchRepository()
        results = await es_repo.search("", top_k=1000)
        return len({hit.get("source_file") or hit.get("doc_id") for hit in results if hit.get("source_file") or hit.get("doc_id")})
    except Exception as e:
        logger.debug(f"ES document fallback count failed: {e}")
        return 0


async def _list_documents_from_es(keyword: str, page: int, page_size: int) -> DocumentListResponse:
    try:
        es_repo = ElasticsearchRepository()
        results = await es_repo.search(keyword, top_k=1000)
    except Exception as e:
        logger.debug(f"ES document fallback list failed: {e}")
        return DocumentListResponse(documents=[], total=0, page=page, page_size=page_size)

    grouped: dict[str, dict[str, Any]] = {}
    for hit in results:
        source_file = hit.get("source_file") or ""
        doc_id = hit.get("doc_id") or source_file
        key = source_file or doc_id
        if not key:
            continue
        if key not in grouped:
            grouped[key] = {
                "doc_id": doc_id,
                "file_name": source_file or doc_id,
                "source_path": source_file or doc_id,
                "chunk_count": 0,
            }
        grouped[key]["chunk_count"] += 1

    docs = list(grouped.values())
    total = len(docs)
    start = (page - 1) * page_size
    page_docs = docs[start:start + page_size]

    return DocumentListResponse(
        documents=[
            DocumentItem(
                doc_id=item["doc_id"],
                file_name=item["file_name"],
                source_path=item["source_path"],
                chunk_count=item["chunk_count"],
            )
            for item in page_docs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def _table_exists_raw(table_name: str) -> bool:
    """检查表是否存在（直接建连接，不依赖 request scope）。"""
    try:
        from app.core.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_name = :table_name LIMIT 1"),
                {"table_name": table_name},
            )
            return result.scalar() is not None
    except Exception:
        return False


async def _drop_table_if_exists(session, table_name: str) -> None:
    if await _table_exists_raw(table_name):
        from sqlalchemy import text

        await session.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))


def _safe_remove_path(path: str) -> None:
    p = Path(path)
    if p.exists():
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                p.unlink()
            except Exception:
                pass


@router.post("/reset")
async def reset_knowledge_storage():
    """清空知识库测试数据与索引。"""
    result: dict[str, Any] = {"ok": True, "steps": []}

    try:
        async with AsyncSessionLocal() as session:
            for table in [
                "chunk_parse_blocks",
                "wiki_card_chunks",
                "wiki_claims",
                "wiki_reviews",
                "parse_blocks",
                "parse_artifacts",
                "ingest_jobs",
                "build_documents",
                "chunks",
                "wiki_cards",
                "documents",
                "builds",
                "nl2sql_value_info",
                "nl2sql_metric_info",
                "nl2sql_column_info",
                "nl2sql_table_info",
            ]:
                try:
                    await _drop_table_if_exists(session, table)
                    result["steps"].append({"layer": "postgres", "table": table, "ok": True})
                except Exception as exc:
                    result["steps"].append({"layer": "postgres", "table": table, "ok": False, "error": str(exc)})
            await session.commit()
        from app.core.database import init_database

        await init_database()
    except Exception as exc:
        result["ok"] = False
        result["steps"].append({"layer": "postgres", "ok": False, "error": str(exc)})

    for repo_cls, label in [
        (MilvusRepository, "milvus_chunks"),
        (WikiCardMilvusRepository, "milvus_wiki"),
    ]:
        try:
            repo = repo_cls()
            repo.clear()
            result["steps"].append({"layer": label, "ok": True})
        except Exception as exc:
            result["ok"] = False
            result["steps"].append({"layer": label, "ok": False, "error": str(exc)})

    for repo_cls, label in [
        (ElasticsearchRepository, "es_chunks"),
        (WikiCardESRepository, "es_wiki"),
        (EntityESRepository, "es_entities"),
    ]:
        try:
            repo = repo_cls()
            await repo.clear()
            result["steps"].append({"layer": label, "ok": True})
        except Exception as exc:
            result["ok"] = False
            result["steps"].append({"layer": label, "ok": False, "error": str(exc)})

    try:
        bucket = getattr(minio_client_manager, "_bucket_name", "rag-bucket")
        minio_client_manager.clear_bucket()
        result["steps"].append({"layer": "minio", "bucket": bucket, "ok": True})
    except Exception as exc:
        result["ok"] = False
        result["steps"].append({"layer": "minio", "ok": False, "error": str(exc)})

    for path in ["wiki_output/review_store.json", "wiki_output/activity_log", "wiki_output/exports", "wiki_output/refresh"]:
        try:
            _safe_remove_path(path)
            result["steps"].append({"layer": "filesystem", "path": path, "ok": True})
        except Exception as exc:
            result["ok"] = False
            result["steps"].append({"layer": "filesystem", "path": path, "ok": False, "error": str(exc)})

    return result


# ---------------------------------------------------------------------------
# 接口
# ---------------------------------------------------------------------------


@router.get("/overview", response_model=KnowledgeOverview)
async def get_knowledge_overview():
    """知识库总览：聚合所有存储层的资产统计。"""
    milvus_chunks, es_chunks, es_entities = await _load_index_counts()
    reviews = await _load_review_counts()
    documents = await _count_pg_table("documents")
    if documents == 0 and es_chunks > 0:
        documents = await _count_documents_from_es()
    chunks = await _count_pg_table("chunks")
    if chunks == 0:
        chunks = es_chunks
    wiki_cards = await _count_pg_table("wiki_cards")

    return KnowledgeOverview(
        documents=documents,
        chunks=chunks,
        wiki_cards=wiki_cards,
        entities=es_entities,
        reviews=reviews,
        indexes=IndexCounts(
            milvus_chunks=milvus_chunks,
            es_chunks=es_chunks,
            es_entities=es_entities,
        ),
        qa_ready=QaReady(
            approved_cards=reviews.approved,
            approved_chunks=es_chunks,
        ),
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    keyword: str = Query("", description="文件名/路径关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """文档列表：支持分页和关键词搜索，数据来源为 PostgreSQL documents 表。"""
    keyword = keyword if isinstance(keyword, str) else ""
    try:
        from sqlalchemy import select, func, text
        from app.core.database import AsyncSessionLocal
        from app.models.documents import Document

        async with AsyncSessionLocal() as session:
            if not await _table_exists_raw("documents"):
                return await _list_documents_from_es(keyword, page, page_size)

            offset = (page - 1) * page_size

            # 基础条件
            conditions = []
            params: dict[str, Any] = {"limit": page_size, "offset": offset}
            if keyword:
                conditions.append(
                    text("(file_name ILIKE :kw OR source_path ILIKE :kw OR manual_type ILIKE :kw)")
                )
                params["kw"] = f"%{keyword}%"

            where_clause = ""
            if conditions:
                where_clause = " AND " + " AND ".join(str(c) for c in conditions)

            # 总数
            count_q = text(f"SELECT COUNT(*) FROM documents WHERE 1=1{where_clause}")
            total_result = await session.execute(count_q, params)
            total = total_result.scalar() or 0
            if total == 0:
                return await _list_documents_from_es(keyword, page, page_size)

            # 数据
            data_q = text(
                f"SELECT * FROM documents WHERE 1=1{where_clause} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            )
            rows_result = await session.execute(data_q, params)

            documents = []
            for row in rows_result:
                m = dict(row._mapping)
                doc_id = m.get("doc_id", "")

                chunk_count = 0
                card_count = 0
                try:
                    if await _table_exists_raw("chunks"):
                        r = await session.execute(
                            text("SELECT COUNT(*) FROM chunks WHERE doc_id = :doc_id"),
                            {"doc_id": doc_id},
                        )
                        chunk_count = r.scalar() or 0
                except Exception:
                    pass
                try:
                    if await _table_exists_raw("wiki_cards"):
                        r = await session.execute(
                            text("SELECT COUNT(*) FROM wiki_cards WHERE doc_id = :doc_id"),
                            {"doc_id": doc_id},
                        )
                        card_count = r.scalar() or 0
                except Exception:
                    pass

                documents.append(DocumentItem(
                    doc_id=doc_id,
                    file_name=m.get("file_name", ""),
                    source_path=m.get("source_path", ""),
                    manual_type=m.get("manual_type") or "",
                    aircraft_model=m.get("aircraft_model") or "",
                    engine_model=m.get("engine_model") or "",
                    ata_chapter=m.get("ata_chapter") or "",
                    manual_revision=m.get("manual_revision") or "",
                    effective_date=m.get("effective_date") or "",
                    applicability=m.get("applicability") or "",
                    language=m.get("language") or "",
                    confidentiality=m.get("confidentiality") or "",
                    parser_name=m.get("parser_name") or "",
                    parser_version=m.get("parser_version") or "",
                    created_at=m.get("created_at") or "",
                    chunk_count=chunk_count,
                    card_count=card_count,
                ))

            return DocumentListResponse(
                documents=documents,
                total=total,
                page=page,
                page_size=page_size,
            )

    except Exception as e:
        logger.error(f"list_documents failed: {e}")
        return DocumentListResponse(documents=[], total=0, page=page, page_size=page_size)


@router.get("/chunks", response_model=ChunkListResponse)
async def list_chunks(
    keyword: str = Query("", description="关键词搜索（支持 content/section_path/entities）"),
    status: str = Query("", description="状态过滤：approved/review/rejected"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """原文切块列表：基于 Elasticsearch knowledge_chunks 索引，支持搜索和分页。"""
    keyword = keyword if isinstance(keyword, str) else ""
    status = status if isinstance(status, str) else ""
    try:
        es_repo = ElasticsearchRepository()
        offset = (page - 1) * page_size

        # 用 search 接口获取 hits
        filters: dict[str, Any] = {}
        if status:
            filters["status"] = status

        results = await es_repo.search(
            query=keyword,
            top_k=page_size,
            filters=filters if filters else None,
            from_=offset,
        )

        total = await es_repo.count()

        chunks = [
            ChunkItem(
                chunk_id=h.get("chunk_id") or "",
                doc_id=h.get("doc_id") or "",
                content=h.get("content") or "",
                source_file=h.get("source_file") or "",
                section_path=h.get("section_path") or "",
                block_type=h.get("block_type") or "",
                page_numbers=h.get("page_numbers"),
                status=h.get("status") or "approved",
                score=h.get("score", 0.0),
            )
            for h in results
        ]

        return ChunkListResponse(
            chunks=chunks,
            total=total or 0,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"list_chunks failed: {e}")
        return ChunkListResponse(chunks=[], total=0, page=page, page_size=page_size)


@router.get("/entities", response_model=EntityListResponse)
async def list_entities(
    keyword: str = Query("", description="实体关键词搜索"),
    entity_type: str = Query("", description="实体类型过滤：component/part_number/symptom/procedure/... "),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """实体列表：基于 Elasticsearch entities 索引，支持搜索和分类过滤。"""
    keyword = keyword if isinstance(keyword, str) else ""
    entity_type = entity_type if isinstance(entity_type, str) else ""
    try:
        entity_repo = EntityESRepository()
        await entity_repo.create_index()
        entity_count = await entity_repo.count()

        results = await entity_repo.search_entities(
            query=keyword,
            entity_type=entity_type or None,
            top_k=page_size,
        )

        entities = [
            EntityItem(
                entity_type=h.get("entity_type", ""),
                value=h.get("value", ""),
                chunk_ids=h.get("chunk_ids", []),
                count=h.get("count", 0),
                score=h.get("score", 0.0),
            )
            for h in results
        ]

        return EntityListResponse(
            entities=entities,
            total=entity_count if not keyword and not entity_type else len(entities),
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"list_entities failed: {e}")
        return EntityListResponse(entities=[], total=0, page=page, page_size=page_size)


@router.get("/indexes", response_model=IndexStatus)
async def get_index_status():
    """索引状态：各存储层的索引健康度。"""
    status = IndexStatus()

    # Milvus
    try:
        milvus_repo = MilvusRepository()
        status.milvus = {
            "ok": True,
            "rag_chunks": milvus_repo.count(),
        }
    except Exception as e:
        logger.debug(f"Milvus status failed: {e}")
        status.milvus = {"ok": False, "error": str(e)}

    # Elasticsearch
    try:
        es_repo = ElasticsearchRepository()
        entity_repo = EntityESRepository()
        await entity_repo.create_index()
        status.elasticsearch = {
            "ok": True,
            "knowledge_chunks": await es_repo.count(),
            "entities": await entity_repo.count(),
        }
    except Exception as e:
        logger.debug(f"ES status failed: {e}")
        status.elasticsearch = {"ok": False, "error": str(e)}

    # PostgreSQL
    try:
        from sqlalchemy import text
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            doc_count = 0
            chunk_count = 0
            wiki_card_count = 0
            review_count = 0
            if await _table_exists_raw("documents"):
                doc_count = await session.scalar(text("SELECT COUNT(*) FROM documents")) or 0
            if await _table_exists_raw("chunks"):
                chunk_count = await session.scalar(text("SELECT COUNT(*) FROM chunks")) or 0
            if await _table_exists_raw("wiki_cards"):
                wiki_card_count = await session.scalar(text("SELECT COUNT(*) FROM wiki_cards")) or 0
            if await _table_exists_raw("wiki_reviews"):
                review_count = await session.scalar(text("SELECT COUNT(*) FROM wiki_reviews")) or 0
            status.postgres = {
                "ok": True,
                "documents": doc_count,
                "chunks": chunk_count,
                "wiki_cards": wiki_card_count,
                "wiki_reviews": review_count,
            }
    except Exception as e:
        logger.debug(f"PG status failed: {e}")
        status.postgres = {"ok": False, "error": str(e)}

    # NL2SQL metadata
    try:
        from app.nl2sql.service import NL2SQLService

        nl2sql = NL2SQLService()
        nl2sql_status = await nl2sql.status()
        status.nl2sql = {
            "ok": True,
            "table_info": nl2sql_status.metadata.get("nl2sql_table_info", 0),
            "column_info": nl2sql_status.metadata.get("nl2sql_column_info", 0),
            "metric_info": nl2sql_status.metadata.get("nl2sql_metric_info", 0),
            "value_info": nl2sql_status.metadata.get("nl2sql_value_info", 0),
            "seeded": nl2sql_status.seeded,
            "warnings": nl2sql_status.warnings,
        }
    except Exception as e:
        logger.debug(f"NL2SQL status failed: {e}")
        status.nl2sql = {"ok": False, "error": str(e)}

    return status
