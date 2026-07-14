from app.agent.state import AgentState


def test_recall_wiki_filters_to_approved_cards(monkeypatch):
    from app.agent.nodes import recall_wiki

    captured = {}

    async def fake_list_cards(page: int, page_size: int, card_type=None, status=None, keyword: str = "", **kwargs):
        captured["status"] = status
        return [], 0

    monkeypatch.setattr(recall_wiki, "list_pg_wiki_cards", fake_list_cards)

    result = recall_wiki.recall_wiki_node(AgentState(question="燃油系统拆卸步骤"))

    assert captured["status"] == "approved"
    assert "wiki_results" in result
    assert "chunk_results" in result
    assert "wiki_metadata" in result


def test_recall_wiki_strips_concept_suffixes():
    from app.agent.nodes import recall_wiki

    candidates = recall_wiki._wiki_query_candidates("机身最低点离地高度是什么意思？")

    assert candidates[0] == "机身最低点离地高度是什么意思？"
    assert "机身最低点离地高度" in candidates


def test_recall_wiki_falls_back_to_chunks_when_wiki_misses(monkeypatch):
    from app.agent.nodes import recall_wiki

    class FakeChunkRepo:
        def search(self, embedding, top_k=8, filters=None):
            return [{"chunk_id": "chunk-1", "content": "命中的原文切片", "status": "approved", "score": 0.9}]

    async def fake_list_cards(page: int, page_size: int, card_type=None, status=None, keyword: str = "", **kwargs):
        return [], 0

    monkeypatch.setattr(recall_wiki, "list_pg_wiki_cards", fake_list_cards)
    monkeypatch.setattr(recall_wiki, "build_query_vector", lambda query: [0.0] * 1536)
    monkeypatch.setattr(recall_wiki, "MilvusRepository", lambda: FakeChunkRepo())

    result = recall_wiki.recall_wiki_node(AgentState(question="机身最低点离地高度是什么意思？"))

    assert result["wiki_results"] == []
    assert len(result["chunk_results"]) == 1
    assert result["chunk_results"][0]["chunk_id"] == "chunk-1"
    assert "wiki_metadata" in result


def test_recall_chunks_filters_to_approved_chunks(monkeypatch):
    from app.agent.nodes import recall_chunks

    captured = {}

    class FakeChunkRepo:
        def search(self, embedding, top_k=8, filters=None):
            captured["filters"] = filters
            return []

    monkeypatch.setattr(recall_chunks, "build_query_vector", lambda query: [0.0] * 1536)
    monkeypatch.setattr(recall_chunks, "MilvusRepository", lambda: FakeChunkRepo())

    recall_chunks.recall_chunks_node(AgentState(question="燃油系统拆卸步骤"))

    assert captured["filters"] == {"status": "approved"}


def test_recall_entities_filters_to_approved_chunks(monkeypatch):
    from app.agent.nodes import recall_entities
    from app.agent.state import AgentState

    captured: list[tuple[str, dict | None]] = []

    class FakeESRepo:
        async def search_entities(self, query, entity_type="part_number", top_k=5, filters=None):
            captured.append(("search_entities", filters))
            return []

        async def search(self, query, top_k=5, filters=None):
            captured.append(("search", filters))
            return []

    monkeypatch.setattr(recall_entities, "ElasticsearchRepository", lambda: FakeESRepo())

    state = AgentState(question="粗燃油滤清器")
    state.entities = {"part_numbers": ["PN-1"], "components": ["粗燃油滤清器"]}

    recall_entities.recall_entities_node(state)

    assert captured == [
        ("search_entities", {"status": "approved"}),
        ("search", {"status": "approved"}),
    ]


def test_compile_cards_apply_review_policy_before_persist():
    from app.compiler.wiki_cards import WikiCard, WikiCardStatus, WikiCardType
    from app.services.compile_service import apply_review_policy_to_cards

    card = WikiCard(
        card_id="card-1",
        card_type=WikiCardType.PROCEDURE,
        title="无来源步骤",
        content="步骤内容",
        source_ref="build-1",
        confidence=0.9,
        status=WikiCardStatus.DRAFT,
        linked_chunks=[],
    )

    reviewed = apply_review_policy_to_cards([card])

    assert reviewed[0].status == WikiCardStatus.REVIEW


def test_compile_cards_do_not_hold_warning_only_no_specs():
    from app.compiler.wiki_cards import WikiCard, WikiCardStatus, WikiCardType
    from app.services.compile_service import apply_review_policy_to_cards

    card = WikiCard(
        card_id="card-2",
        card_type=WikiCardType.CONCEPT,
        title="电飞行控制系统",
        content="电飞行控制系统用于控制飞机姿态与操纵面响应，并通过多通道飞控计算机协调升降舵、副翼、方向舵与扰流板动作，支持不同飞行阶段的稳定控制与指令传递。该系统通过传感器采集飞行状态，经过控制律计算后输出舵面指令，同时在异常情况下提供冗余通道接管能力，以确保飞行操纵连续性、稳定性和可控性。",
        source_ref="build-1",
        confidence=0.95,
        status=WikiCardStatus.DRAFT,
        linked_chunks=["chunk-1"],
        facts=[{"statement": "用于控制飞机姿态", "source_ref": "chunk-1", "confidence": 0.9}],
    )

    reviewed = apply_review_policy_to_cards([card])

    assert reviewed[0].status == WikiCardStatus.APPROVED


def test_evidence_sufficiency_blocks_unapproved_evidence():
    from app.retrieval.context_build import calculate_evidence_sufficiency

    sufficiency = calculate_evidence_sufficiency(
        {
            "evidence_items": [
                {
                    "type": "chunk",
                    "chunk_id": "chunk-1",
                    "content": "待审核内容",
                    "status": "review",
                }
            ]
        },
        {"min_chunks": 1, "require_evidence": True},
    )

    assert sufficiency["sufficient"] is False
    assert sufficiency["blocked_by_review"] is True


def test_compile_does_not_sync_held_cards_to_chunk_indexes():
    from app.compiler.wiki_cards import WikiCard, WikiCardStatus, WikiCardType
    from app.services import compile_service

    cards = [
        WikiCard(
            card_id="card-review",
            card_type=WikiCardType.PROCEDURE,
            title="待审核卡片",
            content="content",
            source_ref="build-1",
            status=WikiCardStatus.REVIEW,
            linked_chunks=["chunk-1"],
        ),
        WikiCard(
            card_id="card-approved",
            card_type=WikiCardType.PROCEDURE,
            title="已审核卡片",
            content="content",
            source_ref="build-1",
            status=WikiCardStatus.APPROVED,
            linked_chunks=["chunk-2"],
        ),
    ]

    import asyncio

    result = asyncio.run(compile_service.sync_held_card_chunk_statuses(cards))

    assert result == []
