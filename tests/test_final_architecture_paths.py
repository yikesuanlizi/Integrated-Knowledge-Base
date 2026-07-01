from __future__ import annotations

import asyncio


def test_ingest_indexes_only_auto_approved_chunks(monkeypatch):
    from app.models.schemas import Chunk, ChunkMetadata, DocumentMetadata
    from app.services.ingest_service import IngestService

    service = IngestService()
    indexed_chunks: list[dict] = []
    indexed_entities: list[dict] = []

    class FakeESRepo:
        async def create_index(self):
            return None

        async def index_chunk(self, chunk):
            indexed_chunks.append(chunk)

    class FakeEntityRepo:
        async def create_index(self):
            return None

        async def index_entity(self, entity):
            indexed_entities.append(entity)

    class FakeMilvusRepo:
        def insert_chunks(self, chunks, embeddings):
            indexed_chunks.extend(chunks)

    monkeypatch.setattr(service, "_es_repo", FakeESRepo())
    monkeypatch.setattr(service, "_entity_repo", FakeEntityRepo())
    monkeypatch.setattr(service, "_milvus_repo", FakeMilvusRepo())
    monkeypatch.setattr("app.services.ingest_service.embedding_client.embed", lambda texts: [[0.1] * 3 for _ in texts])

    chunks = [
        Chunk(chunk_id="approved-1", doc_id="doc-1", content="正常段落，长度足够，ATA32 起落架系统说明。", metadata=ChunkMetadata(block_type="paragraph", section_path="1.1", page_numbers=[1])),
        Chunk(chunk_id="review-1", doc_id="doc-1", content="短", metadata=ChunkMetadata(block_type="ocr_text", section_path="", page_numbers=[2])),
    ]

    asyncio.run(service._store_chunks(chunks, "build-1", DocumentMetadata()))

    approved_ids = {item["chunk_id"] for item in indexed_chunks if isinstance(item, dict)}
    assert "approved-1" in approved_ids
    assert "review-1" not in approved_ids


def test_intent_routes_match_final_architecture():
    from app.retrieval.intent import classify_intent

    assert classify_intent("ATA27 是什么系统").route == "concept"
    assert classify_intent("更换主轮需要什么工具").route == "fact"
    assert classify_intent("退款和取消有什么区别").route == "complex"


def test_wiki_card_types_are_final_five():
    from app.compiler.wiki_cards import WikiCardType

    assert {item.value for item in WikiCardType} == {
        "definition",
        "concept",
        "procedure",
        "faq",
        "fault",
    }


def test_chunk_uses_three_layer_content_model():
    from app.models.schemas import Chunk

    chunk = Chunk(
        raw_content="RAW",
        search_content="SEARCH",
        embedding_content="EMBED",
    )

    assert chunk.raw_content == "RAW"
    assert chunk.search_content == "SEARCH"
    assert chunk.embedding_content == "EMBED"
    assert chunk.content == "RAW"


def test_ingest_indexes_search_and_embedding_content(monkeypatch):
    from app.models.schemas import Chunk, ChunkMetadata, DocumentMetadata
    from app.services.ingest_service import IngestService
    import asyncio

    service = IngestService()
    milvus_rows: list[dict] = []
    es_rows: list[dict] = []
    embedded_texts: list[str] = []

    class FakeESRepo:
        async def create_index(self):
            return None

        async def index_chunk(self, chunk):
            es_rows.append(chunk)

    class FakeEntityRepo:
        async def create_index(self):
            return None

        async def index_entity(self, entity):
            return None

    class FakeMilvusRepo:
        def insert_chunks(self, chunks, embeddings):
            milvus_rows.extend(chunks)

    async def fake_embed(texts):
        embedded_texts.extend(texts)
        return [[0.1] * 3 for _ in texts]

    monkeypatch.setattr(service, "_es_repo", FakeESRepo())
    monkeypatch.setattr(service, "_entity_repo", FakeEntityRepo())
    monkeypatch.setattr(service, "_milvus_repo", FakeMilvusRepo())
    monkeypatch.setattr("app.services.ingest_service.embedding_client.embed", fake_embed)

    chunk = Chunk(
        chunk_id="chunk-1",
        doc_id="doc-1",
        raw_content="AMM 32-41-00 Page 201\nmainte-\nnance instruction raw",
        search_content="maintenance instruction raw",
        embedding_content="maintenance instruction",
        metadata=ChunkMetadata(block_type="paragraph", section_path="1.1", page_numbers=[1]),
    )

    asyncio.run(service._store_chunks([chunk], "build-1", DocumentMetadata()))

    assert embedded_texts == ["maintenance instruction"]
    assert es_rows[0]["search_content"] == "maintenance instruction raw"
    assert es_rows[0]["raw_content"] == "AMM 32-41-00 Page 201\nmainte-\nnance instruction raw"
    assert milvus_rows[0]["embedding_content"] == "maintenance instruction"
    assert milvus_rows[0]["raw_content"] == "AMM 32-41-00 Page 201\nmainte-\nnance instruction raw"


def test_compile_phase1_uses_raw_content(monkeypatch):
    from app.compiler import pipeline
    from app.models.schemas import Chunk
    import asyncio

    captured: dict[str, str] = {}

    def fake_get_prompt(name: str):
        assert name == "concept_extraction"

        class Template:
            def substitute(self, **kwargs):
                captured["chunk_text"] = kwargs["chunk_text"]
                return kwargs["chunk_text"]

        return "system", Template()

    async def fake_call_llm_json(system, user_prompt, temperature=0.1):
        return []

    monkeypatch.setattr(pipeline, "get_prompt", fake_get_prompt)
    monkeypatch.setattr(pipeline, "call_llm_json", fake_call_llm_json)

    chunk = Chunk(
        chunk_id="chunk-1",
        doc_id="doc-1",
        raw_content="RAW evidence text",
        search_content="SEARCH text",
        embedding_content="EMBED text",
    )

    asyncio.run(pipeline.phase1_extract_concepts([chunk]))

    assert captured["chunk_text"] == "RAW evidence text"
