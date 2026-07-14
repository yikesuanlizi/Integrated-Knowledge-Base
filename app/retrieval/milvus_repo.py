from __future__ import annotations

from typing import Optional

from app.clients.milvus_client import get_milvus_client
from app.conf.app_config import config


class MilvusRepository:
    def __init__(self):
        self.collection_name = config.MILVUS_COLLECTION
        self.client = get_milvus_client()
        self._ensure_collection()

    def _ensure_collection(self, dim: int | None = None) -> None:
        """用显式字段名建 collection：chunk_id（主键，string）+ embedding（向量），其他字段走动态字段。"""
        dim = dim or config.embedding_dimensions
        if not self.client.has_collection(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                dimension=dim,
                metric_type="COSINE",
                primary_field_name="chunk_id",
                vector_field_name="embedding",
                id_type="string",
                max_length=256,
                enable_dynamic_field=True,
                consistency_level="Strong",
            )

    def insert_chunk(self, chunk: dict, embedding: list[float]) -> None:
        """写入单个 chunk。chunk 应为 dict 形式（从 Chunk dataclass 转换而来）。"""
        self.client.insert(
            collection_name=self.collection_name,
            data=[{
                "chunk_id": chunk.get("chunk_id", ""),
                "doc_id": chunk.get("doc_id", ""),
                "content": chunk.get("raw_content", chunk.get("content", "")),
                "raw_content": chunk.get("raw_content", chunk.get("content", "")),
                "search_content": chunk.get("search_content", ""),
                "embedding_content": chunk.get("embedding_content", ""),
                "source_file": chunk.get("source_file", ""),
                "section_path": chunk.get("section_path", ""),
                "block_type": chunk.get("block_type", ""),
                "page_numbers": chunk.get("page_numbers") or [],
                "manual_type": chunk.get("manual_type", ""),
                "ata_chapter": chunk.get("ata_chapter", ""),
                "aircraft_model": chunk.get("aircraft_model", ""),
                "manual_revision": chunk.get("manual_revision", ""),
                "effective_date": chunk.get("effective_date", ""),
                "applicability": chunk.get("applicability", ""),
                "status": chunk.get("status", "approved"),
                "embedding": embedding,
            }],
        )

    def insert_chunks(self, items: list[dict], embeddings: list[list[float]]) -> None:
        """批量写入。items 必须是 dict（chunk_id/doc_id/content/... 字段）。"""
        if not items:
            return
        data = []
        for item, embedding in zip(items, embeddings):
            data.append({
                "chunk_id": item.get("chunk_id", ""),
                "doc_id": item.get("doc_id", ""),
                "content": item.get("raw_content", item.get("content", "")),
                "raw_content": item.get("raw_content", item.get("content", "")),
                "search_content": item.get("search_content", ""),
                "embedding_content": item.get("embedding_content", ""),
                "source_file": item.get("source_file", ""),
                "section_path": item.get("section_path", ""),
                "block_type": item.get("block_type", ""),
                "page_numbers": item.get("page_numbers") or [],
                "manual_type": item.get("manual_type", ""),
                "ata_chapter": item.get("ata_chapter", ""),
                "aircraft_model": item.get("aircraft_model", ""),
                "manual_revision": item.get("manual_revision", ""),
                "effective_date": item.get("effective_date", ""),
                "applicability": item.get("applicability", ""),
                "status": item.get("status", "approved"),
                "embedding": embedding,
            })
        self.client.insert(collection_name=self.collection_name, data=data)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 8,
        filters: dict | None = None,
    ) -> list[dict]:
        fields = [
            "chunk_id",
            "doc_id",
            "content",
            "raw_content",
            "search_content",
            "embedding_content",
            "source_file",
            "section_path",
            "block_type",
            "page_numbers",
            "manual_type",
            "ata_chapter",
            "aircraft_model",
            "manual_revision",
            "effective_date",
            "applicability",
            "status",
        ]

        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_embedding],
            limit=top_k,
            filter=_build_filter_expr(filters) if filters else "",
            output_fields=fields,
        )

        hits = []
        for hit in results[0]:
            hits.append({
                "chunk_id": hit["entity"].get("chunk_id"),
                "doc_id": hit["entity"].get("doc_id"),
                "content": hit["entity"].get("raw_content") or hit["entity"].get("content"),
                "raw_content": hit["entity"].get("raw_content") or hit["entity"].get("content"),
                "search_content": hit["entity"].get("search_content"),
                "embedding_content": hit["entity"].get("embedding_content"),
                "source_file": hit["entity"].get("source_file"),
                "section_path": hit["entity"].get("section_path"),
                "block_type": hit["entity"].get("block_type"),
                "page_numbers": hit["entity"].get("page_numbers"),
                "manual_type": hit["entity"].get("manual_type"),
                "ata_chapter": hit["entity"].get("ata_chapter"),
                "aircraft_model": hit["entity"].get("aircraft_model"),
                "manual_revision": hit["entity"].get("manual_revision"),
                "effective_date": hit["entity"].get("effective_date"),
                "applicability": hit["entity"].get("applicability"),
                "status": hit["entity"].get("status", "approved"),
                "score": float(hit["distance"]),
            })

        return hits

    def get_chunk(self, chunk_id: str) -> dict | None:
        results = self.client.query(
            collection_name=self.collection_name,
            filter=f'chunk_id == "{chunk_id}"',
            output_fields=[
                "chunk_id",
                "doc_id",
                "content",
                "raw_content",
                "search_content",
                "embedding_content",
                "source_file",
                "section_path",
                "block_type",
                "page_numbers",
                "manual_type",
                "ata_chapter",
                "aircraft_model",
                "manual_revision",
                "effective_date",
                "applicability",
                "status",
                "embedding",
            ],
            limit=1,
        )
        return results[0] if results else None

    def update_chunk_statuses(self, chunk_ids: list[str], status: str) -> None:
        data = []
        for chunk_id in chunk_ids:
            chunk = self.get_chunk(chunk_id)
            if not chunk:
                continue
            chunk["status"] = status
            data.append(chunk)
        if data:
            _upsert(self.client, self.collection_name, data)

    def delete_chunk(self, chunk_id: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            filter=f'chunk_id == "{chunk_id}"',
        )

    def delete_by_doc_id(self, doc_id: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            filter=f'doc_id == "{doc_id}"',
        )

    def clear(self) -> None:
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)
        self._ensure_collection()

    def count(self) -> int:
        try:
            rows = self.client.query(
                collection_name=self.collection_name,
                filter='chunk_id != ""',
                output_fields=["chunk_id"],
                limit=10000,
            )
            return len(rows)
        except Exception:
            return 0


