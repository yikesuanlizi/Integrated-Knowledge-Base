from __future__ import annotations

import asyncio


def test_compile_status_counts_pg_wiki_cards(monkeypatch):
    from app.api import compile as compile_api

    calls: list[str] = []

    async def fake_count(table_name: str, where: str = "", params=None) -> int:
        calls.append(f"{table_name}:{where}")
        return 3

    monkeypatch.setattr(compile_api, "_count_pg_rows", fake_count)

    result = asyncio.run(compile_api.get_compile_status("build-1"))

    assert result["status"] == "completed"
    assert result["card_count"] == 3
    assert calls == ["wiki_cards:build_id = :build_id"]


def test_wiki_api_lists_cards_from_pg(monkeypatch):
    from app.api import wiki

    async def fake_list_cards(page: int, page_size: int, card_type=None, status=None, keyword: str = ""):
        assert page == 1
        assert page_size == 20
        assert status == "approved"
        return (
            [
                {
                    "card_id": "card-1",
                    "card_type": "concept",
                    "title": "ATA 32",
                    "content": "起落架系统",
                    "source_ref": "build-1",
                    "confidence": 0.9,
                    "status": "approved",
                    "linked_chunks": ["chunk-1"],
                    "score": 1.0,
                    "created_at": "2026-01-01T00:00:00",
                }
            ],
            1,
        )

    monkeypatch.setattr(wiki, "_list_pg_cards", fake_list_cards)

    result = asyncio.run(wiki.list_wiki_cards(status="approved"))

    assert result["total"] == 1
    assert result["cards"][0]["card_id"] == "card-1"
    assert result["cards"][0]["content"] == "起落架系统"


def test_knowledge_overview_reports_pg_wiki_and_chunk_indexes(monkeypatch):
    from app.api import knowledge

    async def fake_count_pg_table(table_name: str) -> int:
        return {"documents": 2, "wiki_cards": 4}.get(table_name, 0)

    async def fake_count_pg_by_status(table_name: str, status: str) -> int:
        assert table_name == "wiki_cards"
        return {"review": 1, "approved": 2, "rejected": 1}.get(status, 0)

    async def fake_load_index_counts():
        return 42, 42, 7

    monkeypatch.setattr(knowledge, "_count_pg_table", fake_count_pg_table)
    monkeypatch.setattr(knowledge, "_count_pg_by_status", fake_count_pg_by_status)
    monkeypatch.setattr(knowledge, "_load_index_counts", fake_load_index_counts)
    monkeypatch.setattr(knowledge, "_count_documents_from_es", lambda: 0)

    result = asyncio.run(knowledge.get_knowledge_overview())

    assert result.documents == 2
    assert result.wiki_cards == 4
    assert result.indexes.milvus_chunks == 42
    assert result.indexes.es_chunks == 42
    assert not hasattr(result.indexes, "milvus_cards")
    assert not hasattr(result.indexes, "es_cards")
    assert result.reviews.pending == 1
    assert result.qa_ready.approved_cards == 2


def test_review_api_lists_pg_wiki_reviews(monkeypatch):
    from app.api import review
    import asyncio

    async def fake_list(page: int, page_size: int, status: str | None = None):
        assert page == 1
        assert page_size == 20
        assert status == "review"
        return (
            [
                {
                    "review_id": "card-1:review",
                    "card_id": "card-1",
                    "card_title": "ATA 32 起落架系统",
                    "status": "review",
                    "reviewer": "system",
                    "notes": "warning only",
                    "created_at": "2026-01-01T00:00:00",
                }
            ],
            1,
        )

    async def fake_stats():
        return {"total": 1, "pending_review": 1, "approved": 0, "rejected": 0}

    monkeypatch.setattr(review, "list_pg_wiki_reviews", fake_list)
    monkeypatch.setattr(review, "get_pg_wiki_review_stats", fake_stats)

    result = asyncio.run(review.list_review_queue(status="review"))
    stats = asyncio.run(review.get_review_stats())

    assert result["total"] == 1
    assert result["reviews"][0]["card_id"] == "card-1"
    assert stats["pending_review"] == 1


def test_knowledge_overview_uses_card_status_for_review_counts(monkeypatch):
    from app.api import knowledge

    async def fake_count_pg_table(table_name: str) -> int:
        return {"documents": 1, "chunks": 8, "wiki_cards": 50}.get(table_name, 0)

    async def fake_count_pg_by_status(table_name: str, status: str) -> int:
        assert table_name == "wiki_cards"
        return {"review": 3, "approved": 44, "rejected": 3}[status]

    async def fake_load_index_counts():
        return 8, 8, 2

    monkeypatch.setattr(knowledge, "_count_pg_table", fake_count_pg_table)
    monkeypatch.setattr(knowledge, "_count_pg_by_status", fake_count_pg_by_status)
    monkeypatch.setattr(knowledge, "_load_index_counts", fake_load_index_counts)
    monkeypatch.setattr(knowledge, "_count_documents_from_es", lambda: 0)

    result = asyncio.run(knowledge.get_knowledge_overview())

    assert result.wiki_cards == 50
    assert result.reviews.pending == 3
    assert result.reviews.approved == 44
    assert result.reviews.rejected == 3
    assert result.qa_ready.approved_cards == 44
