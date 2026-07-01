from __future__ import annotations

from typing import Any, List, Optional

from app.clients.es_client import get_es_client


class ElasticsearchRepository:
    def __init__(self, index_name: str = "knowledge_chunks"):
        self.index_name = index_name
        self.client = get_es_client()

    async def create_index(self, mappings: Optional[dict] = None) -> None:
        if not await self.client.indices.exists(index=self.index_name):
            default_mappings = {
                "mappings": {
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "doc_id": {"type": "keyword"},
                        "raw_content": {"type": "text", "index": False},
                        "search_content": {"type": "text", "analyzer": "standard"},
                        "embedding_content": {"type": "text", "index": False},
                        "content": {"type": "text", "index": False},
                        "source_file": {"type": "keyword"},
                        "section_path": {"type": "text"},
                        "block_type": {"type": "keyword"},
                        "page_numbers": {"type": "integer"},
                        "entities": {"type": "keyword"},
                        "keywords": {"type": "keyword"},
                        "manual_type": {"type": "keyword"},
                        "ata_chapter": {"type": "keyword"},
                        "aircraft_model": {"type": "keyword"},
                        "status": {"type": "keyword"},
                    }
                }
            }
            await self.client.indices.create(index=self.index_name, mappings=_normalize_mappings(mappings or default_mappings))

    async def index_chunk(self, chunk: dict) -> None:
        await self.client.index(
            index=self.index_name,
            id=chunk["chunk_id"],
            document=chunk,
        )

    async def index_chunks(self, chunks: List[dict]) -> None:
        for chunk in chunks:
            await self.index_chunk(chunk)

    async def search(self, query: str, top_k: int = 10, filters: Optional[dict] = None, from_: int = 0) -> List[dict]:
        must_clause: list[dict[str, Any]] = []
        if query and query.strip():
            must_clause.append(
                {
                    "multi_match": {
                        "query": query,
                        "fields": ["search_content^3", "section_path^2", "entities^2", "keywords"],
                        "type": "best_fields",
                    }
                }
            )

        body: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": must_clause if must_clause else [{"match_all": {}}],
                }
            },
            "from": from_,
            "size": top_k,
        }

        if filters:
            filter_clauses = []
            for key, value in filters.items():
                if isinstance(value, list):
                    filter_clauses.append({"terms": {key: value}})
                else:
                    filter_clauses.append({"term": {key: value}})
            if filter_clauses:
                body["query"]["bool"]["filter"] = filter_clauses

        response = await self.client.search(
            index=self.index_name,
            query=body["query"],
            from_=body["from"],
            size=body["size"],
        )

        hits = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            hits.append({
                "chunk_id": source.get("chunk_id"),
                "doc_id": source.get("doc_id"),
                "content": source.get("raw_content") or source.get("content"),
                "raw_content": source.get("raw_content") or source.get("content"),
                "search_content": source.get("search_content") or "",
                "embedding_content": source.get("embedding_content") or "",
                "source_file": source.get("source_file"),
                "section_path": source.get("section_path"),
                "block_type": source.get("block_type"),
                "page_numbers": source.get("page_numbers"),
                "status": source.get("status"),
                "score": hit["_score"],
            })

        return hits

    async def search_entities(
        self,
        entity_value: str,
        entity_type: str = "part_number",
        top_k: int = 5,
        filters: Optional[dict] = None,
    ) -> List[dict]:
        body = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"entities": entity_value}},
                    ]
                }
            },
            "size": top_k,
        }

        if filters:
            filter_clauses = []
            for key, value in filters.items():
                if isinstance(value, list):
                    filter_clauses.append({"terms": {key: value}})
                else:
                    filter_clauses.append({"term": {key: value}})
            if filter_clauses:
                body["query"]["bool"]["filter"] = filter_clauses

        response = await self.client.search(index=self.index_name, query=body["query"], size=body["size"])

        hits = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            hits.append({
                "chunk_id": source.get("chunk_id"),
                "doc_id": source.get("doc_id"),
                "content": source.get("raw_content") or source.get("content"),
                "raw_content": source.get("raw_content") or source.get("content"),
                "search_content": source.get("search_content") or "",
                "embedding_content": source.get("embedding_content") or "",
                "source_file": source.get("source_file"),
                "section_path": source.get("section_path"),
                "block_type": source.get("block_type"),
                "page_numbers": source.get("page_numbers"),
                "status": source.get("status"),
                "score": hit["_score"],
            })

        return hits

    async def get_chunk(self, chunk_id: str) -> Optional[dict]:
        try:
            response = await self.client.get(index=self.index_name, id=chunk_id)
            return response["_source"]
        except Exception:
            return None

    async def update_chunk_statuses(self, chunk_ids: List[str], status: str) -> None:
        for chunk_id in chunk_ids:
            await self.client.update(
                index=self.index_name,
                id=chunk_id,
                doc={"status": status},
            )

    async def delete_chunk(self, chunk_id: str) -> None:
        await self.client.delete(index=self.index_name, id=chunk_id)

    async def delete_by_doc_id(self, doc_id: str) -> None:
        body = {
            "query": {
                "term": {"doc_id": doc_id}
            }
        }
        await self.client.delete_by_query(index=self.index_name, query=body["query"])

    async def clear(self) -> None:
        if await self.client.indices.exists(index=self.index_name):
            await self.client.indices.delete(index=self.index_name)
        await self.create_index()

    async def count(self) -> int:
        if not await self.client.indices.exists(index=self.index_name):
            return 0
        response = await self.client.count(index=self.index_name)
        return response["count"]


