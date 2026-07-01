"""实体抽取：正则快速匹配 + 类型推断。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List

from app.models.schemas import Entity, EntityType


# ============================================================
# 正则模式库
# ============================================================

ENTITY_PATTERNS: list[tuple[EntityType, re.Pattern]] = [
    (EntityType.PART_NUMBER, re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]{2,}[-_][A-Z0-9]{2,}[-_]?[A-Z0-9]{0,6}(?![A-Za-z0-9])")),
    (EntityType.PART_NUMBER, re.compile(r"(?<![A-Za-z0-9])\d{2,4}[-_]\d{3,6}(?![A-Za-z0-9])")),
    (EntityType.PART_NUMBER, re.compile(r"\bP/?N\s*[:：]?\s*([A-Z0-9][A-Z0-9_\-]{4,20})\b", re.IGNORECASE)),
    (EntityType.MATERIAL_CODE, re.compile(r"(?<![A-Za-z0-9])[A-Z]{2,4}[-]?\d{3,6}(?![A-Za-z0-9])")),
    (EntityType.SERIAL_NUMBER, re.compile(r"(?<![A-Za-z0-9])S/?N[-_]?[A-Z0-9]{5,}(?![A-Za-z0-9])", re.IGNORECASE)),
    (EntityType.SERIAL_NUMBER, re.compile(r"(?<![A-Za-z0-9])ESN[-_]?\d{4,8}(?![A-Za-z0-9])", re.IGNORECASE)),
    (EntityType.WORK_ORDER, re.compile(r"(?<![A-Za-z0-9])WO[-_]?\d{4,8}(?![A-Za-z0-9])", re.IGNORECASE)),
    (EntityType.REVISION, re.compile(r"\b(?:REV[-_]?|R\.?E\.?V\.?)\s*([A-Z0-9](?:\.\d{1,2}){0,3})\b", re.IGNORECASE)),
    (EntityType.COMPONENT, re.compile(r"(?<![\u4e00-\u9fff])[\u4e00-\u9fff]{2,8}(?:部件|组件|零件|装置|设备|系统|泵|阀|管|线|开关|传感器|控制器|执行器)(?![\u4e00-\u9fff])")),
    (EntityType.COMPONENT, re.compile(r"(?<![A-Za-z])([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+(?:pump|valve|switch|sensor|controller|actuator|filter|regulator|module|unit)\b")),
]

# ATA 章节号
ATA_CHAPTER_REGEX = re.compile(r"\bATA\s*[-_]?\s*(\d{2})(?:[-/](\d{2}))?\b", re.IGNORECASE)
ATA_CHAPTER_CN_REGEX = re.compile(r"第\s*(\d{2})\s*章")
ATA_CHAPTER_FILENAME_REGEX = re.compile(r"^(\d{2})[-_]")

# 机型
AIRCRAFT_MODEL_REGEX = re.compile(
    r"\b(CH[-_ ]?\d+[A-Z]?|A3\d{2}|A220|A350|A380|B7\d{2}(?:NG|MAX)?|737NG|737MAX|ARJ21|C919|E19\d|E17\d)\b"
)

# 数值规格
QUANTITY_PATTERN = re.compile(r"(?<![0-9])(\d+(?:\.\d+)?)\s*(N·m|Nm|psi|kPa|MPa|bar|°C|℃|℉|mm|cm|m|inch|in|ft|kg|g|mg|lb|ml|L|s|sec|min|hr|hour|A|V|W|kW|Hz|rpm|%|percent)(?![A-Za-z0-9])", re.IGNORECASE)
QUANTITY_CN_PATTERN = re.compile(r"(?<![0-9])(\d+(?:\.\d+)?)\s*(个|件|套|组|只|台|根|条|块|片|颗|瓶|升|毫升|米|厘米|毫米|千克|克|吨|小时|分钟|秒|天|周|牛·米|帕|兆帕|千帕)(?![0-9])")

# 动作动词
ACTION_VERBS = ["拆卸", "安装", "更换", "检查", "清洁", "润滑", "调试", "测试", "启动", "停止", "关闭", "打开", "调节", "调整", "控制", "监控", "测量", "校准", "填充", "排放", "加注", "断开", "连接", "复位", "锁定", "解锁"]
ACTION_PATTERN = re.compile("|".join(ACTION_VERBS))

# 警告关键词
WARNING_KEYWORDS = ["警告", "注意", "危险", "安全", "严禁", "不得", "禁止", "小心", "避免", "WARNING", "CAUTION", "DANGER", "NOTE"]
WARNING_PATTERN = re.compile("|".join(WARNING_KEYWORDS), re.IGNORECASE)


@dataclass
class EntityExtractionResult:
    entities: list[Entity] = field(default_factory=list)
    quantities: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def regex_extractor(text: str) -> EntityExtractionResult:
    """纯正则实体抽取，无 LLM 调用。"""
    entities: list[Entity] = []
    quantities: list[dict] = []
    warnings: list[str] = []

    # 1) 通用模式
    for entity_type, pattern in ENTITY_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1) if match.groups() else match.group(0)
            value = value.strip().rstrip(".,;:")
            if len(value) < 2:
                continue
            entities.append(Entity(
                entity_type=entity_type,
                value=value,
                start_pos=match.start(),
                end_pos=match.end(),
            ))

    # 2) ATA 章节
    for m in ATA_CHAPTER_REGEX.finditer(text):
        ch = m.group(1)
        sub = m.group(2)
        value = f"ATA {ch}-{sub}" if sub else f"ATA {ch}"
        entities.append(Entity(
            entity_type=EntityType.REVISION,
            value=value,
            start_pos=m.start(),
            end_pos=m.end(),
        ))

    for m in ATA_CHAPTER_CN_REGEX.finditer(text):
        entities.append(Entity(
            entity_type=EntityType.REVISION,
            value=f"ATA {m.group(1)}",
            start_pos=m.start(),
            end_pos=m.end(),
        ))

    # 3) 机型
    for m in AIRCRAFT_MODEL_REGEX.finditer(text):
        entities.append(Entity(
            entity_type=EntityType.COMPONENT,
            value=m.group(1),
            start_pos=m.start(),
            end_pos=m.end(),
        ))

    # 4) 数值规格
    for m in QUANTITY_PATTERN.finditer(text):
        try:
            value_num = float(m.group(1))
        except ValueError:
            continue
        quantities.append({
            "value": value_num,
            "unit": m.group(2),
            "raw": m.group(0),
            "start_pos": m.start(),
            "end_pos": m.end(),
        })

    for m in QUANTITY_CN_PATTERN.finditer(text):
        try:
            value_num = float(m.group(1))
        except ValueError:
            continue
        quantities.append({
            "value": value_num,
            "unit": m.group(2),
            "raw": m.group(0),
            "start_pos": m.start(),
            "end_pos": m.end(),
        })

    # 5) 警告
    for m in WARNING_PATTERN.finditer(text):
        snippet = text[max(0, m.start() - 20):m.end() + 80].strip()
        warnings.append(snippet[:200])

    # 6) 动作（也作为 Entity）
    for verb in ACTION_VERBS:
        for m in re.finditer(re.escape(verb), text):
            entities.append(Entity(
                entity_type=EntityType.ACTION,
                value=verb,
                start_pos=m.start(),
                end_pos=m.end(),
            ))

    # 去重
    seen = set()
    unique: list[Entity] = []
    for e in entities:
        key = (e.entity_type.value, e.value.lower(), e.start_pos)
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)

    # 数量去重
    qty_seen = set()
    unique_qty = []
    for q in quantities:
        key = (q.get("raw"), q.get("start_pos"))
        if key in qty_seen:
            continue
        qty_seen.add(key)
        unique_qty.append(q)

    return EntityExtractionResult(
        entities=unique,
        quantities=unique_qty,
        relations=[],
        warnings=warnings,
    )


# 兼容旧 API
def extract_entities(text: str) -> EntityExtractionResult:
    return regex_extractor(text)


# 旧 API 兼容
def extract_actions(text: str) -> list[str]:
    return list(set(ACTION_PATTERN.findall(text)))


def extract_warnings(text: str) -> list[str]:
    return regex_extractor(text).warnings


def extract_requirements(text: str) -> list[str]:
    """从文本中提取要求/必须条款。"""
    pattern = re.compile(r"(?:必须|应|应当|需要|要求|不得|禁止|严禁)\s*([^\n。；;]{2,80})")
    return [m.group(1).strip() for m in pattern.finditer(text) if m.group(1).strip()]


def extract_numeric_ranges(text: str) -> list[dict]:
    """提取数值范围，形如 10-15 N·m。"""
    pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(?:~|-|至|到)\s*(\d+(?:\.\d+)?)\s*([A-Za-z\u4e00-\u9fff/·²³]+)")
    ranges = []
    for m in pattern.finditer(text):
        try:
            ranges.append({
                "min": float(m.group(1)),
                "max": float(m.group(2)),
                "unit": m.group(3),
                "raw": m.group(0),
            })
        except ValueError:
            continue
    return ranges


def extract_keywords(text: str, max_keywords: int = 20) -> list[str]:
    """提取关键词（基于实体 + 中文短语）。"""
    entities = regex_extractor(text)
    keywords: list[str] = []
    for e in entities.entities:
        if e.value and e.value not in keywords and len(e.value) >= 2:
            keywords.append(e.value)
    # 补中文 2-6 字短语
    for m in re.finditer(r"(?<![\u4e00-\u9fff])[\u4e00-\u9fff]{2,6}(?![\u4e00-\u9fff])", text):
        phrase = m.group(0)
        if phrase not in keywords:
            keywords.append(phrase)
    return keywords[:max_keywords]


def build_entity_index(entities: list[Entity]) -> dict:
    index: dict = {}
    for entity in entities:
        t = entity.entity_type.value
        index.setdefault(t, []).append(entity)
    return index
