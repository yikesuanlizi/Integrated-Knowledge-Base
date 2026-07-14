"""查询扩展、改写、分析。"""
from __future__ import annotations

import re
from typing import List, Optional

from app.compiler.llm_utils import call_llm_json
from app.compiler.prompts import get_prompt
from app.core.log import logger
from app.ingest.entities import extract_entities, extract_keywords
from app.models.schemas import QueryIntent


# ============================================================
# 航空维修领域同义词表
# ============================================================

AVIATION_SYNONYMS = {
    "拆卸": ["拆除", "取下", "卸下", "拆下", "脱开"],
    "安装": ["装配", "装上", "安装就位", "固定"],
    "更换": ["替换", "换新", "置换"],
    "检查": ["检测", "查验", "检验", "查看"],
    "清洁": ["清洗", "清理", "擦拭"],
    "润滑": ["加油", "上油", "涂润滑脂"],
    "调试": ["调整", "校准", "调校"],
    "测试": ["测验", "验证", "试验"],
    "故障": ["问题", "异常", "失效", "损坏", "缺陷"],
    "步骤": ["流程", "方法", "过程", "程序"],
    "工具": ["设备", "仪器", "用具"],
    "部件": ["组件", "零件", "装配件"],
    "系统": ["装置", "总成"],
    "燃油": ["燃料", "煤油", "航油"],
    "液压": ["油压"],
    "力矩": ["扭矩", "转矩"],
    "紧固件": ["螺栓", "螺钉", "螺帽", "紧固件"],
    "卡子": ["夹子", "卡箍", "固定夹"],
    "开口销": ["开口销", "保险销"],
    "O型圈": ["O 形圈", "密封圈"],
    "航材": ["器材", "物料"],
    "工卡": ["工作单", "工单", "工作单卡"],
    "AMM": ["Aircraft Maintenance Manual", "飞机维修手册"],
    "FIM": ["Fault Isolation Manual", "故障隔离手册"],
    "IPC": ["Illustrated Parts Catalog", "图解零件目录"],
    "TSM": ["Trouble Shooting Manual", "排故手册"],
    "SB": ["Service Bulletin", "服务通告"],
    "AD": ["Airworthiness Directive", "适航指令"],
}


class QueryFeatures:
    def __init__(self, query: str):
        self.query = query
        self.keywords: List[str] = []
        self.entities: dict = {}
        self.query_variants: List[str] = []
        self.synonyms: List[str] = []
        self.intent: Optional[QueryIntent] = None
        self.complexity: dict = {}

    def extract(self) -> "QueryFeatures":
        from app.retrieval.intent import classify_intent

        self.intent = classify_intent(self.query)
        self.keywords = self.intent.keywords
        self.entities = self.intent.entities
        self.generate_variants()
        self.expand_synonyms()
        self.complexity = analyze_query_complexity(self.query)
        return self

    def generate_variants(self) -> List[str]:
        variants: List[str] = [self.query]

        # 去除问号
        variants.append(self.query.replace("？", "").replace("?", "").strip())

        # 常见疑问词替换
        replacements = [
            ("如何", ""), ("怎样", ""), ("怎么", ""),
            ("什么是", ""), ("是什么", ""), ("是什么", ""),
            ("如何进行", ""), ("步骤是", ""),
        ]
        for old, new in replacements:
            if old in self.query:
                variants.append(self.query.replace(old, new).strip())

        # 实体变体
        for pn in self.entities.get("part_numbers", []):
            variants.append(f"{pn}")
        for comp in self.entities.get("components", []):
            variants.append(f"{comp}")

        # 去重、清洗
        seen = set()
        unique: List[str] = []
        for v in variants:
            v = v.strip()
            if v and v not in seen:
                seen.add(v)
                unique.append(v)
        self.query_variants = unique
        return self.query_variants

    def expand_synonyms(self) -> List[str]:
        synonyms: List[str] = []
        for word, syns in AVIATION_SYNONYMS.items():
            if word in self.query:
                synonyms.extend(syns)
        self.synonyms = list(set(synonyms))
        return self.synonyms

    def build_fusion_queries(self) -> List[str]:
        queries: List[str] = list(self.query_variants)

        # 加入原 query
        queries.append(self.query)

        # 加同义词变体
        for word, syns in AVIATION_SYNONYMS.items():
            if word in self.query:
                for syn in syns[:2]:
                    variant = self.query.replace(word, syn)
                    queries.append(variant)

        # 去重
        seen = set()
        unique: List[str] = []
        for q in queries:
            q = q.strip()
            if q and q not in seen:
                seen.add(q)
                unique.append(q)
        return unique


