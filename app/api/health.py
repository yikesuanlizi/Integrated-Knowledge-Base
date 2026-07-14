"""健康检查 + 系统状态 API。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.clients.minio_client import minio_client_manager
from app.conf.app_config import config
from app.core.log import logger
from app.retrieval.es_repo import ElasticsearchRepository, EntityESRepository
from app.retrieval.milvus_repo import MilvusRepository
from app.services.wiki_pg_service import count_pg_rows

router = APIRouter(tags=["health"])

_cache: Optional[dict] = None
_cache_time: Optional[datetime] = None
_CACHE_TTL = timedelta(seconds=15)


class HealthStatus(BaseModel):
    status: str
    timestamp: str
    services: dict
    version: str = "0.1.0"


async def _check_milvus() -> dict:
    try:
        repo = MilvusRepository()
        chunk_count = repo.count()
        return {"ok": True, "chunks": chunk_count}
    except Exception as e:
        logger.debug(f"Milvus check failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


async def _check_pg() -> dict:
    try:
        cards = await count_pg_rows("wiki_cards")
        reviews = await count_pg_rows("wiki_reviews")
        return {"ok": True, "cards": cards, "reviews": reviews}
    except Exception as e:
        logger.debug(f"PG check failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


async def _check_es() -> dict:
    try:
        es_repo = ElasticsearchRepository()
        es_count = await es_repo.count()
        entity_repo = EntityESRepository()
        entity_count = await entity_repo.count()
        return {"ok": True, "chunks": es_count, "entities": entity_count}
    except Exception as e:
        logger.debug(f"ES check failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


async def _check_minio() -> dict:
    try:
        minio_client = minio_client_manager.client
        bucket_exists = minio_client.bucket_exists(config.MINIO_BUCKET)
        return {"ok": True, "bucket": config.MINIO_BUCKET, "bucket_exists": bucket_exists}
    except Exception as e:
        logger.debug(f"MinIO check failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


def _check_model_configured(name: str, api_key: str, model_name: str) -> dict:
    if not api_key:
        return {"ok": False, "error": "API key not configured", "model": model_name}
    return {"ok": True, "model": model_name, "api_base": _mask_url(getattr(config, f"{name}_api_base", ""))}


def _mask_url(url: str) -> str:
    if not url:
        return ""
    if "://" in url:
        return url.split("://", 1)[1]
    return url


@router.get("/")
async def health_check():
    """综合健康检查（带15秒缓存）。"""
    global _cache, _cache_time

    now = datetime.now()
    if _cache is not None and _cache_time is not None and (now - _cache_time) < _CACHE_TTL:
        cached = dict(_cache)
        cached["timestamp"] = now.isoformat()
        return HealthStatus(**cached)

    services = {}

    results = await asyncio.gather(
        _check_milvus(),
        _check_pg(),
        _check_es(),
        _check_minio(),
        return_exceptions=True,
    )

    checks = [("milvus", 0), ("wiki_pg", 1), ("elasticsearch", 2), ("minio", 3)]
    for name, idx in checks:
        r = results[idx]
        services[name] = r if not isinstance(r, Exception) else {"ok": False, "error": str(r)[:200]}

    services["llm"] = _check_model_configured("llm", config.llm_api_key, config.llm_model_name)
    services["embedding"] = _check_model_configured("embedding", config.embedding_api_key, config.embedding_model_name)
    services["reranker"] = _check_model_configured("rerank", config.rerank_api_key, config.rerank_model_name)

    critical_services = ["milvus", "wiki_pg", "elasticsearch", "llm", "embedding"]
    critical_ok = all(services.get(s, {}).get("ok", False) for s in critical_services)
    overall_ok = all(s.get("ok", False) for s in services.values())
    final_status = "healthy" if overall_ok else ("degraded" if critical_ok else "unhealthy")

    result = {
        "status": final_status,
        "timestamp": now.isoformat(),
        "services": services,
    }
    _cache = result
    _cache_time = now

    return HealthStatus(**result)


@router.get("/ping")
async def ping():
    """快速 ping。"""
    return {"pong": True, "timestamp": datetime.now().isoformat()}
