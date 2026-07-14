"""Mini Golden Set 验证脚本 - 正确性增强链路端到端节点级测试"""
from __future__ import annotations

import json
from string import Template
from typing import Any, Dict, List, Tuple

from app.agent.state import AgentState


def make_evidence_pack(chunk_count: int = 2, card_count: int = 0):
    return {
        "chunk_count": chunk_count,
        "card_count": card_count,
        "structured_metadata_count": 0,
        "total_items": chunk_count + card_count,
        "evidence_items": [{"type": "chunk"} for _ in range(chunk_count)] + [{"type": "card"} for _ in range(card_count)],
        "sufficient": True,
        "score": 0.8,
        "reasons": [],
        "blocked_by_review": False,
    }


def scenario_1_steps_plus_warning_missing_warning():
    """场景1：步骤+警告查询（覆盖检查应发现缺warning）"""
    try:
        from app.agent.nodes.extract_query import extract_answer_requirements
        from app.agent.nodes.validate_evidence import validate_evidence_node

        query = "液压泵拆卸步骤和注意事项"
        answer_reqs = extract_answer_requirements(query)

        if not answer_reqs.get("procedure"):
            return False, f"期望procedure=True, 实际为{answer_reqs.get('procedure')}"
        if not answer_reqs.get("warning"):
            return False, f"期望warning=True, 实际为{answer_reqs.get('warning')}"

        state = AgentState(
            question=query,
            answer_requirements=answer_reqs,
            evidence_roles={"chunk1": ["procedure"]},
            evidence_pack=make_evidence_pack(chunk_count=2),
            applicability_stats={"aircraft_models": set(), "manual_types": set(), "ata_chapters": set(), "revisions": set()},
            applicability_filters={"aircraft_model": None, "manual_type": None, "ata_chapter": None},
            iteration=0,
            max_iterations=3,
            query_features={},
        )

        result = validate_evidence_node(state)

        if "warning" not in result.missing_requirements:
            return False, f"期望missing_requirements包含'warning', 实际为{result.missing_requirements}"
        if result.evidence_sufficiency.get("sufficient") is not False:
            return False, f"期望sufficient=False, 实际为{result.evidence_sufficiency.get('sufficient')}"

        return True, "通过：正确检测到缺失warning证据类型"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_2_history_resolution_history_as_evidence_false(monkeypatch=None):
    """场景2：历史指代消解（验证history_as_evidence=False）"""
    try:
        from app.agent.nodes import context_builder as cb_mod
        from app.agent.nodes.context_builder import context_builder_node

        def mock_generate_sync(**kw):
            return json.dumps({
                "resolved_question": "液压泵怎么拆？",
                "reference_entities": ["液压泵"],
                "topic": "液压泵拆卸",
                "used_history": True,
                "rewrite_reason": "消解了'它'的指代"
            })

        monkeypatch.setattr(cb_mod.llm_client, "generate_sync", mock_generate_sync)

        state = AgentState(
            raw_question="它怎么拆？",
            question="它怎么拆？",
            original_question="",
            history=[
                {"role": "user", "content": "液压泵是什么？"},
                {"role": "assistant", "content": "液压泵是液压系统的动力元件。"}
            ],
            conversation_id="test-conv-001",
            query_features={},
        )

        result = context_builder_node(state)

        if result.conversation_context.get("history_as_evidence") is not False:
            return False, f"期望history_as_evidence=False, 实际为{result.conversation_context.get('history_as_evidence')}"
        if "query_rewrite_only" != result.conversation_context.get("history_used_for"):
            return False, f"期望history_used_for='query_rewrite_only', 实际为{result.conversation_context.get('history_used_for')}"
        if not result.resolved_question:
            return False, "resolved_question为空"

        return True, "通过：历史仅用于指代消解，不作为证据"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_3_specified_aircraft_model():
    """场景3：指定机型查询（适用性识别）"""
    try:
        from app.agent.nodes.extract_query import extract_applicability_filters, extract_answer_requirements

        query = "A320液压泵拆卸步骤"
        app_filters = extract_applicability_filters(query)
        answer_reqs = extract_answer_requirements(query)

        if app_filters.get("aircraft_model") != "A320":
            return False, f"期望aircraft_model='A320', 实际为{app_filters.get('aircraft_model')}"
        if not answer_reqs.get("procedure"):
            return False, f"期望procedure=True, 实际为{answer_reqs.get('procedure')}"

        return True, "通过：正确识别A320机型和procedure需求"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_4_cross_aircraft_conflict():
    """场景4：跨机型冲突检测"""
    try:
        from app.agent.nodes.validate_evidence import validate_evidence_node

        state = AgentState(
            question="A320液压泵拆卸",
            answer_requirements={"procedure": True, "warning": False, "parameter": False, "applicability": False, "tooling": False},
            evidence_roles={"chunk1": ["procedure"]},
            evidence_pack=make_evidence_pack(chunk_count=2),
            applicability_stats={"aircraft_models": {"B737"}, "manual_types": set(), "ata_chapters": set(), "revisions": set()},
            applicability_filters={"aircraft_model": "A320", "manual_type": None, "ata_chapter": None},
            iteration=0,
            max_iterations=3,
            query_features={},
        )

        result = validate_evidence_node(state)

        if result.applicability_conflict is not True:
            return False, f"期望applicability_conflict=True, 实际为{result.applicability_conflict}"
        if result.evidence_sufficiency.get("sufficient") is not False:
            return False, f"期望sufficient=False, 实际为{result.evidence_sufficiency.get('sufficient')}"

        return True, "通过：正确检测到跨机型冲突(A320 vs B737)"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_5_parameter_query():
    """场景5：参数查询（parameter requirement）"""
    try:
        from app.agent.nodes.extract_query import extract_answer_requirements

        query = "液压泵力矩参数是多少？"
        answer_reqs = extract_answer_requirements(query)

        if not answer_reqs.get("parameter"):
            return False, f"期望parameter=True, 实际为{answer_reqs.get('parameter')}"

        return True, "通过：正确识别parameter需求"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_6_tooling_query():
    """场景6：工具查询（tooling requirement）"""
    try:
        from app.agent.nodes.extract_query import extract_answer_requirements

        query = "更换液压泵需要什么工具？"
        answer_reqs = extract_answer_requirements(query)

        if not answer_reqs.get("tooling"):
            return False, f"期望tooling=True, 实际为{answer_reqs.get('tooling')}"

        return True, "通过：正确识别tooling需求"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_7_full_coverage_no_missing():
    """场景7：覆盖完整（不缺证据）"""
    try:
        from app.agent.nodes.validate_evidence import validate_evidence_node

        state = AgentState(
            question="液压泵拆卸步骤",
            answer_requirements={"procedure": True, "warning": False, "parameter": False, "applicability": False, "tooling": False},
            evidence_roles={"chunk1": ["procedure"]},
            evidence_pack=make_evidence_pack(chunk_count=2),
            applicability_stats={"aircraft_models": set(), "manual_types": set(), "ata_chapters": set(), "revisions": set()},
            applicability_filters={"aircraft_model": None, "manual_type": None, "ata_chapter": None},
            iteration=0,
            max_iterations=3,
            query_features={},
        )

        result = validate_evidence_node(state)

        if result.missing_requirements != []:
            return False, f"期望missing_requirements=[], 实际为{result.missing_requirements}"
        if result.applicability_conflict is not False:
            return False, f"期望applicability_conflict=False, 实际为{result.applicability_conflict}"

        return True, "通过：证据覆盖完整，无缺失无冲突"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_8_ata_chapter_recognition():
    """场景8：ATA章节识别"""
    try:
        from app.agent.nodes.extract_query import extract_applicability_filters

        query = "AMM 第29章液压系统维护"
        app_filters = extract_applicability_filters(query)

        if app_filters.get("manual_type") != "AMM":
            return False, f"期望manual_type='AMM', 实际为{app_filters.get('manual_type')}"
        if app_filters.get("ata_chapter") != "29":
            return False, f"期望ata_chapter='29', 实际为{app_filters.get('ata_chapter')}"

        return True, "通过：正确识别AMM手册和29章"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_9_rule_based_rewrite_add_warning_keywords():
    """场景9：correct_answer改写补充warning关键词"""
    try:
        from app.agent.nodes.correct_answer import _rule_based_rewrite

        state = AgentState(
            question="液压泵拆卸步骤",
            original_question="液压泵拆卸步骤",
            missing_requirements=["warning"],
            applicability_conflict=False,
            applicability_filters={},
            planner_feedback={"reasons": ["缺少证据类型: warning"]},
            entities={},
        )

        result = _rule_based_rewrite(state)
        rewritten = result["rewritten_query"]

        has_warning_kw = any(kw in rewritten for kw in ["注意事项", "警告", "小心", "warning", "caution"])
        if not has_warning_kw:
            return False, f"改写后query未包含warning相关关键词: {rewritten}"

        return True, f"通过：改写后query包含warning关键词: {rewritten}"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_10_rule_based_rewrite_add_aircraft_model():
    """场景10：correct_answer改写补充机型"""
    try:
        from app.agent.nodes.correct_answer import _rule_based_rewrite

        state = AgentState(
            question="液压泵拆卸",
            original_question="液压泵拆卸",
            missing_requirements=[],
            applicability_conflict=True,
            applicability_filters={"aircraft_model": "A320"},
            planner_feedback={"reasons": ["证据存在跨机型/版本冲突"]},
            entities={},
        )

        result = _rule_based_rewrite(state)
        rewritten = result["rewritten_query"]

        if "A320" not in rewritten:
            return False, f"改写后query未包含'A320': {rewritten}"

        return True, f"通过：改写后query包含机型A320: {rewritten}"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_11_generate_answer_history_boundary(monkeypatch=None):
    """场景11：generate_answer prompt包含历史边界声明"""
    try:
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

        state = AgentState(
            question="液压泵怎么拆？",
            original_question="液压泵怎么拆？",
            evidence_pack={
                "chunk_count": 1,
                "card_count": 0,
                "structured_metadata_count": 0,
                "total_items": 1,
                "evidence_items": [{"type": "chunk", "content": "测试"}],
            },
        )

        ga_mod._run_sync(state)

        system_prompt = captured_messages.get("system", "")
        has_history_note = ("conversation_context" in system_prompt and "指代" in system_prompt) or "不是事实来源" in system_prompt
        if not has_history_note:
            return False, f"system prompt未包含历史边界声明: {system_prompt[:200]}..."

        return True, "通过：system prompt包含历史仅用于指代消解、不是事实来源的声明"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_12_generate_answer_applicability_requirement(monkeypatch=None):
    """场景12：generate_answer prompt包含适用范围要求"""
    try:
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

        state = AgentState(
            question="A320液压泵拆卸",
            original_question="A320液压泵拆卸",
            evidence_pack={
                "chunk_count": 1,
                "card_count": 0,
                "structured_metadata_count": 0,
                "total_items": 1,
                "evidence_items": [{"type": "chunk", "content": "测试"}],
            },
            applicability_summary="适用范围：A320，AMM 29章",
        )

        ga_mod._run_sync(state)

        system_prompt = captured_messages.get("system", "")
        has_applicability_note = "适用范围" in system_prompt and ("标注" in system_prompt or "机型" in system_prompt or "末尾" in system_prompt)
        if not has_applicability_note:
            return False, f"system prompt未包含适用范围标注要求: {system_prompt[:200]}..."

        return True, "通过：system prompt包含适用范围标注要求"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_13_milvus_filter_with_aircraft_model(monkeypatch=None):
    """场景13：指定机型时Milvus带filter"""
    try:
        from app.agent.nodes import recall_chunks as rc_mod

        original_strict = rc_mod.config.STRICT_REVIEW_GATE
        rc_mod.config.STRICT_REVIEW_GATE = True

        try:
            state = AgentState(
                question="A320液压泵拆卸",
                applicability_filters={"aircraft_model": "A320"},
                query_features={},
            )

            filters = rc_mod._build_search_filters(state)

            if filters is None:
                return False, "期望filters不为None"
            if "aircraft_model" not in filters:
                return False, f"期望filters包含aircraft_model, 实际为{filters}"
            if filters["aircraft_model"] != "A320":
                return False, f"期望aircraft_model='A320', 实际为{filters['aircraft_model']}"

            return True, "通过：Milvus filter正确包含aircraft_model='A320'"
        finally:
            rc_mod.config.STRICT_REVIEW_GATE = original_strict
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_14_missing_requirements_baseline_channels(monkeypatch=None):
    """场景14：missing_requirements时baseline调整通道"""
    try:
        from app.agent.nodes.plan_retrieval import _build_baseline_plan

        state = AgentState(
            question="液压泵拆卸步骤",
            iteration=1,
            planner_feedback={"missing_requirements": ["warning"]},
            planner_route="fact",
            query_features={},
        )

        baseline = _build_baseline_plan(state)

        if "chunks" not in baseline["selected_channels"]:
            return False, f"期望selected_channels包含'chunks', 实际为{baseline['selected_channels']}"
        if baseline["rerank_profile"] != "safety_strict":
            return False, f"期望rerank_profile='safety_strict', 实际为{baseline['rerank_profile']}"
        if baseline["selected_channels"][0] != "chunks":
            return False, f"期望chunks在第一位, 实际为{baseline['selected_channels']}"

        return True, f"通过：baseline正确调整，chunks优先，rerank=safety_strict"
    except Exception as e:
        return False, f"异常：{str(e)}"


