from __future__ import annotations

import asyncio


def test_ingest_triggers_auto_compile_when_approved_chunks_exist(monkeypatch):
    from app.models.schemas import Chunk, ChunkMetadata, DocumentMetadata
    from app.services.ingest_service import IngestService

    service = IngestService()
    calls: list[tuple[str, str]] = []

    async def fake_store_pg(*args, **kwargs):
        calls.append(("store_pg", "ok"))

    async def fake_store_chunks(*args, **kwargs):
        calls.append(("store_chunks", "ok"))

    async def fake_compile(build_id: str):
        calls.append(("compile", build_id))
        return {"status": "completed"}

    monkeypatch.setattr(service, "_store_pg_records", fake_store_pg)
    monkeypatch.setattr(service, "_store_chunks", fake_store_chunks)
    monkeypatch.setattr(service, "_store_source_file", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.ingest_service.parse_document", lambda path: type("Parsed", (), {"metadata": DocumentMetadata(), "artifact": type("Artifact", (), {"parser_name": "x", "parser_version": "1", "source_format": "pdf", "status": "ok", "page_count": 1, "warnings": (), "ocr_enabled": False})(), "blocks": []})())
    monkeypatch.setattr("app.services.ingest_service.chunk_document", lambda parsed: [Chunk(chunk_id="", doc_id="", content="正常段落，长度足够，ATA32 起落架系统说明。", metadata=ChunkMetadata(block_type="paragraph", section_path="1.1", page_numbers=[1]))])
    monkeypatch.setattr(service, "_auto_compile_if_needed", fake_compile)

    result = asyncio.run(service.ingest_file(b"demo", "demo.pdf"))

    assert result["build_id"]
    assert ("compile", result["build_id"]) in calls


def test_approve_chunk_indexes_and_triggers_compile(monkeypatch):
    from app.services import chunk_review_service

    calls: list[tuple[str, object]] = []

    async def fake_mark(chunk_id: str, status: str, reviewer: str, notes: str = ""):
        calls.append(("mark", (chunk_id, status, reviewer)))
        return {"chunk_id": chunk_id, "build_id": "build-1", "status": status}

    async def fake_index(chunk_id: str):
        calls.append(("index", chunk_id))
        return {"chunk_id": chunk_id, "status": "approved"}

    async def fake_compile(build_id: str):
        calls.append(("compile", build_id))
        return {"status": "completed"}

    monkeypatch.setattr(chunk_review_service, "_mark_chunk_status", fake_mark)
    monkeypatch.setattr(chunk_review_service, "_index_single_chunk", fake_index)
    monkeypatch.setattr(chunk_review_service, "_auto_compile_build", fake_compile)

    result = asyncio.run(chunk_review_service.approve_chunk("chunk-1", reviewer="tester"))

    assert result["chunk_id"] == "chunk-1"
    assert ("index", "chunk-1") in calls
    assert ("compile", "build-1") in calls


def test_approve_chunks_batches_compile_per_build(monkeypatch):
    from app.services import chunk_review_service

    calls: list[tuple[str, object]] = []
    build_map = {
        "chunk-1": "build-1",
        "chunk-2": "build-1",
        "chunk-3": "build-2",
    }

    async def fake_mark(chunk_id: str, status: str, reviewer: str, notes: str = ""):
        calls.append(("mark", (chunk_id, status, reviewer)))
        return {"chunk_id": chunk_id, "build_id": build_map[chunk_id], "status": status}

    async def fake_index(chunk_id: str):
        calls.append(("index", chunk_id))
        return {"chunk_id": chunk_id, "status": "approved"}

    async def fake_compile(build_id: str):
        calls.append(("compile", build_id))
        return {"status": "completed", "build_id": build_id}

    monkeypatch.setattr(chunk_review_service, "_mark_chunk_status", fake_mark)
    monkeypatch.setattr(chunk_review_service, "_index_single_chunk", fake_index)
    monkeypatch.setattr(chunk_review_service, "_auto_compile_build", fake_compile)

    result = asyncio.run(
        chunk_review_service.approve_chunks(
            ["chunk-1", "chunk-2", "chunk-1", "chunk-3"],
            reviewer="tester",
        )
    )

    assert result["approved_count"] == 3
    assert result["failed_count"] == 0
    assert {entry["build_id"] for entry in result["compile_results"]} == {"build-1", "build-2"}
    assert [call for call in calls if call[0] == "compile"] == [
        ("compile", "build-1"),
        ("compile", "build-2"),
    ]


def test_reject_chunks_marks_all_without_compile(monkeypatch):
    from app.services import chunk_review_service

    calls: list[tuple[str, object]] = []

    async def fake_mark(chunk_id: str, status: str, reviewer: str, notes: str = ""):
        calls.append(("mark", (chunk_id, status, reviewer)))
        return {"chunk_id": chunk_id, "build_id": "build-1", "status": status}

    async def fake_compile(build_id: str):
        calls.append(("compile", build_id))
        return {"status": "completed", "build_id": build_id}

    monkeypatch.setattr(chunk_review_service, "_mark_chunk_status", fake_mark)
    monkeypatch.setattr(chunk_review_service, "_auto_compile_build", fake_compile)

    result = asyncio.run(chunk_review_service.reject_chunks(["chunk-1", "chunk-2"], reviewer="tester"))

    assert result["rejected_count"] == 2
    assert result["failed_count"] == 0
    assert not any(call[0] == "compile" for call in calls)


def test_compile_fetches_only_approved_chunks(monkeypatch):
    from app.services import wiki_pg_service

    captured: dict[str, object] = {}

    class FakeResult:
        def mappings(self):
            return self

        def all(self):
            return []

    class FakeSession:
        async def execute(self, sql, params=None):
            captured["sql"] = str(sql)
            captured["params"] = params
            return FakeResult()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_init_database():
        return None

    monkeypatch.setattr(wiki_pg_service, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(wiki_pg_service, "init_database", fake_init_database)

    asyncio.run(wiki_pg_service.fetch_chunks_for_build("build-1"))

    assert "c.status = 'approved'" in captured["sql"]
    assert captured["params"] == {"build_id": "build-1"}
