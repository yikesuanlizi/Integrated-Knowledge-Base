"""Tests for correctness enhancements: answer requirements, applicability, evidence roles, validation, rewrite, answer generation."""
from __future__ import annotations

from string import Template
from unittest.mock import MagicMock

import pytest

from app.agent.state import AgentState


class TestAnswerRequirementsExtraction:
    def test_extract_answer_requirements_hydraulic_pump_disassembly(self):
        from app.agent.nodes.extract_query import extract_answer_requirements

        query = "液压泵拆卸步骤和注意事项是什么？需要什么工具？"
        result = extract_answer_requirements(query)

        assert result["procedure"] is True
        assert result["warning"] is True
        assert result["tooling"] is True
        assert result["parameter"] is False

    def test_extract_answer_requirements_a320_pressure(self):
        from app.agent.nodes.extract_query import extract_answer_requirements

        query = "A320液压泵压力参数是多少？"
        result = extract_answer_requirements(query)

        assert result["parameter"] is True
        assert result["applicability"] is False

    def test_extract_answer_requirements_amm_29_chapter(self):
        from app.agent.nodes.extract_query import extract_answer_requirements

        query = "AMM 29章液压泵拆卸"
        result = extract_answer_requirements(query)

        assert result["procedure"] is True
        assert result["warning"] is False
        assert result["parameter"] is False
        assert result["tooling"] is False

    def test_extract_answer_requirements_simple_definition(self):
        from app.agent.nodes.extract_query import extract_answer_requirements

        query = "什么是液压泵"
        result = extract_answer_requirements(query)

        assert result["procedure"] is False
        assert result["warning"] is False
        assert result["parameter"] is False
        assert result["tooling"] is False


class TestApplicabilityFiltersExtraction:
    def test_extract_applicability_filters_a320(self):
        from app.agent.nodes.extract_query import extract_applicability_filters

        query = "A320液压泵拆卸"
        result = extract_applicability_filters(query)

        assert result["aircraft_model"] == "A320"

    def test_extract_applicability_filters_amm_29(self):
        from app.agent.nodes.extract_query import extract_applicability_filters

        query = "AMM 第29章"
        result = extract_applicability_filters(query)

        assert result["manual_type"] == "AMM"
        assert result["ata_chapter"] == "29"

    def test_extract_applicability_filters_b737ng_fim(self):
        from app.agent.nodes.extract_query import extract_applicability_filters

        query = "B737NG FIM 故障隔离"
        result = extract_applicability_filters(query)

        assert "B737" in result["aircraft_model"] or result["aircraft_model"] == "B737NG"
        assert result["manual_type"] == "FIM"


class TestEvidenceRolesMarking:
    def test_mark_evidence_roles_warning_block(self):
        from app.agent.nodes.build_evidence import _mark_evidence_roles

        chunk = {
            "chunk_id": "warn1",
            "content": "警告：拆卸前必须释放液压压力",
            "block_type": "warning",
        }
        roles = _mark_evidence_roles(chunk, "chunk")

        assert "warning" in roles

    def test_mark_evidence_roles_procedure_step(self):
        from app.agent.nodes.build_evidence import _mark_evidence_roles

        chunk = {
            "chunk_id": "proc1",
            "content": "1. 拆卸液压泵：首先断开管路接头，然后移除固定螺栓",
            "block_type": "",
        }
        roles = _mark_evidence_roles(chunk, "chunk")

        assert "procedure" in roles

    def test_mark_evidence_roles_parameter_torque(self):
        from app.agent.nodes.build_evidence import _mark_evidence_roles

        chunk = {
            "chunk_id": "param1",
            "content": "安装螺栓力矩 35Nm，确保紧固到位",
            "block_type": "",
        }
        roles = _mark_evidence_roles(chunk, "chunk")

        assert "parameter" in roles

    def test_mark_evidence_roles_tooling(self):
        from app.agent.nodes.build_evidence import _mark_evidence_roles

        chunk = {
            "chunk_id": "tool1",
            "content": "需要准备扳手、力矩扳手等工具进行拆卸",
            "block_type": "",
        }
        roles = _mark_evidence_roles(chunk, "chunk")

        assert "tooling" in roles


