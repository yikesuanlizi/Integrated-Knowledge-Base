import pytest


@pytest.mark.asyncio
async def test_run_unified_query_is_agent_graph_wrapper(monkeypatch):
    from app.agent import orchestrator
    from app.agent.state import AgentState
    from app.models.schemas import RetrievalTrace

    captured = {}

    def fake_run_agent_sync(
        question: str,
        top_k: int = 8,
        conversation_id: str | None = None,
        history: list[dict] | None = None,
    ) -> AgentState:
        captured["question"] = question
        captured["top_k"] = top_k
        captured["conversation_id"] = conversation_id
        captured["history"] = history
        return AgentState(
            question="液压泵拆卸步骤是什么？",
            raw_question=question,
            original_question=question,
            answer="统一图回答",
            citations=[],
            retrieval_trace=RetrievalTrace(
                strategy="agent_graph",
                grounding={"structured_metadata": {"used": False}},
            ),
        )

    monkeypatch.setattr(orchestrator, "run_agent_sync", fake_run_agent_sync)

    history = [{"role": "user", "content": "液压泵有什么作用？"}]
    result = await orchestrator.run_unified_query(
        "它怎么拆？",
        top_k=7,
        conversation_id="conv-1",
        history=history,
    )

    assert captured == {
        "question": "它怎么拆？",
        "top_k": 7,
        "conversation_id": "conv-1",
        "history": history,
    }
    assert result.question == "它怎么拆？"
    assert result.answer == "统一图回答"
    assert result.mode == "evidence_lookup"
    assert result.retrieval_trace.strategy == "agent_graph"
    assert "orchestrator" not in result.retrieval_trace.grounding


def test_agent_graph_has_new_12_node_structure():
    from app.agent import graph as graph_mod

    graph = graph_mod._build_graph().get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert "context_builder" in graph.nodes
    assert "plan_retrieval" in graph.nodes
    assert "recall_dispatch" in graph.nodes
    assert ("__start__", "context_builder") in edges
    assert ("context_builder", "classify_intent") in edges
    assert ("extract_query", "plan_retrieval") in edges
    assert ("plan_retrieval", "recall_dispatch") in edges
    assert ("recall_dispatch", "merge_results") in edges
    assert "recall_structured_metadata" not in graph.nodes


def test_merge_results_includes_structured_metadata_source():
    from app.agent.nodes.merge_results import merge_results_node
    from app.agent.state import AgentState

    state = AgentState(
        question="哪些字段控制 Wiki 卡片审核状态",
        structured_results=[
            {
                "id": "structured:status",
                "content": "字段 wiki_cards.status 控制卡片审核状态。",
                "score": 0.9,
            }
        ],
    )
    state.query_features["top_k"] = 10

    merged = merge_results_node(state)

    assert any(item.get("source_type") == "structured_metadata" for item in merged.merged_results)


def test_build_evidence_packs_structured_metadata_without_citation():
    from app.agent.nodes.build_evidence import build_evidence_node
    from app.agent.state import AgentState

    state = AgentState(
        question="哪些字段控制 Wiki 卡片审核状态",
        reranked_results=[
            {
                "source_type": "structured_metadata",
                "content": "字段 wiki_cards.status 控制卡片审核状态。",
                "sql": "SELECT kind, name FROM nl2sql_column_info LIMIT 20",
                "score": 0.9,
            }
        ],
    )
    state.query_features["top_k"] = 8

    result = build_evidence_node(state)

    assert result.evidence_pack["structured_metadata_count"] == 1
    assert result.evidence_pack["evidence_items"][0]["type"] == "structured_metadata"
    assert result.citations == []
    assert result.sql_result["sql"].startswith("SELECT")


def test_procedure_question_does_not_trigger_structured_metadata_recall():
    from app.agent.nodes.recall_structured_metadata import recall_structured_metadata_node
    from app.agent.state import AgentState

    state = recall_structured_metadata_node(AgentState(question="粗燃油滤清器拆卸步骤是什么"))

    assert state.uses_structured_metadata is False
    assert state.structured_results == []
    assert state.sql_result == {}


def test_structured_metadata_recall_uses_llm_assist_when_keywords_are_weak(monkeypatch):
    from app.agent.nodes import recall_structured_metadata
    from app.agent.state import AgentState
    from app.nl2sql.schemas import NL2SQLQueryResponse

    def fake_run_llm_decision(question: str):
        return {
            "use_structured_metadata": True,
            "reason": "问题询问知识库如何判定可回答内容，需要查看审核状态和证据协议。",
        }

    def fake_run_query(question: str, limit: int):
        return NL2SQLQueryResponse(
            question=question,
            sql="SELECT kind, name FROM nl2sql_column_info LIMIT 20",
            columns=["kind", "name"],
            rows=[{"kind": "column", "name": "wiki_cards.status", "description": "审核状态"}],
            row_count=1,
            explanation="命中审核状态字段。",
            trace={"steps": [{"node": "llm_assisted_structured_recall"}]},
        )

    monkeypatch.setattr(recall_structured_metadata, "_run_llm_decision", fake_run_llm_decision)
    monkeypatch.setattr(recall_structured_metadata, "_run_query", fake_run_query)

    state = recall_structured_metadata.recall_structured_metadata_node(
        AgentState(question="这个知识库怎么判断哪些内容能回答")
    )

    assert state.uses_structured_metadata is True
    assert state.structured_results[0]["name"] == "wiki_cards.status"
    assert state.retrieval_trace.grounding["structured_metadata"]["decision"]["source"] == "llm"