def scenario_15_applicability_conflict_baseline_rerank(monkeypatch=None):
    """场景15：applicability_conflict时baseline调整rerank"""
    try:
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

        if baseline["rerank_profile"] != "safety_strict":
            return False, f"期望rerank_profile='safety_strict', 实际为{baseline['rerank_profile']}"
        if "chunks" not in baseline["selected_channels"]:
            return False, f"期望selected_channels包含'chunks', 实际为{baseline['selected_channels']}"
        if baseline["selected_channels"][0] != "chunks":
            return False, f"期望chunks在第一位, 实际为{baseline['selected_channels']}"

        return True, "通过：applicability_conflict时baseline正确设置rerank=safety_strict"
    except Exception as e:
        return False, f"异常：{str(e)}"


class MockMonkeypatch:
    """简易monkeypatch用于直接运行脚本时使用"""
    def __init__(self):
        self._patches = []

    def setattr(self, target, name, value):
        original = getattr(target, name, None)
        self._patches.append((target, name, original))
        setattr(target, name, value)

    def undo(self):
        for target, name, original in reversed(self._patches):
            if original is not None:
                setattr(target, name, original)
        self._patches.clear()


def run_all_scenarios():
    scenarios = [
        ("场景1：步骤+警告查询（缺warning检测）", scenario_1_steps_plus_warning_missing_warning),
        ("场景2：历史指代消解（history_as_evidence=False）", scenario_2_history_resolution_history_as_evidence_false),
        ("场景3：指定机型查询（适用性识别）", scenario_3_specified_aircraft_model),
        ("场景4：跨机型冲突检测", scenario_4_cross_aircraft_conflict),
        ("场景5：参数查询（parameter requirement）", scenario_5_parameter_query),
        ("场景6：工具查询（tooling requirement）", scenario_6_tooling_query),
        ("场景7：覆盖完整（不缺证据）", scenario_7_full_coverage_no_missing),
        ("场景8：ATA章节识别", scenario_8_ata_chapter_recognition),
        ("场景9：correct_answer改写补充warning关键词", scenario_9_rule_based_rewrite_add_warning_keywords),
        ("场景10：correct_answer改写补充机型", scenario_10_rule_based_rewrite_add_aircraft_model),
        ("场景11：generate_answer prompt历史边界声明", scenario_11_generate_answer_history_boundary),
        ("场景12：generate_answer prompt适用范围要求", scenario_12_generate_answer_applicability_requirement),
        ("场景13：指定机型时Milvus带filter", scenario_13_milvus_filter_with_aircraft_model),
        ("场景14：missing_requirements时baseline调整通道", scenario_14_missing_requirements_baseline_channels),
        ("场景15：applicability_conflict时baseline调整rerank", scenario_15_applicability_conflict_baseline_rerank),
    ]

    passed = 0
    failed = 0
    results = []

    mp = MockMonkeypatch()

    for name, scenario_fn in scenarios:
        try:
            import inspect
            sig = inspect.signature(scenario_fn)
            if "monkeypatch" in sig.parameters:
                ok, msg = scenario_fn(monkeypatch=mp)
            else:
                ok, msg = scenario_fn()

            if ok:
                passed += 1
                results.append(("PASS", name, msg))
            else:
                failed += 1
                results.append(("FAIL", name, msg))
        except Exception as e:
            failed += 1
            results.append(("ERROR", name, f"执行异常：{str(e)}"))

    mp.undo()

    total = passed + failed
    pass_rate = (passed / total * 100) if total > 0 else 0

    print("=" * 70)
    print("Mini Golden Set 验证结果")
    print("=" * 70)
    for status, name, msg in results:
        status_marker = "PASS" if status == "PASS" else "FAIL"
        print(f"[{status_marker}] {name}")
        print(f"       {msg}")
        print()

    print("=" * 70)
    print(f"Mini Golden Set验证完成：{passed}/{total}通过，通过率{pass_rate:.1f}%")

    if pass_rate >= 90:
        print("通过率达标（>=90%，即14/15以上）")
    else:
        print(f"通过率未达标（需要>=90%，当前{pass_rate:.1f}%）")
        import sys
        sys.exit(1)


if __name__ == "__main__":
    run_all_scenarios()