class TestValidateEvidenceCoverage:
    def test_validate_evidence_missing_requirements(self):
        from app.agent.nodes.validate_evidence import validate_evidence_node

        state = AgentState(
            question="液压泵拆卸步骤和注意事项",
            answer_requirements={
                "procedure": True,
                "warning": True,
                "parameter": False,
                "applicability": False,
                "tooling": False,
            },
            evidence_roles={"chunk1": ["procedure"]},
            evidence_pack={
                "chunk_count": 2,
                "card_count": 0,
                "structured_metadata_count": 0,
                "total_items": 2,
                "evidence_items": [{"type": "chunk"}],
                "sufficient": True,
                "score": 0.8,
                "reasons": [],
                "blocked_by_review": False,
            },
            applicability_stats={
                "aircraft_models": [],
                "manual_types": [],
                "ata_chapters": [],
                "revisions": [],
            },
            applicability_filters={"aircraft_model": None},
            iteration=0,
            max_iterations=3,
            query_features={},
        )

        result = validate_evidence_node(state)

        assert "warning" in result.missing_requirements
        assert result.evidence_sufficiency["sufficient"] is False

    def test_validate_evidence_all_covered(self):
        from app.agent.nodes.validate_evidence import validate_evidence_node

        state = AgentState(
            question="液压泵拆卸",
            answer_requirements={
                "procedure": True,
                "warning": True,
                "parameter": False,
                "applicability": False,
                "tooling": False,
            },
            evidence_roles={"chunk1": ["procedure"], "chunk2": ["warning"]},
            evidence_pack={
                "chunk_count": 2,
                "card_count": 0,
                "structured_metadata_count": 0,
                "total_items": 2,
                "evidence_items": [{"type": "chunk"}, {"type": "chunk"}],
                "sufficient": True,
                "score": 0.9,
                "reasons": [],
                "blocked_by_review": False,
            },
            applicability_stats={
                "aircraft_models": [],
                "manual_types": [],
                "ata_chapters": [],
                "revisions": [],
            },
            applicability_filters={"aircraft_model": None},
            iteration=0,
            max_iterations=3,
            query_features={},
        )

        result = validate_evidence_node(state)

        assert result.missing_requirements == []
        assert result.applicability_conflict is False

    def test_validate_evidence_applicability_conflict(self):
        from app.agent.nodes.validate_evidence import validate_evidence_node

        state = AgentState(
            question="A320液压泵拆卸",
            answer_requirements={
                "procedure": True,
                "warning": False,
                "parameter": False,
                "applicability": False,
                "tooling": False,
            },
            evidence_roles={"chunk1": ["procedure"]},
            evidence_pack={
                "chunk_count": 2,
                "card_count": 0,
                "structured_metadata_count": 0,
                "total_items": 2,
                "evidence_items": [{"type": "chunk"}],
                "sufficient": True,
                "score": 0.7,
                "reasons": [],
                "blocked_by_review": False,
            },
            applicability_stats={
                "aircraft_models": ["B737"],
                "manual_types": [],
                "ata_chapters": [],
                "revisions": [],
            },
            applicability_filters={"aircraft_model": "A320"},
            iteration=0,
            max_iterations=3,
            query_features={},
        )

        result = validate_evidence_node(state)

        assert result.applicability_conflict is True
        assert result.evidence_sufficiency["sufficient"] is False

    def test_validate_evidence_no_aircraft_model_no_conflict(self):
        from app.agent.nodes.validate_evidence import validate_evidence_node

        state = AgentState(
            question="液压泵拆卸",
            answer_requirements={
                "procedure": True,
                "warning": False,
                "parameter": False,
                "applicability": False,
                "tooling": False,
            },
            evidence_roles={"chunk1": ["procedure"]},
            evidence_pack={
                "chunk_count": 2,
                "card_count": 0,
                "structured_metadata_count": 0,
                "total_items": 2,
                "evidence_items": [{"type": "chunk"}],
                "sufficient": True,
                "score": 0.8,
                "reasons": [],
                "blocked_by_review": False,
            },
            applicability_stats={
                "aircraft_models": ["B737"],
                "manual_types": [],
                "ata_chapters": [],
                "revisions": [],
            },
            applicability_filters={"aircraft_model": None},
            iteration=0,
            max_iterations=3,
            query_features={},
        )

        result = validate_evidence_node(state)

        assert result.applicability_conflict is False


