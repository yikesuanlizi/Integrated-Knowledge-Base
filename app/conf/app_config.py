import os
from typing import ClassVar, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    DATABASE_URL: Optional[str] = None
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "akos"
    POSTGRES_PASSWORD: str = "akos_pass"
    POSTGRES_DB: str = "akos"

    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "rag_chunks"
    WIKI_COLLECTION: str = "wiki_cards"
    STRICT_REVIEW_GATE: bool = True

    RECALL_EXECUTION_MODE: str = "parallel"
    RECALL_PARALLEL_MAX_WORKERS: int = 4
    RECALL_CHANNEL_TIMEOUTS: dict = {
        "wiki": 1.5,
        "chunks": 2.5,
        "entities": 1.8,
        "structured_metadata": 3.5,
    }

    ELASTICSEARCH_URL: Optional[str] = None
    ES_HOST: str = "localhost"
    ES_PORT: int = 9200
    ES_USER: str = ""
    ES_PASSWORD: str = ""

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "rag-bucket"

    # Model provider settings are application configuration, not environment
    # variables. Only provider secrets are read from the environment.
    DEEPSEEK_API_BASE: ClassVar[str] = "https://api.deepseek.com"
    GITEE_API_BASE: ClassVar[str] = "https://ai.gitee.com/v1"
    LLM_MODEL_NAME: ClassVar[str] = "deepseek-v4-flash"
    EMBEDDING_MODEL_NAME: ClassVar[str] = "Qwen3-Embedding-8B"
    EMBEDDING_DIMENSIONS: ClassVar[int] = 1024
    EMBEDDING_INSTRUCTION: ClassVar[str] = "为航空维修知识库检索生成语义向量。"
    RERANK_MODEL_NAME: ClassVar[str] = "Qwen3-Reranker-8B"
    RERANK_INSTRUCTION: ClassVar[str] = "按照问题与航空维修知识证据的相关性排序。"
    OCR_MODEL_NAME: ClassVar[str] = "DeepSeek-OCR-2"
    VL_MODEL_NAME: ClassVar[str] = "MiniMax-M3"

    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"
    LOG_DIR: str = "logs"
    LOG_FILE_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB per file
    LOG_FILE_BACKUP_COUNT: int = 5

    @property
    def postgres_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def es_url(self) -> str:
        if self.ELASTICSEARCH_URL:
            return self.ELASTICSEARCH_URL
        return f"http://{self.ES_HOST}:{self.ES_PORT}"

    @property
    def llm_api_base(self) -> str:
        return self.DEEPSEEK_API_BASE

    @property
    def llm_model_name(self) -> str:
        return self.LLM_MODEL_NAME

    @property
    def deepseek_api_key(self) -> str:
        return os.getenv("DEEPSEEK_API_KEY") or ""

    @property
    def llm_api_key(self) -> str:
        return self.deepseek_api_key

    @property
    def embedding_api_base(self) -> str:
        return self.GITEE_API_BASE

    @property
    def embedding_model_name(self) -> str:
        return self.EMBEDDING_MODEL_NAME

    @property
    def embedding_dimensions(self) -> int:
        return self.EMBEDDING_DIMENSIONS

    @property
    def embedding_instruction(self) -> str:
        return self.EMBEDDING_INSTRUCTION

    @property
    def embedding_api_key(self) -> str:
        return self.gitee_api_key

    @property
    def gitee_api_key(self) -> str:
        return os.getenv("GITEE_API_KEY") or ""

    @property
    def rerank_api_base(self) -> str:
        return self.GITEE_API_BASE

    @property
    def rerank_model_name(self) -> str:
        return self.RERANK_MODEL_NAME

    @property
    def rerank_instruction(self) -> str:
        return self.RERANK_INSTRUCTION

    @property
    def rerank_api_key(self) -> str:
        return self.gitee_api_key

    @property
    def ocr_api_base(self) -> str:
        return self.GITEE_API_BASE

    @property
    def ocr_model_name(self) -> str:
        return self.OCR_MODEL_NAME

    @property
    def ocr_api_key(self) -> str:
        return self.gitee_api_key

    @property
    def vl_api_base(self) -> str:
        return self.GITEE_API_BASE

    @property
    def vl_model_name(self) -> str:
        return self.VL_MODEL_NAME

    @property
    def vl_api_key(self) -> str:
        return self.gitee_api_key


config = AppConfig()
