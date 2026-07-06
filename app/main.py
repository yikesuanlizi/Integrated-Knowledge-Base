"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.compile import router as compile_router
from app.api.chunk_review import router as chunk_review_router
from app.api.eval import router as eval_router
from app.api.export import router as export_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.knowledge import router as knowledge_router
from app.api.mcp import router as mcp_router
from app.api.monitor import router as monitor_router
from app.api.nl2sql import router as nl2sql_router
from app.api.query import router as query_router
from app.api.review import router as review_router
from app.api.wiki import router as wiki_router
from app.conf.app_config import config
from app.core.log import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期。"""
    logger.info("Starting Agentic Knowledge OS...")
    try:
        from app.core.database import init_database
        await init_database()
    except Exception as e:
        logger.warning(f"Database init failed (may be ok in dev): {e}")
    logger.info(f"Started. LLM: {config.llm_model_name} | Embedding: {config.embedding_model_name}")
    yield
    logger.info("Shutting down Agentic Knowledge OS...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Agentic Knowledge OS",
        description="Agentic RAG System: Document ingestion to intelligent Q&A",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(SessionMiddleware, secret_key="agentic-rag-secret")

    app.include_router(ingest_router, prefix="/api/ingest", tags=["ingest"])
    app.include_router(compile_router, prefix="/api/compile", tags=["compile"])
    app.include_router(query_router, prefix="/api/query", tags=["query"])
    app.include_router(wiki_router, prefix="/api/wiki", tags=["wiki"])
    app.include_router(review_router, prefix="/api/review", tags=["review"])
    app.include_router(chunk_review_router, prefix="/api/chunk-review", tags=["chunk-review"])
    app.include_router(eval_router, prefix="/api/eval", tags=["eval"])
    app.include_router(export_router, prefix="/api/export", tags=["export"])
    app.include_router(mcp_router, prefix="/api/mcp", tags=["mcp"])
    app.include_router(nl2sql_router, prefix="/api/nl2sql", tags=["nl2sql"])
    app.include_router(health_router, prefix="/api/health", tags=["health"])
    app.include_router(knowledge_router, prefix="/api/knowledge", tags=["knowledge"])
    app.include_router(monitor_router, prefix="/api/monitor", tags=["monitor"])

    return app


app = create_app()