class TestRuleBasedRewrite:
    def test_rule_based_rewrite_missing_warning(self):
        from app.agent.nodes.correct_answer import _rule_based_rewrite

        state = AgentState(
            question="液压泵拆卸步骤",
            original_question="液压泵拆卸步骤",
            missing_requirements=["warning"],
            applicability_conflict=False,
            applicability_filters={},
            planner_feedback={"reasons": []},
            entities={},
        )

        result = _rule_based_rewrite(state)
        rewritten = result["rewritten_query"]

        assert "注意事项" in rewritten or "警告" in rewritten or "warning" in rewritten.lower()

    def test_rule_based_rewrite_applicability_conflict_a320(self):
        from app.agent.nodes.correct_answer import _rule_based_rewrite

        state = AgentState(
            question="液压泵拆卸",
            original_question="液压泵拆卸",
            missing_requirements=[],
            applicability_conflict=True,
            applicability_filters={"aircraft_model": "A320"},
            planner_feedback={"reasons": []},
            entities={},
        )

        result = _rule_based_rewrite(state)
        rewritten = result["rewritten_query"]

        assert "A320" in rewritten

    def test_correct_answer_fallback_on_llm_failure(self, monkeypatch):
        from app.agent.nodes import correct_answer
        from app.agent.nodes.correct_answer import correct_answer_node

        def fake_generate_sync(*args, **kwargs):
            raise RuntimeError("LLM unavailable")

        monkeypatch.setattr(correct_answer.llm_client, "generate_sync", fake_generate_sync)

        state = AgentState(
            question="液压泵拆卸步骤",
            original_question="液压泵拆卸步骤",
            missing_requirements=["warning"],
            applicability_conflict=True,
            applicability_filters={"aircraft_model": "A320"},
            planner_feedback={"reasons": ["缺少证据类型: warning"]},
            entities={},
            iteration=0,
            max_iterations=3,
            reranked_results=[],
            query_features={},
        )

        result = correct_answer_node(state)

        assert result.iteration == 1
        assert len(result.rewrite_history) == 1
        assert result.rewrite_history[0]["fallback_used"] is True
        assert "A320" in result.question
        assert "警告" in result.question or "注意事项" in result.question


class TestGenerateAnswerPrompt:
    def _make_state_with_context(self, **kwargs):
        default_pack = {
            "chunk_count": 1,
            "card_count": 0,
            "structured_metadata_count": 0,
            "total_items": 1,
            "evidence_items": [
                {
                    "type": "chunk",
                    "content": "液压泵拆卸需要先释放压力。",
                    "source_file": "AMM 29-11",
                }
            ],
        }
        state_kwargs = {
            "question": "液压泵怎么拆？",
            "original_question": "液压泵怎么拆？",
            "evidence_pack": default_pack,
        }
        state_kwargs.update(kwargs)
        state = AgentState(**state_kwargs)
        return state

    def test_generate_answer_prompt_contains_history_boundary(self, monkeypatch):
        from app.agent.nodes import generate_answer as ga_mod

        captured_messages = {}

        def fake_build_context(pack, max_tokens=8000):
            return "## 证据 1\n液压泵拆卸需要先释放压力。"

        def fake_get_prompt(name):
            return ("BASE SYSTEM PROMPT", Template("$question\n\n$context"))

        def fake_generate_sync(messages=None, **kwargs):
            captured_messages["system"] = messages[0]["content"]
            captured_messages["user"] = messages[1]["content"]
            return "测试答案内容"

        monkeypatch.setattr(ga_mod, "build_context_for_llm", fake_build_context)
        monkeypatch.setattr(ga_mod, "get_prompt", fake_get_prompt)
        monkeypatch.setattr(ga_mod.llm_client, "generate_sync", fake_generate_sync)

        state = self._make_state_with_context()
        ga_mod._run_sync(state)

        system_prompt = captured_messages["system"]
        assert "历史" in system_prompt or "conversation_context" in system_prompt
        assert "指代" in system_prompt or "不是事实来源" in system_prompt

    def test_generate_answer_prompt_contains_applicability_when_summary_present(self, monkeypatch):
        from app.agent.nodes import generate_answer as ga_mod

        captured_messages = {}

        def fake_build_context(pack, max_tokens=8000):
            return "## 证据 1\n液压泵拆卸内容。"

        def fake_get_prompt(name):
            return ("BASE SYSTEM PROMPT", Template("$question\n\n$context"))

        def fake_generate_sync(messages=None, **kwargs):
            captured_messages["system"] = messages[0]["content"]
            return "测试答案"

        monkeypatch.setattr(ga_mod, "build_context_for_llm", fake_build_context)
        monkeypatch.setattr(ga_mod, "get_prompt", fake_get_prompt)
        monkeypatch.setattr(ga_mod.llm_client, "generate_sync", fake_generate_sync)

        state = self._make_state_with_context(
            applicability_summary="适用范围：A320 AMM 29章",
        )
        ga_mod._run_sync(state)

        system_prompt = captured_messages["system"]
        assert "适用范围" in system_prompt or "机型" in system_prompt or "ATA" in system_prompt

    def test_generate_answer_prompt_contains_conflict_warning(self, monkeypatch):
        from app.agent.nodes import generate_answer as ga_mod

        captured_messages = {}

        def fake_build_context(pack, max_tokens=8000):
            return "## 证据 1\n测试内容。"

        def fake_get_prompt(name):
            return ("BASE SYSTEM PROMPT", Template("$question\n\n$context"))

        def fake_generate_sync(messages=None, **kwargs):
            captured_messages["system"] = messages[0]["content"]
            return "测试答案"

        monkeypatch.setattr(ga_mod, "build_context_for_llm", fake_build_context)
        monkeypatch.setattr(ga_mod, "get_prompt", fake_get_prompt)
        monkeypatch.setattr(ga_mod.llm_client, "generate_sync", fake_generate_sync)

        state = self._make_state_with_context(
            applicability_summary="适用范围：A320/B737",
            applicability_conflict=True,
        )
        ga_mod._run_sync(state)

        system_prompt = captured_messages["system"]
        assert "冲突" in system_prompt or "跨机型" in system_prompt or "版本" in system_prompt


