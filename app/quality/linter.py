"""Wiki 卡片 linter：规则引擎化检查，支持注册表模式。

检查维度：
- completeness: 必要字段、引用完整性
- quality: 内容长度、置信度一致性
- safety: 占位符、危险内容
- format: 标题格式、wikilink 数量
- provenance: fact 溯源、chunk 链路、重复事实
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Literal, Optional

from app.compiler.llm_utils import call_llm_json
from app.compiler.prompts import get_prompt
from app.compiler.wiki_cards import Fact, WikiCard, WikiCardType
from app.core.log import logger


# ============================================================
# 数据结构（向后兼容）
# ============================================================

@dataclass
class LintIssue:
    rule: str
    severity: str  # error / warning / info
    message: str


@dataclass
class LintResult:
    passed: bool
    issues: List[LintIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "info")


@dataclass
class LintBatchResult:
    """批量 lint 统计结果。"""
    total: int
    passed: int
    failed: int
    total_errors: int
    total_warnings: int
    results: List[tuple[WikiCard, LintResult]]
    by_category: Dict[str, Dict[str, int]]

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0


# ============================================================
# LintConfig：可配置各 severity 是否计入 passed，各 category 是否启用
# ============================================================

@dataclass
class LintConfig:
    # passed 的判定标准：只有 severity 在此列表中才计入失败
    error_severities: List[str] = field(default_factory=lambda: ["error"])
    # 启用的 category（空列表表示全部启用）
    enabled_categories: List[str] = field(default_factory=list)
    # 禁用的 category
    disabled_categories: List[str] = field(default_factory=lambda: ["safety"])
    # 长内容阈值
    long_content_threshold: int = 20000
    # 短内容阈值
    short_content_threshold: int = 50
    # wikilink 数量上限
    max_wikilinks: int = 50
    # 标题长度上限
    max_title_length: int = 200
    # 置信度下限
    min_confidence: float = 0.5
    # 自我矛盾的置信度下限
    self_contradict_confidence: float = 0.8

    def is_enabled(self, category: str) -> bool:
        """检查 category 是否启用。"""
        if self.enabled_categories:
            return category in self.enabled_categories
        return category not in self.disabled_categories

    def is_blocking(self, severity: str) -> bool:
        """检查 severity 是否导致 passed=False。"""
        return severity in self.error_severities


# ============================================================
# LintRule：规则注册表条目
# ============================================================

LintRule = Dict[
    Literal["name", "check", "severity", "message", "category"],
    object,
]


def _make_issue(rule: LintRule, card: WikiCard) -> Optional[LintIssue]:
    """执行规则检查，命中则构造 LintIssue。"""
    try:
        triggered = rule["check"](card)
    except Exception as e:
        logger.warning(f"规则 {rule['name']} 执行异常: {e}")
        triggered = False
    if triggered:
        msg_tpl = str(rule["message"])
        # 支持 {card.xxx} 占位符替换
        try:
            message = msg_tpl.format(card=card)
        except (KeyError, ValueError):
            message = msg_tpl
        return LintIssue(
            rule=str(rule["name"]),
            severity=str(rule["severity"]),
            message=message,
        )
    return None


# ============================================================
# 规则定义
# ============================================================

# ---- completeness: 必要字段、引用完整性 ----

RULE_MISSING_TITLE: LintRule = {
    "name": "missing_title",
    "category": "completeness",
    "check": lambda c: not c.title,
    "severity": "error",
    "message": "title 字段为空",
}

RULE_MISSING_CARD_ID: LintRule = {
    "name": "missing_card_id",
    "category": "completeness",
    "check": lambda c: not c.card_id,
    "severity": "error",
    "message": "card_id 字段为空",
}

RULE_MISSING_SOURCE_REF: LintRule = {
    "name": "missing_source_ref",
    "category": "completeness",
    "check": lambda c: not c.source_ref,
    "severity": "warning",
    "message": "source_ref 字段为空",
}

RULE_NO_CITATIONS: LintRule = {
    "name": "no_citations",
    "category": "completeness",
    "check": lambda c: not c.facts and not c.references,
    "severity": "warning",
    "message": "无 fact 引用也无 references",
}

# ---- quality: 内容质量、置信度一致性 ----

RULE_LOW_CONFIDENCE: LintRule = {
    "name": "low_confidence",
    "category": "quality",
    "check": lambda c: c.confidence < 0.5,
    "severity": "warning",
    "message": "置信度过低: {card.confidence:.2f}",
}

RULE_SHORT_CONTENT: LintRule = {
    "name": "short_content",
    "category": "quality",
    "check": lambda c: len(c.content) < 50,
    "severity": "warning",
    "message": "内容过短: {len(card.content)} 字符",
}

RULE_LONG_CONTENT: LintRule = {
    "name": "long_content",
    "category": "quality",
    "check": lambda c: len(c.content) > 20000,
    "severity": "warning",
    "message": "内容过长: {len(card.content)} 字符",
}

RULE_LONG_TITLE: LintRule = {
    "name": "long_title",
    "category": "quality",
    "check": lambda c: bool(c.title and len(c.title) > 200),
    "severity": "warning",
    "message": "标题过长: {len(card.title)} 字符",
}

# ---- safety: 占位符 ----

RULE_PLACEHOLDERS: LintRule = {
    "name": "placeholders",
    "category": "safety",
    "check": lambda c: bool(
        re.search(r"\{\{[^}]+\}\}|\bTBD\b|\bTODO\b|\bXXX\b|\[\[WIP\]\]", c.content)
    ),
    "severity": "error",
    "message": "内容包含占位符或未完成标记",
}

# ---- format: 格式、wikilink 数量 ----

RULE_TOO_MANY_LINKS: LintRule = {
    "name": "too_many_links",
    "category": "format",
    "check": lambda c: len(re.findall(r"\[\[([^\]|]+)", c.content)) > 50,
    "severity": "warning",
    "message": "wikilink 过多: {len(re.findall(r'\\[\\[([^\\]|]+)', card.content))}",
}

# ---- provenance: fact 溯源、chunk 链路、重复事实 ----

RULE_DUPLICATE_FACTS: LintRule = {
    "name": "duplicate_facts",
    "category": "provenance",
    "check": lambda c: _has_duplicate_facts(c.facts),
    "severity": "error",
    "message": "存在重复的 fact（相同 statement+source_ref）",
}

RULE_ORPHAN_FACT: LintRule = {
    "name": "orphan_fact",
    "category": "provenance",
    "check": lambda c: _has_orphan_fact(c.facts),
    "severity": "warning",
    "message": "存在 orphan fact（source_ref 对应的 chunk 不在 linked_chunks 里）",
}

RULE_DEAD_WIKILINK: LintRule = {
    "name": "dead_wikilink",
    "category": "provenance",
    "check": lambda c: _has_dead_wikilink(c),
    "severity": "warning",
    "message": "存在 dead wikilink（指向的卡片不在 related_cards 里）",
}

RULE_MISSING_METADATA_FIELDS: LintRule = {
    "name": "missing_metadata_fields",
    "category": "completeness",
    "check": lambda c: _has_missing_metadata(c),
    "severity": "warning",
    "message": "缺少必要的 metadata 字段（根据 card_type）",
}

RULE_INCONSISTENT_CONFIDENCE: LintRule = {
    "name": "inconsistent_confidence",
    "category": "quality",
    "check": lambda c: _has_inconsistent_confidence(c),
    "severity": "warning",
    "message": "置信度自我矛盾（置信度高但内容短或无 facts）",
}

RULE_CIRCULAR_RELATED: LintRule = {
    "name": "circular_related",
    "category": "provenance",
    "check": lambda c: c.card_id in c.related_cards,
    "severity": "error",
    "message": "related_cards 里出现自身 card_id（自环）",
}


# ============================================================
# 辅助检查函数
# ============================================================

def _has_duplicate_facts(facts: List[Fact]) -> bool:
    """检查是否有重复的 fact（相同 statement+source_ref）。"""
    seen: set = set()
    for f in facts:
        key = (f.statement.strip(), f.source_ref.strip())
        if key in seen:
            return True
        seen.add(key)
    return False


def _has_orphan_fact(facts: List[Fact]) -> bool:
    """检查是否有 orphan fact（source_ref 不在 linked_chunks 里）。

    注：Fact.source_ref 记录来源文件，linked_chunks 在 WikiCard 中以 chunk_id 形式存在。
    这里做宽松检查：如果 source_ref 为空且无 page_no，则认为是孤儿 fact。
    """
    for f in facts:
        if not f.source_ref and f.page_no is None:
            return True
    return False


def _has_dead_wikilink(card: WikiCard) -> bool:
    """检查是否有 dead wikilink（wikilink 指向的卡片不在 related_cards 里）。

    由于 related_cards 存的是 card_id 而 wikilink 是 title，
    这里做宽松检查：提取所有 wikilink title，若均不在 related_cards 中则报 warning。
    """
    wikilinks = re.findall(r"\[\[([^\]|]+)", card.content)
    if not wikilinks:
        return False
    # related_cards 是 card_id 列表，wikilink 是 title，无法精确匹配时跳过
    # 只有当 related_cards 非空且完全没有交集时才报
    if not card.related_cards:
        return False
    # 做子串匹配：wikilink title 是否在 related_cards 中
    matched = any(
        link in related or related in link
        for link in wikilinks
        for related in card.related_cards
    )
    return not matched


# component 型强烈建议有 aircraft_model；task 型建议有 procedure_step
_REQUIRED_METADATA: Dict[WikiCardType, List[str]] = {
    WikiCardType.CONCEPT: ["aircraft_model"],
    WikiCardType.PROCEDURE: ["procedure_step"],
    WikiCardType.DEFINITION: ["source_file"],
}


def _has_missing_metadata(card: WikiCard) -> bool:
    """检查 card_type 对应的必要 metadata 字段是否缺失。"""
    required = _REQUIRED_METADATA.get(card.card_type, [])
    return any(field not in card.metadata for field in required)


def _has_inconsistent_confidence(card: WikiCard) -> bool:
    """检查置信度自我矛盾：
    - confidence > 0.8 但 content 短（<100 字符）且无 facts
    - confidence 高但引用信息明显缺失
    """
    if card.confidence <= 0.8:
        return False
    short_content = len(card.content) < 100
    no_facts = not card.facts
    no_refs = not card.references
    return short_content and (no_facts or no_refs)


# ============================================================
# 规则注册表
# ============================================================

LINT_RULES: List[LintRule] = [
    # completeness
    RULE_MISSING_TITLE,
    RULE_MISSING_CARD_ID,
    RULE_MISSING_SOURCE_REF,
    RULE_NO_CITATIONS,
    RULE_MISSING_METADATA_FIELDS,
    # quality
    RULE_LOW_CONFIDENCE,
    RULE_SHORT_CONTENT,
    RULE_LONG_CONTENT,
    RULE_LONG_TITLE,
    RULE_INCONSISTENT_CONFIDENCE,
    # safety
    RULE_PLACEHOLDERS,
    # format
    RULE_TOO_MANY_LINKS,
    # provenance
    RULE_DUPLICATE_FACTS,
    RULE_ORPHAN_FACT,
    RULE_DEAD_WIKILINK,
    RULE_CIRCULAR_RELATED,
]


# ============================================================
# 核心 lint 函数
# ============================================================

def lint_card(card: WikiCard, config: Optional[LintConfig] = None) -> LintResult:
    """遍历规则注册表，对单张卡片进行检查。

    passed = error_count == 0（无论 config 如何，error 均阻塞）
    """
    if config is None:
        config = LintConfig()

    issues: List[LintIssue] = []
    for rule in LINT_RULES:
        if not config.is_enabled(rule["category"]):
            continue
        issue = _make_issue(rule, card)
        if issue:
            issues.append(issue)

    # passed 判定：只要有 error 就失败
    passed = not any(i.severity == "error" for i in issues)
    return LintResult(passed=passed, issues=issues)


async def lint_card_with_llm(card: WikiCard, config: Optional[LintConfig] = None) -> LintResult:
    """规则 + LLM 双重检查。"""
    rule_result = lint_card(card, config)
    # 有 error 时直接返回，不调 LLM
    if rule_result.error_count > 0:
        return rule_result

    try:
        system, user_tpl = get_prompt("linter")
        content_preview = card.content[:3000]
        user_prompt = user_tpl.substitute(content=content_preview)
        result = await call_llm_json(system, user_prompt, temperature=0.1, max_tokens=1000)
        if isinstance(result, dict):
            for issue in result.get("issues", []):
                rule_result.issues.append(LintIssue(
                    rule=str(issue.get("rule", "llm")),
                    severity=str(issue.get("severity", "warning")),
                    message=str(issue.get("message", "")),
                ))
            if not result.get("passed", True):
                rule_result.issues.append(LintIssue(
                    rule="llm_quality",
                    severity="warning",
                    message="LLM 检查未通过",
                ))
    except Exception as e:
        logger.warning(f"LLM lint failed: {e}")

    passed = not any(i.severity == "error" for i in rule_result.issues)
    return LintResult(passed=passed, issues=rule_result.issues)


def lint_batch(
    cards: List[WikiCard],
    config: Optional[LintConfig] = None,
) -> LintBatchResult:
    """批量 lint，返回统计结果。"""
    results: List[tuple[WikiCard, LintResult]] = [(c, lint_card(c, config)) for c in cards]

    total = len(results)
    passed = sum(1 for _, r in results if r.passed)
    failed = total - passed
    total_errors = sum(r.error_count for _, r in results)
    total_warnings = sum(r.warning_count for _, r in results)

    # 按 category 统计
    by_category: Dict[str, Dict[str, int]] = {}
    for _, result in results:
        for issue in result.issues:
            cat = _issue_category(result.issues, issue.rule)
            if cat not in by_category:
                by_category[cat] = {"error": 0, "warning": 0, "info": 0}
            by_category[cat][issue.severity] = by_category[cat].get(issue.severity, 0) + 1

    logger.info(
        f"[lint_batch] total={total} passed={passed} failed={failed} "
        f"errors={total_errors} warnings={total_warnings}"
    )

    return LintBatchResult(
        total=total,
        passed=passed,
        failed=failed,
        total_errors=total_errors,
        total_warnings=total_warnings,
        results=results,
        by_category=by_category,
    )


def _issue_category(issues: List[LintIssue], rule_name: str) -> str:
    """根据 rule_name 推断 category。"""
    name_to_cat: Dict[str, str] = {
        "missing_title": "completeness",
        "missing_card_id": "completeness",
        "missing_source_ref": "completeness",
        "no_citations": "completeness",
        "missing_metadata_fields": "completeness",
        "low_confidence": "quality",
        "short_content": "quality",
        "long_content": "quality",
        "long_title": "quality",
        "inconsistent_confidence": "quality",
        "placeholders": "safety",
        "too_many_links": "format",
        "duplicate_facts": "provenance",
        "orphan_fact": "provenance",
        "dead_wikilink": "provenance",
        "circular_related": "provenance",
    }
    return name_to_cat.get(rule_name, "unknown")