@pytest.mark.asyncio
async def test_structured_metadata_alone_does_not_generate_fact_answer():
    from app.agent.nodes.generate_answer import generate_answer_node_async
    from app.agent.state import AgentState

    state = AgentState(
        question="哪些字段控制 Wiki 卡片审核状态",
        evidence_pack={
            "evidence_items": [
                {
                    "type": "structured_metadata",
                    "content": "wiki_cards.status 控制审核状态。",
                    "status": "approved",
                }
            ],
            "chunk_count": 0,
            "card_count": 0,
            "entity_count": 0,
            "structured_metadata_count": 1,
            "total_items": 1,
        },
    )

    result = await generate_answer_node_async(state)

    assert result.needs_clarification is True
    assert "不能生成独立事实答案" in result.answer


def test_concept_evidence_with_single_wiki_card_is_sufficient():
    from app.retrieval.context_build import calculate_evidence_sufficiency

    sufficiency = calculate_evidence_sufficiency(
        {
            "evidence_items": [
                {
                    "type": "wiki_card",
                    "card_id": "card-1",
                    "title": "可用燃油容量",
                    "content": "可用燃油容量是指发动机可用的燃油量。",
                    "status": "approved",
                }
            ],
            "chunk_count": 0,
            "card_count": 1,
            "entity_count": 0,
            "structured_metadata_count": 0,
            "total_items": 1,
        },
        {
            "min_chunks": 0,
            "min_cards": 1,
            "require_evidence": True,
            "route": "concept",
        },
    )

    assert sufficiency["sufficient"] is True
    assert sufficiency["card_count"] == 1


def test_fallback_answer_is_natural_for_single_wiki_card():
    from app.agent.nodes.generate_answer import _fallback_answer
    from app.agent.state import AgentState

    state = AgentState(
        question="可用燃油容量是什么意思？",
        evidence_pack={
            "evidence_items": [
                {
                    "type": "wiki_card",
                    "title": "可用燃油容量",
                    "content": "可用燃油容量是指在总燃油容量中扣除不可用燃油后的燃油量，可实际用于飞行与发动机工作。",
                    "source_ref": "doc-1",
                    "status": "approved",
                }
            ]
        },
    )

    answer = _fallback_answer(state)

    assert "关于「可用燃油容量是什么意思？」" not in answer
    assert "可用燃油容量是指" in answer
    assert "来源：" not in answer


def test_finalize_answer_text_strips_markdown_artifacts():
    from app.agent.nodes.generate_answer import _finalize_answer_text

    answer = _finalize_answer_text(
        "**可用燃油容量**是指供飞机发动机使用的燃油容量 [1]。\n\n"
        "## 具体数值\n"
        "- 体积：12.8 m³\n"
        "- 质量：10308 kg [1]"
    )

    assert "**" not in answer
    assert "##" not in answer
    assert "可用燃油容量是指供飞机发动机使用的燃油容量 [1]。" in answer
    assert "- 体积：12.8 m³" in answer


def test_finalize_answer_text_removes_system_process_phrasing():
    from app.agent.nodes.generate_answer import _finalize_answer_text

    answer = _finalize_answer_text(
        "根据原文和检索到的 Wiki 卡片，可用燃油容量是指供飞机发动机使用的燃油容量。"
    )

    assert "根据原文" not in answer
    assert "Wiki 卡片" not in answer
    assert "检索到的" not in answer
    assert answer.startswith("可用燃油容量是指")


def test_correct_answer_degrades_without_exposing_retrieval_process():
    from app.agent.nodes.correct_answer import correct_answer_node
    from app.agent.state import AgentState

    state = AgentState(
        question="可用燃油容量是什么意思？",
        reranked_results=[
            {
                "content": "可用燃油容量是供飞机发动机使用的燃油量。",
                "title": "可用燃油容量",
                "source_file": "doc-1",
            }
        ],
    )
    state.iteration = state.max_iterations - 1

    result = correct_answer_node(state)

    assert "经过多次检索" not in result.answer
    assert "证据可能不完整" not in result.answer
    assert "切片" not in result.answer
    assert "卡片" not in result.answer