class TestMilvusPrefilter:
    def test_build_filters_with_aircraft_model(self, monkeypatch):
        from app.agent.nodes import recall_chunks as rc_mod

        monkeypatch.setattr(rc_mod.config, "STRICT_REVIEW_GATE", True)

        state = AgentState(
            question="A320液压泵拆卸",
            applicability_filters={"aircraft_model": "A320"},
            query_features={},
        )

        filters = rc_mod._build_search_filters(state)

        assert filters is not None
        assert "status" in filters
        assert filters["status"] == "approved"
        assert "aircraft_model" in filters
        assert filters["aircraft_model"] == "A320"

    def test_build_filters_no_applicability(self, monkeypatch):
        from app.agent.nodes import recall_chunks as rc_mod

        monkeypatch.setattr(rc_mod.config, "STRICT_REVIEW_GATE", True)

        state = AgentState(
            question="液压泵拆卸",
            applicability_filters={"aircraft_model": None, "manual_type": None, "ata_chapter": None},
            query_features={},
        )

        filters = rc_mod._build_search_filters(state)

        if rc_mod.config.STRICT_REVIEW_GATE:
            assert filters is not None
            assert "status" in filters
            assert filters["status"] == "approved"
            assert len(filters) == 1
        else:
            assert filters is None

    def test_build_filters_with_all_conditions(self, monkeypatch):
        from app.agent.nodes import recall_chunks as rc_mod

        monkeypatch.setattr(rc_mod.config, "STRICT_REVIEW_GATE", True)

        state = AgentState(
            question="A320 AMM 29章液压泵拆卸",
            applicability_filters={
                "aircraft_model": "A320",
                "manual_type": "AMM",
                "ata_chapter": "29",
            },
            query_features={},
        )

        filters = rc_mod._build_search_filters(state)

        assert filters is not None
        assert "status" in filters
        assert filters["status"] == "approved"
        assert "aircraft_model" in filters
        assert filters["aircraft_model"] == "A320"
        assert "manual_type" in filters
        assert filters["manual_type"] == "AMM"
        assert "ata_chapter" in filters
        assert filters["ata_chapter"] == "29"


