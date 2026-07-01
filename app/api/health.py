"""健康检查 + 系统状态 API。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

from app.clients.llm_client import embedding_client, llm_client
from app.core.log import logger
from app.retrieval.es_repo import ElasticsearchRepository, EntityESRepository
from app.retrieval.milvus_repo import MilvusRepository
from app.services.wiki_pg_service import count_pg_rows

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: str
    timestamp: str
    services: dict
    version: str = "0.1.0"


@router.get("/")
async def health_check():
    """综合健康检查。"""
    services = {}

    # Milvus chunk index
    try:
        repo = MilvusRepository()
        chunk_count = repo.count()
        services["milvus"] = {"ok": True, "chunks": chunk_count}
    except Exception as e:
        logger.debug(f"Milvus check failed: {e}")
        services["milvus"] = {"ok": False, "error": str(e)}

    # Wiki truth store in PostgreSQL
    try:
        services["wiki_pg"] = {
            "ok": True,
            "cards": await count_pg_rows("wiki_cards"),
            "reviews": await count_pg_rows("wiki_reviews"),
        }
    except Exception as e:
        logger.debug(f"Wiki PG check failed: {e}")
        services["wiki_pg"] = {"ok": False, "error": str(e)}

    # Elasticsearch chunks + entities
    try:
        es_repo = ElasticsearchRepository()
        es_count = await es_repo.count()
        entity_repo = EntityESRepository()
        await entity_repo.create_index()
        services["elasticsearch"] = {"ok": True, "chunks": es_count, "entities": await entity_repo.count()}
    except Exception as e:
        logger.debug(f"ES check failed: {e}")
        services["elasticsearch"] = {"ok": False, "error": str(e)}

    # LLM
    try:
        services["llm"] = {"ok": True, "model": llm_client._model_name}
    except Exception as e:
        services["llm"] = {"ok": False, "error": str(e)}

    # Embedding
    try:
        services["embedding"] = {"ok": True, "model": embedding_client._model_name}
    except Exception as e:
        services["embedding"] = {"ok": False, "error": str(e)}

    overall_ok = all(s.get("ok", False) for s in services.values())
    return HealthStatus(
        status="healthy" if overall_ok else "degraded",
        timestamp=datetime.now().isoformat(),
        services=services,
    )


@router.get("/ping")
async def ping():
    """快速 ping。"""
    return {"pong": True, "timestamp": datetime.now().isoformat()}