def build_query_vector(query: str) -> List[float]:
    """同步接口：使用同步 embedding 客户端。"""
    from app.clients.llm_client import embedding_client
    return embedding_client.embed_text_sync(query)


async def build_query_vector_async(query: str) -> List[float]:
    from app.clients.llm_client import embedding_client
    return await embedding_client.aembed_text(query)


def extract_query_entities(query: str) -> dict:
    result = extract_entities(query)
    return {
        "part_numbers": [e.value for e in result.entities if e.entity_type.value == "part_number"],
        "components": [e.value for e in result.entities if e.entity_type.value == "component"],
        "actions": [e.value for e in result.entities if e.entity_type.value == "action"],
        "warnings": result.warnings,
    }


def generate_query_variants(query: str) -> List[str]:
    features = QueryFeatures(query)
    return features.extract().query_variants


def expand_query_with_synonyms(query: str) -> List[str]:
    features = QueryFeatures(query)
    features.extract()
    expanded: List[str] = [query]
    for word, syns in AVIATION_SYNONYMS.items():
        if word in query:
            for syn in syns[:2]:
                expanded.append(query.replace(word, syn))
    return list(set(expanded))


def build_rag_fusion_queries(query: str, top_k: int = 5) -> List[str]:
    features = QueryFeatures(query)
    features.extract()
    return features.build_fusion_queries()[:top_k]


def analyze_query_complexity(query: str) -> dict:
    complexity = 0
    factors: List[str] = []

    if len(query) > 30:
        complexity += 1
        factors.append("long_query")

    if re.search(r"[和与及]", query):
        complexity += 1
        factors.append("multiple_intents")

    part_pattern = re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]{3,}(?![A-Za-z0-9])")
    parts = list(part_pattern.finditer(query))
    if len(parts) > 1:
        complexity += 1
        factors.append("multiple_parts")

    if re.search(r"步骤|流程|方法", query):
        complexity += 1
        factors.append("procedural")

    if re.search(r"故障|问题|异常", query):
        complexity += 1
        factors.append("troubleshooting")

    if re.search(r"警告|注意|危险", query):
        complexity += 2
        factors.append("safety_critical")

    return {
        "complexity": complexity,
        "level": "simple" if complexity <= 1 else "medium" if complexity <= 3 else "complex",
        "factors": factors,
    }


def extract_numerical_constraints(query: str) -> List[dict]:
    constraints: List[dict] = []

    range_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(?:~|-|至|到)\s*(\d+(?:\.\d+)?)")
    for match in range_pattern.finditer(query):
        try:
            constraints.append({
                "type": "range",
                "min": float(match.group(1)),
                "max": float(match.group(2)),
            })
        except ValueError:
            continue

    cmp_pattern = re.compile(r"(?:大于|小于|超过|不少于|不超过|<=|>=|大于等于|小于等于)\s*(\d+(?:\.\d+)?)")
    for match in cmp_pattern.finditer(query):
        try:
            constraints.append({
                "type": "comparison",
                "value": float(match.group(1)),
                "operator": match.group(0),
            })
        except ValueError:
            continue

    return constraints


# ============================================================
# LLM 增强的查询改写
# ============================================================

async def llm_rewrite_query(query: str) -> dict:
    """使用 LLM 改写查询，提取实体、变体、同义词。"""
    try:
        system, user_tpl = get_prompt("query_rewrite")
        user_prompt = user_tpl.substitute(question=query)
        result = await call_llm_json(system, user_prompt, temperature=0.2, max_tokens=800)
        if isinstance(result, dict):
            return {
                "core_entities": result.get("core_entities", []),
                "variants": result.get("variants", []),
                "synonyms": result.get("synonyms", {}),
            }
    except Exception as e:
        logger.warning(f"LLM query rewrite failed: {e}")
    return {"core_entities": [], "variants": [], "synonyms": {}}


async def hybrid_rewrite_query(query: str) -> List[str]:
    """LLM 改写 + 本地扩展融合。"""
    features = QueryFeatures(query)
    features.extract()
    local_variants = features.build_fusion_queries()

    llm_result = await llm_rewrite_query(query)
    llm_variants = llm_result.get("variants", [])

    all_variants = list(set(local_variants + llm_variants + [query]))
    return [v.strip() for v in all_variants if v and v.strip()][:8]