class TestApplicabilityMetadataPropagation:
    def test_milvus_insert_chunks_writes_applicability_metadata(self):
        from app.retrieval.milvus_repo import MilvusRepository

        captured = {}

        class FakeClient:
            def insert(self, collection_name, data):
                captured["collection_name"] = collection_name
                captured["data"] = data

        repo = MilvusRepository.__new__(MilvusRepository)
        repo.collection_name = "rag_chunks"
        repo.client = FakeClient()

        repo.insert_chunks(
            [
                {
                    "chunk_id": "chunk-1",
                    "doc_id": "build-1",
                    "raw_content": "A320 AMM 29 hydraulic pump removal.",
                    "aircraft_model": "A320",
                    "manual_type": "AMM",
                    "ata_chapter": "29",
                    "manual_revision": "REV-1",
                }
            ],
            [[0.1, 0.2]],
        )

        row = captured["data"][0]
        assert row["aircraft_model"] == "A320"
        assert row["manual_type"] == "AMM"
        assert row["ata_chapter"] == "29"
        assert row["manual_revision"] == "REV-1"

    def test_milvus_search_returns_applicability_metadata(self):
        from app.retrieval.milvus_repo import MilvusRepository

        captured = {}

        class FakeClient:
            def search(self, **kwargs):
                captured["output_fields"] = kwargs["output_fields"]
                return [[
                    {
                        "entity": {
                            "chunk_id": "chunk-1",
                            "doc_id": "build-1",
                            "raw_content": "A320 AMM 29 hydraulic pump removal.",
                            "aircraft_model": "A320",
                            "manual_type": "AMM",
                            "ata_chapter": "29",
                            "manual_revision": "REV-1",
                            "status": "approved",
                        },
                        "distance": 0.9,
                    }
                ]]

        repo = MilvusRepository.__new__(MilvusRepository)
        repo.collection_name = "rag_chunks"
        repo.client = FakeClient()

        results = repo.search([0.1, 0.2], top_k=1, filters={"aircraft_model": "A320"})

        assert "aircraft_model" in captured["output_fields"]
        assert "manual_type" in captured["output_fields"]
        assert "ata_chapter" in captured["output_fields"]
        assert results[0]["aircraft_model"] == "A320"
        assert results[0]["manual_type"] == "AMM"
        assert results[0]["ata_chapter"] == "29"
        assert results[0]["manual_revision"] == "REV-1"

    @pytest.mark.asyncio
    async def test_es_search_returns_applicability_metadata(self, monkeypatch):
        from app.retrieval import es_repo as es_mod
        from app.retrieval.es_repo import ElasticsearchRepository

        class FakeClient:
            async def search(self, **kwargs):
                return {
                    "hits": {
                        "hits": [
                            {
                                "_source": {
                                    "chunk_id": "chunk-1",
                                    "doc_id": "build-1",
                                    "raw_content": "A320 AMM 29 hydraulic pump removal.",
                                    "aircraft_model": "A320",
                                    "manual_type": "AMM",
                                    "ata_chapter": "29",
                                    "manual_revision": "REV-1",
                                    "status": "approved",
                                },
                                "_score": 1.0,
                            }
                        ]
                    }
                }

        monkeypatch.setattr(es_mod, "get_es_client", lambda: FakeClient())
        repo = ElasticsearchRepository()

        results = await repo.search("hydraulic pump", filters={"aircraft_model": "A320"})

        assert results[0]["aircraft_model"] == "A320"
        assert results[0]["manual_type"] == "AMM"
        assert results[0]["ata_chapter"] == "29"
        assert results[0]["manual_revision"] == "REV-1"


class TestPlannerBaselineAdjustment:
    def test_baseline_adjusts_for_missing_warning(self):
        from app.agent.nodes.plan_retrieval import _build_baseline_plan

        state = AgentState(
            question="液压泵拆卸步骤",
            iteration=1,
            planner_feedback={"missing_requirements": ["warning"]},
            planner_route="fact",
            query_features={},
        )

        baseline = _build_baseline_plan(state)

        assert "chunks" in baseline["selected_channels"]
        assert baseline["selected_channels"][0] == "chunks"
        assert baseline["rerank_profile"] == "safety_strict"
        assert "warning" in baseline["responded_to_missing"]

    def test_baseline_adjusts_for_applicability_conflict(self):
        from app.agent.nodes.plan_retrieval import _build_baseline_plan

        state = AgentState(
            question="A320液压泵拆卸",
            iteration=1,
            applicability_conflict=True,
            applicability_filters={"aircraft_model": "A320"},
            planner_route="fact",
            query_features={},
        )

        baseline = _build_baseline_plan(state)

        assert "chunks" in baseline["selected_channels"]
        assert baseline["selected_channels"][0] == "chunks"
        assert baseline["rerank_profile"] == "safety_strict"
        assert baseline["applicability_conflict"] is True

    def test_baseline_adjusts_for_missing_parameter(self):
        from app.agent.nodes.plan_retrieval import _build_baseline_plan

        state = AgentState(
            question="液压泵压力参数",
            iteration=1,
            planner_feedback={"missing_requirements": ["parameter"]},
            planner_route="fact",
            query_features={},
        )

        baseline = _build_baseline_plan(state)

        assert "chunks" in baseline["selected_channels"]
        assert "structured_metadata" in baseline["selected_channels"]
        assert "parameter" in baseline["responded_to_missing"]

    def test_first_iteration_no_adjustment(self):
        from app.agent.nodes.plan_retrieval import _build_baseline_plan

        state = AgentState(
            question="液压泵拆卸",
            iteration=0,
            planner_feedback={"missing_requirements": ["warning"]},
            applicability_conflict=True,
            planner_route="fact",
            query_features={},
        )

        baseline = _build_baseline_plan(state)

        assert baseline["missing_requirements"] == []
        assert baseline["applicability_conflict"] is False
        assert baseline["rerank_profile"] == "default"


