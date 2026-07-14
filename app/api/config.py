"""运行配置 API。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.conf.app_config import config

router = APIRouter(tags=["config"])


class MinioConfig(BaseModel):
    endpoint: str
    access_key: str
    secret_key_configured: bool
    bucket: str


class ModelConfig(BaseModel):
    name: str
    api_base: str
    api_key_configured: bool


class LLMConfig(ModelConfig):
    pass


class EmbeddingConfig(ModelConfig):
    dimensions: int
    instruction: str


class RerankerConfig(ModelConfig):
    instruction: str


class StorageConfig(BaseModel):
    postgres_host: str
    postgres_port: int
    postgres_db: str
    postgres_user: str
    milvus_host: str
    milvus_port: int
    milvus_collection: str
    es_host: str
    es_port: int
    minio: MinioConfig


class RuntimeConfigResponse(BaseModel):
    app_env: str
    storage: StorageConfig
    llm: LLMConfig
    embedding: EmbeddingConfig
    reranker: RerankerConfig
    ocr: ModelConfig
    vl: ModelConfig


@router.get("/", response_model=RuntimeConfigResponse)
async def get_runtime_config():
    """获取当前运行配置（不含密钥明文）。"""
    return RuntimeConfigResponse(
        app_env=config.APP_ENV,
        storage=StorageConfig(
            postgres_host=config.POSTGRES_HOST,
            postgres_port=config.POSTGRES_PORT,
            postgres_db=config.POSTGRES_DB,
            postgres_user=config.POSTGRES_USER,
            milvus_host=config.MILVUS_HOST,
            milvus_port=config.MILVUS_PORT,
            milvus_collection=config.MILVUS_COLLECTION,
            es_host=config.ES_HOST,
            es_port=config.ES_PORT,
            minio=MinioConfig(
                endpoint=config.MINIO_ENDPOINT,
                access_key=config.MINIO_ACCESS_KEY,
                secret_key_configured=bool(config.MINIO_SECRET_KEY),
                bucket=config.MINIO_BUCKET,
            ),
        ),
        llm=LLMConfig(
            name=config.llm_model_name,
            api_base=config.llm_api_base,
            api_key_configured=bool(config.llm_api_key),
        ),
        embedding=EmbeddingConfig(
            name=config.embedding_model_name,
            api_base=config.embedding_api_base,
            api_key_configured=bool(config.embedding_api_key),
            dimensions=config.embedding_dimensions,
            instruction=config.embedding_instruction,
        ),
        reranker=RerankerConfig(
            name=config.rerank_model_name,
            api_base=config.rerank_api_base,
            api_key_configured=bool(config.rerank_api_key),
            instruction=config.rerank_instruction,
        ),
        ocr=ModelConfig(
            name=config.ocr_model_name,
            api_base=config.ocr_api_base,
            api_key_configured=bool(config.ocr_api_key),
        ),
        vl=ModelConfig(
            name=config.vl_model_name,
            api_base=config.vl_api_base,
            api_key_configured=bool(config.vl_api_key),
        ),
    )
