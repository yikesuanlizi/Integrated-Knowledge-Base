from __future__ import annotations

import asyncio


def test_plain_paragraph_missing_section_path_stays_auto_approved():
    from app.models.schemas import Chunk, ChunkMetadata
    from app.services.ingest_service import IngestService

    service = IngestService()
    review = service._auto_review_chunk(
        Chunk(
            chunk_id="chunk-1",
            doc_id="doc-1",
            content="这是一个正常的维修说明段落，长度足够，而且没有安全警示词，应该自动通过进入后续索引。",
            metadata=ChunkMetadata(block_type="paragraph", section_path="", page_numbers=[1]),
        )
    )

    assert review["status"] == "approved"
    assert "missing_section_path" not in review["reasons"]


def test_ingest_status_reports_pg_and_index_counts(monkeypatch):
    from app.api import ingest

    class FakeMilvusRepository:
        def count(self):
            return 5

    class FakeESRepository:
        async def count(self):
            return 7

    async def fake_count_pg_rows(table_name: str, where: str = "", params=None):
        if table_name != "chunks":
            return 2
        mapping = {
            "": 11,
            "status = 'approved'": 8,
            "status = 'review'": 2,
            "status = 'rejected'": 1,
        }
        return mapping[where]

    monkeypatch.setattr(ingest, "MilvusRepository", lambda: FakeMilvusRepository())
    monkeypatch.setattr(ingest, "ElasticsearchRepository", lambda: FakeESRepository())
    monkeypatch.setattr(ingest, "count_pg_rows", fake_count_pg_rows)

    result = asyncio.run(ingest.get_ingest_status())

    assert result["milvus_chunks"] == 5
    assert result["elasticsearch_chunks"] == 7
    assert result["documents"] == 2
    assert result["pg_chunks"] == 11
    assert result["approved_chunks"] == 8
    assert result["review_chunks"] == 2
    assert result["rejected_chunks"] == 1