class TestPlannerPromptEnhancement:
    def test_prompt_contains_missing_requirements_section(self):
        from app.agent.nodes.plan_retrieval import _build_baseline_plan, _build_planner_prompt

        state = AgentState(
            question="液压泵拆卸步骤",
            iteration=1,
            planner_feedback={"missing_requirements": ["warning"]},
            planner_route="fact",
            original_question="液压泵拆卸步骤",
            query_features={},
            keywords=[],
            entities={},
            rewrite_history=[],
        )

        baseline = _build_baseline_plan(state)
        system_prompt, user_prompt = _build_planner_prompt(state, baseline, iteration=1)

        assert "缺失的证据类型" in user_prompt
        assert "warning" in user_prompt

    def test_prompt_contains_applicability_conflict_section(self):
        from app.agent.nodes.plan_retrieval import _build_baseline_plan, _build_planner_prompt

        state = AgentState(
            question="A320液压泵拆卸",
            iteration=1,
            applicability_conflict=True,
            applicability_filters={"aircraft_model": "A320"},
            planner_route="fact",
            original_question="A320液压泵拆卸",
            query_features={},
            keywords=[],
            entities={},
            rewrite_history=[],
        )

        baseline = _build_baseline_plan(state)
        system_prompt, user_prompt = _build_planner_prompt(state, baseline, iteration=1)

        assert "适用性冲突" in user_prompt


class TestBuildAnswerMessages:
    def test_messages_contain_history_boundary_statement(self):
        from app.agent.nodes.generate_answer import build_answer_messages

        state = AgentState(
            question="液压泵拆卸步骤",
            original_question="液压泵拆卸步骤",
            evidence_pack={
                "context": "测试内容：液压泵拆卸步骤为1. 泄压 2. 拆管",
                "evidence_items": [{"type": "chunk", "content": "液压泵拆卸步骤为1. 泄压 2. 拆管", "source_file": "AMM.pdf"}],
                "chunk_count": 1,
                "card_count": 0,
                "structured_metadata_count": 0,
            },
        )

        messages, early_answer = build_answer_messages(state)

        assert early_answer is None
        assert len(messages) == 2
        system_prompt = messages[0]["content"]
        assert "历史" in system_prompt
        assert "不是事实来源" in system_prompt or "不作为事实证据" in system_prompt

    def test_messages_contain_applicability_summary(self):
        from app.agent.nodes.generate_answer import build_answer_messages

        state = AgentState(
            question="A320液压泵拆卸",
            original_question="A320液压泵拆卸",
            evidence_pack={
                "context": "A320液压泵拆卸：1. 泄压 2. 拆管",
                "evidence_items": [{"type": "chunk", "content": "A320液压泵拆卸步骤", "source_file": "A320_AMM.pdf"}],
                "chunk_count": 1,
                "card_count": 0,
                "structured_metadata_count": 0,
            },
            applicability_summary="适用于A320 AMM",
            applicability_conflict=False,
        )

        messages, early_answer = build_answer_messages(state)

        assert early_answer is None
        system_prompt = messages[0]["content"]
        user_prompt = messages[1]["content"]
        assert "适用范围" in system_prompt
        assert "A320" in user_prompt

    def test_messages_contain_applicability_conflict_warning(self):
        from app.agent.nodes.generate_answer import build_answer_messages

        state = AgentState(
            question="A320液压泵拆卸",
            original_question="A320液压泵拆卸",
            evidence_pack={
                "context": "液压泵拆卸步骤",
                "evidence_items": [{"type": "chunk", "content": "B737液压泵拆卸步骤", "source_file": "B737_AMM.pdf"}],
                "chunk_count": 1,
                "card_count": 0,
                "structured_metadata_count": 0,
            },
            applicability_summary="证据主要来自B737",
            applicability_conflict=True,
        )

        messages, early_answer = build_answer_messages(state)

        assert early_answer is None
        system_prompt = messages[0]["content"]
        assert "跨机型/版本冲突" in system_prompt

    def test_no_context_returns_early_answer(self):
        from app.agent.nodes.generate_answer import build_answer_messages

        state = AgentState(
            question="xxx",
            original_question="xxx",
            evidence_pack={
                "context": "",
                "evidence_items": [],
                "chunk_count": 0,
                "card_count": 0,
                "structured_metadata_count": 0,
            },
        )

        messages, early_answer = build_answer_messages(state)

        assert early_answer is not None
        assert "没有找到充分" in early_answer
        assert state.needs_clarification is True

    def test_only_structured_metadata_returns_early_answer(self):
        from app.agent.nodes.generate_answer import build_answer_messages

        state = AgentState(
            question="知识库有哪些字段",
            original_question="知识库有哪些字段",
            evidence_pack={
                "context": "结构化元数据：wiki_cards.status是审核状态字段",
                "evidence_items": [{"type": "structured_metadata", "name": "wiki_cards.status", "description": "审核状态"}],
                "chunk_count": 0,
                "card_count": 0,
                "structured_metadata_count": 1,
            },
        )

        messages, early_answer = build_answer_messages(state)

        assert early_answer is not None
        assert "结构化元数据" in early_answer


