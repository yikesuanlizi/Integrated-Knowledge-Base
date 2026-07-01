from __future__ import annotations


def test_list_chunks_uses_match_all_for_empty_keyword(monkeypatch):
    import asyncio

    from app.api import knowledge

    calls: list[dict] = []

    class FakeESRepo:
        async def search(self, query, top_k=10, filters=None, from_=0):
            calls.append({"query": query, "top_k": top_k, "filters": filters, "from_": from_})
            return [
                {
                    "chunk_id": "chunk-1",
                    "doc_id": "build-1",
                    "content": "content",
                    "source_file": "manual.pdf",
                    "section_path": "1.1",
                    "block_type": "paragraph",
                    "page_numbers": [1],
                    "status": "approved",
                    "score": 1.0,
                }
            ]

        async def count(self):
            return 1

    monkeypatch.setattr(knowledge, "ElasticsearchRepository", FakeESRepo)

    result = asyncio.run(knowledge.list_chunks(keyword="", page=2, page_size=20))

    assert result.total == 1
    assert result.chunks[0].source_file == "manual.pdf"
    assert calls == [{"query": "", "top_k": 20, "filters": None, "from_": 20}]


def test_document_list_falls_back_to_es_chunks_when_pg_is_empty(monkeypatch):
    import asyncio

    from app.api import knowledge

    class FakeESRepo:
        async def search(self, query, top_k=1000, filters=None, from_=0):
            return [
                {"doc_id": "build-1", "source_file": "a.pdf"},
                {"doc_id": "build-1", "source_file": "a.pdf"},
                {"doc_id": "build-2", "source_file": "b.pdf"},
            ]

    monkeypatch.setattr(knowledge, "ElasticsearchRepository", FakeESRepo)

    result = asyncio.run(knowledge._list_documents_from_es("", 1, 20))

    assert result.total == 2
    assert [doc.file_name for doc in result.documents] == ["a.pdf", "b.pdf"]
    assert result.documents[0].chunk_count == 2


def test_reset_recreates_database_schema(monkeypatch):
    import asyncio

    from app.api import knowledge

    calls: list[str] = []

    class FakeSession:
        async def commit(self):
            calls.append("commit")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeMilvusRepo:
        def clear(self):
            calls.append("milvus")

    class FakeESRepo:
        async def clear(self):
            calls.append("es")

    class FakeMinio:
        def clear_bucket(self):
            calls.append("minio")

    async def fake_init_database():
        calls.append("init_database")

    monkeypatch.setattr(knowledge, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(knowledge, "_drop_table_if_exists", lambda session, table: None)
    monkeypatch.setattr(knowledge, "MilvusRepository", FakeMilvusRepo)
    monkeypatch.setattr(knowledge, "WikiCardMilvusRepository", FakeMilvusRepo)
    monkeypatch.setattr(knowledge, "ElasticsearchRepository", FakeESRepo)
    monkeypatch.setattr(knowledge, "WikiCardESRepository", FakeESRepo)
    monkeypatch.setattr(knowledge, "EntityESRepository", FakeESRepo)
    monkeypatch.setattr(knowledge, "minio_client_manager", FakeMinio())
    monkeypatch.setattr("app.core.database.init_database", fake_init_database)

    result = asyncio.run(knowledge.reset_knowledge_storage())

    assert result["ok"] is True
    assert "init_database" in calls