class EntityESRepository:
    def __init__(self, index_name: str = "entities"):
        self.index_name = index_name
        self.client = get_es_client()

    async def create_index(self) -> None:
        if not await self.client.indices.exists(index=self.index_name):
            mappings = {
                "mappings": {
                    "properties": {
                        "entity_type": {"type": "keyword"},
                        "value": {"type": "keyword"},
                        "chunk_ids": {"type": "keyword"},
                        "doc_ids": {"type": "keyword"},
                        "source_files": {"type": "keyword"},
                        "count": {"type": "integer"},
                    }
                }
            }
            await self.client.indices.create(index=self.index_name, mappings=_normalize_mappings(mappings))

    async def index_entity(self, entity: dict) -> None:
        await self.client.index(
            index=self.index_name,
            id=f"{entity['entity_type']}_{entity['value']}",
            document=entity,
        )

    async def search_entities(self, query: str, entity_type: Optional[str] = None, top_k: int = 10) -> List[dict]:
        must_clause = [{"match": {"value": query}}] if query and query.strip() else [{"match_all": {}}]
        body: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": must_clause
                }
            },
            "size": top_k,
        }

        if entity_type:
            body["query"]["bool"]["filter"] = {"term": {"entity_type": entity_type}}

        response = await self.client.search(index=self.index_name, query=body["query"], size=body["size"])

        hits = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            hits.append({
                "entity_type": source.get("entity_type"),
                "value": source.get("value"),
                "chunk_ids": source.get("chunk_ids", []),
                "count": source.get("count", 0),
                "score": hit["_score"],
            })

        return hits

    async def get_entity(self, entity_type: str, value: str) -> Optional[dict]:
        try:
            response = await self.client.get(index=self.index_name, id=f"{entity_type}_{value}")
            return response["_source"]
        except Exception:
            return None

    async def clear(self) -> None:
        if await self.client.indices.exists(index=self.index_name):
            await self.client.indices.delete(index=self.index_name)
        await self.create_index()

    async def count(self) -> int:
        if not await self.client.indices.exists(index=self.index_name):
            return 0
        response = await self.client.count(index=self.index_name)
        return int(response["count"])


class WikiCardESRepository:
    def __init__(self, index_name: str = "wiki_cards"):
        self.index_name = index_name
        self.client = get_es_client()

    async def create_index(self) -> None:
        if not await self.client.indices.exists(index=self.index_name):
            mappings = {
                "mappings": {
                    "properties": {
                        "card_id": {"type": "keyword"},
                        "card_type": {"type": "keyword"},
                        "title": {"type": "text", "analyzer": "standard"},
                        "content": {"type": "text", "analyzer": "standard"},
                        "source_ref": {"type": "keyword"},
                        "status": {"type": "keyword"},
                        "references": {"type": "keyword"},
                        "related_cards": {"type": "keyword"},
                        "linked_chunks": {"type": "keyword"},
                    }
                }
            }
            await self.client.indices.create(index=self.index_name, mappings=_normalize_mappings(mappings))

    async def index_card(self, card: dict) -> None:
        await self.client.index(
            index=self.index_name,
            id=card["card_id"],
            document=card,
        )

    async def get_card(self, card_id: str) -> Optional[dict]:
        try:
            response = await self.client.get(index=self.index_name, id=card_id)
            return response["_source"]
        except Exception:
            return None

    async def update_card_status(self, card_id: str, status: str) -> None:
        await self.client.update(
            index=self.index_name,
            id=card_id,
            doc={"status": status},
        )

    async def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict] = None,
        from_: int = 0,
    ) -> List[dict]:
        # keyword 为空时用 match_all（支持无关键词列表），否则用 multi_match
        must_clause: List[dict] = []
        if query and query.strip():
            must_clause.append({
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "content^2"],
                    "type": "best_fields",
                }
            })

        body: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": must_clause if must_clause else [{"match_all": {}}],
                }
            },
            "from": from_,
            "size": top_k,
        }

        if filters:
            filter_clauses = []
            for key, value in filters.items():
                if isinstance(value, list):
                    filter_clauses.append({"terms": {key: value}})
                else:
                    filter_clauses.append({"term": {key: value}})
            if filter_clauses:
                body["query"]["bool"]["filter"] = filter_clauses

        response = await self.client.search(
            index=self.index_name,
            query=body["query"],
            from_=body["from"],
            size=body["size"],
        )

        hits = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            hits.append({
                "card_id": source.get("card_id"),
                "card_type": source.get("card_type"),
                "title": source.get("title"),
                "content": source.get("content"),
                "source_ref": source.get("source_ref"),
                "status": source.get("status"),
                "linked_chunks": source.get("linked_chunks") or [],
                "score": hit["_score"],
            })

        return hits

    async def count(self, filters: Optional[dict] = None) -> int:
        if not await self.client.indices.exists(index=self.index_name):
            return 0
        if not filters:
            response = await self.client.count(index=self.index_name)
            return int(response["count"])
        query: dict[str, Any] = {"bool": {"filter": []}}
        for key, value in filters.items():
            if isinstance(value, list):
                query["bool"]["filter"].append({"terms": {key: value}})
            else:
                query["bool"]["filter"].append({"term": {key: value}})
        response = await self.client.count(index=self.index_name, query=query)
        return int(response["count"])

    async def clear(self) -> None:
        if await self.client.indices.exists(index=self.index_name):
            await self.client.indices.delete(index=self.index_name)
        await self.create_index()


def _normalize_mappings(mappings: dict) -> dict:
    """Accept either an ES create-index body or the mappings object itself."""
    return mappings.get("mappings", mappings)
