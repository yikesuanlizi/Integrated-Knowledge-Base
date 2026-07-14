from typing import Any, Dict, List, Optional

import asyncio
from elasticsearch import AsyncElasticsearch

from app.conf.app_config import config
from app.core.log import logger


class ESClientManager:
    def __init__(self):
        self._client: Optional[AsyncElasticsearch] = None
        self._loop_id: Optional[int] = None

    def init(self):
        if self._client is not None and self._loop_id == id(asyncio.get_event_loop()):
            return
        kwargs: Dict[str, Any] = {"hosts": [config.es_url]}
        if config.ES_USER:
            kwargs["basic_auth"] = (config.ES_USER, config.ES_PASSWORD)
        self._client = AsyncElasticsearch(**kwargs)
        self._loop_id = id(asyncio.get_event_loop())
        logger.info("Elasticsearch client initialized")

    @property
    def client(self) -> AsyncElasticsearch:
        if self._client is None or self._loop_id != id(asyncio.get_event_loop()):
            self.init()
        return self._client

    async def create_index(self, index_name: str, mappings: Optional[Dict[str, Any]] = None):
        if not await self.client.indices.exists(index=index_name):
            await self.client.indices.create(
                index=index_name,
                mappings=mappings,
            )
            logger.info(f"ES index '{index_name}' created")

    async def index_document(self, index_name: str, document: Dict[str, Any], doc_id: Optional[str] = None):
        return await self.client.index(index=index_name, document=document, id=doc_id)

    async def search(
        self,
        index_name: str,
        query: Dict[str, Any],
        size: int = 10,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {"index": index_name, "query": query, "size": size}
        if fields:
            kwargs["fields"] = fields
        return await self.client.search(**kwargs)

    async def query(self, index_name: str, query: Dict[str, Any], size: int = 1000) -> Dict[str, Any]:
        return await self.client.search(index=index_name, query=query, size=size)

    async def delete_by_query(self, index_name: str, query: Dict[str, Any]):
        return await self.client.delete_by_query(index=index_name, query=query)

    async def count(self, index_name: str, query: Optional[Dict[str, Any]] = None) -> int:
        if not await self.client.indices.exists(index=index_name):
            return 0
        result = await self.client.count(index=index_name, query=query or {"match_all": {}})
        return result["count"]

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Elasticsearch client closed")


es_client_manager = ESClientManager()


def get_es_client() -> AsyncElasticsearch:
    return es_client_manager.client