class WikiCardMilvusRepository:
    def __init__(self):
        self.collection_name = config.WIKI_COLLECTION
        self.client = get_milvus_client()
        self._ensure_collection()

    def _ensure_collection(self, dim: int | None = None) -> None:
        dim = dim or config.embedding_dimensions
        if not self.client.has_collection(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                dimension=dim,
                metric_type="COSINE",
                primary_field_name="card_id",
                vector_field_name="embedding",
                id_type="string",
                max_length=256,
                enable_dynamic_field=True,
                consistency_level="Strong",
            )

    def insert_card(self, card: dict, embedding: list[float]) -> None:
        self.client.insert(
            collection_name=self.collection_name,
            data=[{
                "card_id": card.get("card_id", ""),
                "card_type": card.get("card_type", ""),
                "title": card.get("title", ""),
                "content": card.get("content", ""),
                "source_ref": card.get("source_ref", ""),
                "status": card.get("status", "draft"),
                "linked_chunks": card.get("linked_chunks") or [],
                "embedding": embedding,
            }],
        )

    def insert_cards(self, items: list[dict], embeddings: list[list[float]]) -> None:
        if not items:
            return
        data = []
        for item, embedding in zip(items, embeddings):
            data.append({
                "card_id": item.get("card_id", ""),
                "card_type": item.get("card_type", ""),
                "title": item.get("title", ""),
                "content": item.get("content", ""),
                "source_ref": item.get("source_ref", ""),
                "status": item.get("status", "draft"),
                "linked_chunks": item.get("linked_chunks") or [],
                "embedding": embedding,
            })
        self.client.insert(collection_name=self.collection_name, data=data)

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        filters: dict | None = None,
    ) -> list[dict]:
        fields = ["card_id", "card_type", "title", "content", "source_ref", "status", "linked_chunks"]

        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_embedding],
            limit=top_k,
            filter=_build_filter_expr(filters) if filters else "",
            output_fields=fields,
        )

        hits = []
        for hit in results[0]:
            hits.append({
                "card_id": hit["entity"].get("card_id"),
                "card_type": hit["entity"].get("card_type"),
                "title": hit["entity"].get("title"),
                "content": hit["entity"].get("content"),
                "source_ref": hit["entity"].get("source_ref"),
                "status": hit["entity"].get("status"),
                "linked_chunks": hit["entity"].get("linked_chunks") or [],
                "score": float(hit["distance"]),
            })

        return hits

    def get_card(self, card_id: str) -> dict | None:
        results = self.client.query(
            collection_name=self.collection_name,
            filter=f'card_id == "{card_id}"',
            output_fields=["card_id", "card_type", "title", "content", "source_ref", "status", "linked_chunks", "embedding"],
            limit=1,
        )
        return results[0] if results else None

    def update_card_status(self, card_id: str, status: str) -> dict | None:
        card = self.get_card(card_id)
        if not card:
            return None
        card["status"] = status
        _upsert(self.client, self.collection_name, [card])
        return card

    def count(self) -> int:
        try:
            rows = self.client.query(
                collection_name=self.collection_name,
                filter='card_id != ""',
                output_fields=["card_id"],
                limit=10000,
            )
            return len(rows)
        except Exception:
            return 0

    def clear(self) -> None:
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)
        self._ensure_collection()


def _build_filter_expr(filters: dict) -> str:
    conditions = []
    for key, value in filters.items():
        if isinstance(value, str):
            conditions.append(f'{key} == "{value}"')
        elif isinstance(value, list):
            values = ",".join(f'"{v}"' for v in value)
            conditions.append(f"{key} in [{values}]")
        else:
            conditions.append(f"{key} == {value}")
    return " and ".join(conditions)


def _upsert(client, collection_name: str, data: list[dict]) -> None:
    if hasattr(client, "upsert"):
        client.upsert(collection_name=collection_name, data=data)
        return
    ids = [
        row.get("chunk_id") or row.get("card_id")
        for row in data
        if row.get("chunk_id") or row.get("card_id")
    ]
    primary_field = "chunk_id" if data and data[0].get("chunk_id") else "card_id"
    if ids:
        values = ",".join(f'"{item}"' for item in ids)
        client.delete(collection_name=collection_name, filter=f"{primary_field} in [{values}]")
    client.insert(collection_name=collection_name, data=data)