class TestStreamPipelineCompleteness:
    def test_stream_imports_correct_answer_node(self):
        from app.api import query as query_mod

        assert query_mod.correct_answer_node is not None
        assert query_mod.validate_evidence_node is not None
        assert query_mod.build_answer_messages is not None

    def test_recall_nodes_list_contains_all_required_nodes(self):
        from app.api.query import _RECALL_NODES, _CORRECTION_NODES

        recall_names = [n[0] for n in _RECALL_NODES]
        assert "context_builder" in recall_names
        assert "classify_intent" in recall_names
        assert "extract_query" in recall_names
        assert "plan_retrieval" in recall_names
        assert "recall_dispatch" in recall_names
        assert "merge_results" in recall_names
        assert "expand_graph" in recall_names
        assert "rerank" in recall_names
        assert "build_evidence" in recall_names

        correction_names = [n[0] for n in _CORRECTION_NODES]
        assert "correct_answer" in correction_names
        assert "extract_query" in correction_names
        assert "plan_retrieval" in correction_names
        assert "recall_dispatch" in correction_names

    def test_correction_loop_clears_previous_results(self):
        """correct_answer_node 会清空上一轮结果，确保重检索不会与旧结果混淆。"""
        from app.agent.nodes.correct_answer import correct_answer_node

        state = AgentState(
            question="液压泵拆卸",
            original_question="液压泵拆卸",
            iteration=0,
            planner_feedback={
                "sufficient": False,
                "reasons": ["缺少证据类型: warning"],
                "missing_requirements": ["warning"],
                "wiki_count": 1,
                "chunk_count": 1,
                "entity_count": 0,
                "structured_count": 0,
                "applicability_conflict": False,
                "applicability_stats": {},
                "applicability_filters": {},
            },
            wiki_results=[{"card_id": "c1"}],
            chunk_results=[{"chunk_id": "ch1"}],
            entity_results=[],
            structured_results=[],
            merged_results=[{"id": "c1"}],
            expanded_results=[{"id": "c1"}],
            reranked_results=[{"id": "c1"}],
            evidence_pack={"evidence_items": [{"id": "c1"}]},
            citations=[{"id": "c1"}],
            retrieval_plan={"selected_channels": ["wiki"]},
            rewrite_history=[],
        )

        result = correct_answer_node(state)

        assert result.iteration == 1
        assert result.wiki_results == []
        assert result.chunk_results == []
        assert result.merged_results == []
        assert result.reranked_results == []
        assert result.evidence_pack == {}
        assert result.citations == []
        assert result.retrieval_plan == {}
