import pytest


@pytest.mark.asyncio
async def test_apply_card_status_updates_pg_wiki_only(monkeypatch):
    from app.services import review_service

    calls: list[tuple[str, object, object]] = []

    class FakeResult:
        def __iter__(self):
            return iter([("chunk-a",), ("chunk-b",)])

    class FakeSession:
        async def execute(self, query, params=None):
            calls.append(("pg_execute", str(query), params))
            if "SELECT chunk_id" in str(query):
                return FakeResult()
            return None

        async def commit(self):
            calls.append(("pg_commit", "", None))

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_init_database():
        calls.append(("pg_init", "", None))

    monkeypatch.setattr(review_service, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(review_service, "init_database", fake_init_database)

    result = await review_service.apply_card_status_to_indexes("card-1", "approved")

    assert result["linked_chunks"] == ["chunk-a", "chunk-b"]
    assert result["errors"] == []
    assert not any("Elasticsearch" in str(call) or "Milvus" in str(call) for call in calls)
    assert any("UPDATE wiki_cards" in query for _, query, _ in calls)
