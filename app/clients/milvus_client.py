from pymilvus import MilvusClient

from app.conf.app_config import config
from app.core.log import logger

_milvus_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    global _milvus_client
    if _milvus_client is None:
        _milvus_client = MilvusClient(
            uri=f"http://{config.MILVUS_HOST}:{config.MILVUS_PORT}"
        )
        logger.info("Milvus client initialized")
    return _milvus_client
