from app.agent.state import AgentState
from app.models.schemas import QueryRequest


def test_query_request_accepts_conversation_context():
    request = QueryRequest(
        question="它怎么拆？",
        conversation_id="conv-hydraulic",
        history=[
            {"role": "user", "content": "液压泵有什么作用？"},
            {"role": "assistant", "content": "液压泵用于提供液压压力。"},
        ],
    )

    assert request.conversation_id == "conv-hydraulic"
    assert len(request.history) == 2
    assert request.history[0].content == "液压泵有什么作用？"


def test_agent_state_has_context_builder_fields():
    state = AgentState(question="它怎么拆？")

    assert state.raw_question == ""
    assert state.conversation_id == ""
    assert state.history == []
    assert state.resolved_question == ""
    assert state.reference_entities == []
    assert state.conversation_context == {}


from app.agent.nodes import context_builder
from app.agent.nodes.context_builder import context_builder_node


def test_context_builder_resolves_pronoun_with_llm(monkeypatch):
    def fake_generate_sync(*args, **kwargs):
        return """
        {
          "resolved_question": "液压泵拆卸步骤是什么？",
          "reference_entities": ["液压泵"],
          "topic": "液压泵维护",
          "used_history": true,
          "rewrite_reason": "用户用它指代上一轮提到的液压泵"
        }
        """

    monkeypatch.setattr(context_builder.llm_client, "generate_sync", fake_generate_sync)

    state = AgentState(
        question="它怎么拆？",
        raw_question="它怎么拆？",
        original_question="它怎么拆？",
        conversation_id="conv-1",
        history=[
            {"role": "user", "content": "液压泵有什么作用？"},
            {"role": "assistant", "content": "液压泵用于提供液压压力。"},
        ],
    )

    result = context_builder_node(state)

    assert result.raw_question == "它怎么拆？"
    assert result.original_question == "它怎么拆？"
    assert result.question == "液压泵拆卸步骤是什么？"
    assert result.resolved_question == "液压泵拆卸步骤是什么？"
    assert result.reference_entities == ["液压泵"]
    assert result.conversation_context["history_as_evidence"] is False
    assert result.retrieval_trace.conversation_context["history_as_evidence"] is False
    assert result.retrieval_trace.grounding["context_builder"]["used_history"] is True


def test_context_builder_falls_back_to_raw_question_when_llm_fails(monkeypatch):
    def fake_generate_sync(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(context_builder.llm_client, "generate_sync", fake_generate_sync)

    state = AgentState(
        question="它怎么拆？",
        raw_question="它怎么拆？",
        original_question="它怎么拆？",
        conversation_id="conv-2",
        history=[
            {"role": "user", "content": "液压泵有什么作用？"},
            {"role": "assistant", "content": "液压泵用于提供液压压力。"},
        ],
    )

    result = context_builder_node(state)

    assert result.question == "它怎么拆？"
    assert result.resolved_question == "它怎么拆？"
    assert result.conversation_context["fallback_used"] is True
    assert result.conversation_context["history_as_evidence"] is False


def test_context_builder_no_history_skips_llm():
    state = AgentState(
        question="液压泵有什么作用？",
        raw_question="液压泵有什么作用？",
        original_question="液压泵有什么作用？",
        conversation_id="conv-3",
        history=[],
    )

    result = context_builder_node(state)

    assert result.question == "液压泵有什么作用？"
    assert result.resolved_question == "液压泵有什么作用？"
    assert result.conversation_context["fallback_used"] is False
    assert result.conversation_context["used_history"] is False


def test_agent_graph_starts_with_context_builder():
    from app.agent import graph as graph_mod

    graph = graph_mod._build_graph().get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert "context_builder" in graph.nodes
    assert ("__start__", "context_builder") in edges
    assert ("context_builder", "classify_intent") in edges


def test_history_is_not_added_to_evidence_pack(monkeypatch):
    from app.agent.nodes import context_builder
    from app.agent.nodes.build_evidence import build_evidence_node

    def fake_generate_sync(*args, **kwargs):
        return """
        {
          "resolved_question": "液压泵拆卸步骤是什么？",
          "reference_entities": ["液压泵"],
          "topic": "液压泵维护",
          "used_history": true,
          "rewrite_reason": "消解它的指代"
        }
        """

    monkeypatch.setattr(context_builder.llm_client, "generate_sync", fake_generate_sync)

    state = AgentState(
        question="它怎么拆？",
        raw_question="它怎么拆？",
        original_question="它怎么拆？",
        history=[
            {"role": "user", "content": "液压泵有什么作用？"},
            {"role": "assistant", "content": "液压泵用于提供液压压力。"},
        ],
        reranked_results=[],
    )

    state = context_builder_node(state)
    state = build_evidence_node(state)

    assert state.evidence_pack.get("evidence_items", []) == []
    assert "液压泵用于提供液压压力" not in str(state.evidence_pack)
    assert state.retrieval_trace.conversation_context["history_as_evidence"] is False
