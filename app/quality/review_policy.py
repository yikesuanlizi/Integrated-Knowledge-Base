"""审核策略引擎：自动决定哪些 Wiki 卡片需要人工 review。

规则体系：
- error 级别：直接触发 hold（必须人工审核）
- warning 级别：在 hold_on_warning=True 时触发 hold
- info 级别：仅记录，不自动 hold

新增规则说明：
- contradiction：同一 subject 出现不同 value → 数据矛盾
- citation_sparse：所有 facts 来自同一 source_chunk_id → 引用单一
- content_dilution：content字数/facts数量 < 50 → 内容稀释
- title_mismatch：title关键词在content不出现 → 标题与内容不匹配
- no_related：task/procedure/comparison 类型但无 related_cards → 缺少关联
- no_chunk_link：linked_chunks 为空 → 未链接源文本块
- no_specs：component/part/entity 类型但 facts 无数字 → 缺少规格信息
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Literal, Optional

from app.compiler.wiki_cards import WikiCard, WikiCardStatus
from app.core.log import logger


# ============================================================
# 安全关键词库：涉及安全提示的内容需要人工审核
# ============================================================
SAFETY_KEYWORDS = [
    "警告", "危险", "注意", "WARNING", "DANGER", "CAUTION",
    "安全", "严禁", "不得", "禁止", "必须", "应立即",
]


# ============================================================
# 策略规则注册项
# ============================================================
PolicyRule = Dict[
    Literal["name", "check", "reason", "severity", "category"],
    object,
]


def _has_placeholder(content: str) -> bool:
    """检查内容是否包含占位符或未完成标记。"""
    return bool(re.search(r"\{\{|\[\[TODO\]\]|\bTBD\b|\bXXX\b|\bTODO\b", content))


def _has_numeric_fact(facts: List[object]) -> bool:
    """检查 facts 中是否存在含数字的 value。"""
    for f in facts:
        if hasattr(f, "value") and re.search(r"\d", str(f.value)):
            return True
    return False


# ============================================================
# 规则注册表：所有审核规则的统一入口
# ============================================================
def _build_rules() -> List[PolicyRule]:
    """构建完整规则注册表。每条规则包含 name/check/reason/severity/category。"""
    return [
        # ---- 原有规则（迁移到注册表） ----

        {
            "name": "low_confidence",
            "severity": "error",
            "category": "quality",
            "reason": "置信度过低",
            "check": lambda card: card.confidence < 0.6,
        },
        {
            "name": "content_too_short",
            "severity": "error",
            "category": "quality",
            "reason": "内容过短",
            "check": lambda card: len(card.content.strip()) < 100,
        },
        {
            "name": "safety_keyword",
            "severity": "error",
            "category": "safety",
            "reason": "包含安全相关内容",
            "check": lambda card: any(kw in card.content for kw in SAFETY_KEYWORDS),
        },
        {
            "name": "no_citation",
            "severity": "error",
            "category": "quality",
            "reason": "无引用 / 无 fact",
            "check": lambda card: not card.facts and not card.references,
        },
        {
            "name": "has_placeholder",
            "severity": "error",
            "category": "quality",
            "reason": "包含占位符 / 未完成标记",
            "check": lambda card: _has_placeholder(card.content),
        },
        {
            "name": "title_missing",
            "severity": "error",
            "category": "quality",
            "reason": "标题缺失或过短",
            "check": lambda card: not card.title or len(card.title.strip()) < 2,
        },

        # ---- 新增规则 ----

        # 数据矛盾检测：同一 subject 出现不同 value
        {
            "name": "contradiction",
            "severity": "error",
            "category": "consistency",
            "reason": "同一 subject 存在矛盾的事实（不同 value）",
            "check": lambda card: _check_contradiction(card.facts),
        },
        # 引用单一：所有 facts 来自同一个 source_chunk_id
        {
            "name": "citation_sparse",
            "severity": "warning",
            "category": "quality",
            "reason": "所有 facts 均来自同一 source_chunk_id，引用单一",
            "check": lambda card: _check_citation_sparse(card.facts),
        },
        # 内容稀释：content字数/facts数量 < 50
        {
            "name": "content_dilution",
            "severity": "warning",
            "category": "quality",
            "reason": "content字数相对于 fact 数量过少（稀释）",
            "check": lambda card: _check_content_dilution(card),
        },
        # 标题与内容不匹配：title关键词在content不出现
        {
            "name": "title_mismatch",
            "severity": "warning",
            "category": "consistency",
            "reason": "标题关键词未在内容中出现",
            "check": lambda card: _check_title_mismatch(card),
        },
        # 缺少关联卡片：procedure/faq/fault 类型但 related_cards 为空
        {
            "name": "no_related",
            "severity": "info",
            "category": "linkage",
            "reason": "procedure/faq/fault 类型但无 related_cards",
            "check": lambda card: _check_no_related(card),
        },
        # 未链接源文本块
        {
            "name": "no_chunk_link",
            "severity": "info",
            "category": "linkage",
            "reason": "linked_chunks 为空，未链接源文本块",
            "check": lambda card: not card.linked_chunks,
        },
        # 缺少规格信息：concept/definition 类型但 facts 无数字
        {
            "name": "no_specs",
            "severity": "warning",
            "category": "completeness",
            "reason": "concept/definition 类型但 facts 中无数字（缺少规格）",
            "check": lambda card: _check_no_specs(card),
        },
    ]


# ============================================================
# 规则辅助检测函数
# ============================================================

def _check_contradiction(facts: List[object]) -> bool:
    """检测同一 subject 不同 predicate 出现不同 value 的矛盾。"""
    subject_predicates: Dict[str, Dict[str, str]] = {}
    for f in facts:
        if not hasattr(f, "subject") or not hasattr(f, "predicate") or not hasattr(f, "value"):
            continue
        key = (f.subject, f.predicate)
        if key in subject_predicates and subject_predicates[key] != f.value:
            return True
        subject_predicates[key] = f.value
    return False


def _check_citation_sparse(facts: List[object]) -> bool:
    """检测所有 facts 是否均来自同一个 source_chunk_id。"""
    if not facts:
        return False
    chunk_ids = [getattr(f, "source_chunk_id", None) for f in facts]
    non_empty = [c for c in chunk_ids if c is not None]
    return len(set(non_empty)) == 1 and len(non_empty) > 1


def _check_content_dilution(card: WikiCard) -> bool:
    """content字数/facts数量 < 50 则认为内容稀释。"""
    if not card.facts:
        return False
    content_len = len(card.content.strip())
    ratio = content_len / len(card.facts)
    return ratio < 50


def _check_title_mismatch(card: WikiCard) -> bool:
    """title关键词在content不出现。提取title前两个实词与content匹配。"""
    if not card.title or not card.content:
        return False
    title_words = re.findall(r"[\w\u4e00-\u9fff]{2,}", card.title)
    if not title_words:
        return False
    # 取前两个有意义的词
    keywords = title_words[:2]
    content_lower = card.content.lower()
    for kw in keywords:
        if kw.lower() in content_lower:
            return False
    return True


def _check_no_related(card: WikiCard) -> bool:
    """procedure/faq/fault 类型但 related_cards 为空。"""
    card_type = str(card.card_type.value if hasattr(card.card_type, "value") else card.card_type)
    if card_type in ("procedure", "faq", "fault"):
        return not card.related_cards
    return False


def _check_no_specs(card: WikiCard) -> bool:
    """concept/definition 类型但 facts 无数字。"""
    card_type = str(card.card_type.value if hasattr(card.card_type, "value") else card.card_type)
    if card_type in ("concept", "definition"):
        return not _has_numeric_fact(card.facts)
    return False


# ============================================================
# 策略配置 dataclass：硬编码阈值统一抽成可配置字段
# ============================================================
@dataclass
class PolicyConfig:
    confidence_threshold: float = 0.6
    min_content_length: int = 100
    min_facts_per_content_ratio: float = 50.0
    hold_on_warning: bool = False
    rules: List[PolicyRule] = field(default_factory=_build_rules)


# ============================================================
# 策略执行结果 dataclass
# ============================================================
@dataclass
class PolicyResult:
    should_hold: bool
    reasons: List[str]
    suggested_status: WikiCardStatus
    issues: List[Dict] = field(default_factory=list)


# ============================================================
# 统计结果 dataclass
# ============================================================
@dataclass
class PolicyStats:
    total: int = 0
    held: int = 0
    approved: int = 0
    approved_with_warnings: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    by_card_type: Dict[str, int] = field(default_factory=dict)


# ============================================================
# 核心审核函数
# ============================================================

def apply_review_policy(
    card: WikiCard,
    config: Optional[PolicyConfig] = None,
) -> PolicyResult:
    """对单张卡片应用审核策略。

    遍历规则注册表，按配置决定是否 hold：
    - 存在 error 级别 issue → hold
    - 存在 warning 级别 issue 且 hold_on_warning=True → hold
    """
    if config is None:
        config = PolicyConfig()

    issues: List[Dict] = []
    reasons: List[str] = []

    for rule in config.rules:
        rule_name: str = rule["name"]
        rule_severity: str = rule["severity"]
        rule_reason: str = rule["reason"]
        rule_check: Callable[[WikiCard], bool] = rule["check"]  # type: ignore

        try:
            triggered = rule_check(card)
        except Exception as e:
            logger.warning(f"规则 {rule_name} 执行异常: {e}")
            continue

        if triggered:
            issue = {
                "name": rule_name,
                "severity": rule_severity,
                "category": rule["category"],
                "reason": rule_reason,
            }
            issues.append(issue)
            reasons.append(f"[{rule_severity.upper()}] {rule_reason} ({rule_name})")

    # 判断是否 hold
    has_error = any(i["severity"] == "error" for i in issues)
    has_warning = any(i["severity"] == "warning" for i in issues)
    should_hold = has_error or (config.hold_on_warning and has_warning)

    suggested_status = WikiCardStatus.REVIEW if should_hold else WikiCardStatus.APPROVED

    return PolicyResult(
        should_hold=should_hold,
        reasons=reasons,
        suggested_status=suggested_status,
        issues=issues,
    )


# ============================================================
# 批量审核函数
# ============================================================

def apply_batch(
    cards: List[WikiCard],
    config: Optional[PolicyConfig] = None,
) -> tuple[List[tuple[WikiCard, PolicyResult]], PolicyStats]:
    """对批量卡片应用审核策略。

    返回:
        - results: List[tuple[WikiCard, PolicyResult]]
        - stats: PolicyStats 统计摘要
    """
    if config is None:
        config = PolicyConfig()

    results: List[tuple[WikiCard, PolicyResult]] = []
    stats = PolicyStats()

    for card in cards:
        result = apply_review_policy(card, config)
        results.append((card, result))

    # 汇总统计
    stats.total = len(results)
    stats.held = sum(1 for _, r in results if r.should_hold)
    stats.approved = sum(
        1 for _, r in results
        if not r.should_hold and not any(i["severity"] == "warning" for i in r.issues)
    )
    stats.approved_with_warnings = sum(
        1 for _, r in results
        if not r.should_hold and any(i["severity"] == "warning" for i in r.issues)
    )

    # 按 category 统计
    for _, r in results:
        for issue in r.issues:
            cat = issue["category"]
            stats.by_category[cat] = stats.by_category.get(cat, 0) + 1

    # 按 card_type 统计 held 数量
    for card, r in results:
        if r.should_hold:
            ct = card.card_type or "unknown"
            stats.by_card_type[ct] = stats.by_card_type.get(ct, 0) + 1

    logger.info(
        f"Policy: {stats.held}/{stats.total} cards held for review, "
        f"{stats.approved} approved, {stats.approved_with_warnings} approved with warnings"
    )

    return results, stats
