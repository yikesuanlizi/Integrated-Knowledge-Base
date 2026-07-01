"""基于 LLM 的实体抽取：作为正则抽取的补充，处理复杂长文本。

正则模块（regex_extractor）做轻量快速匹配；
本模块用 LLM 做深层语义实体识别。
"""
from __future__ import annotations

import asyncio
from typing import List, Optional

from app.compiler.llm_utils import call_llm_json
from app.compiler.prompts import get_prompt
from app.core.log import logger
from app.ingest.entities import EntityExtractionResult, regex_extractor
from app.models.schemas import Entity, EntityType


_ENTITY_TYPE_MAP = {
    "part_number": EntityType.PART_NUMBER,
    "component": EntityType.COMPONENT,
    "tool": EntityType.COMPONENT,  # 暂归 COMPONENT
    "material": EntityType.MATERIAL_CODE,
    "procedure": EntityType.ACTION,
    "warning": EntityType.WARNING,
    "specification": EntityType.REQUIREMENT,
    "ata_chapter": EntityType.REVISION,  # 复用
    "aircraft_model": EntityType.COMPONENT,  # 复用
}


async def llm_extract_entities(text: str, *, max_chars: int = 4000) -> List[Entity]:
    """调用 LLM 抽取实体。"""
    text = text[:max_chars]
    if not text.strip():
        return []

    try:
        system, user_tpl = get_prompt("entity_extraction")
        user_prompt = user_tpl.substitute(text=text)
        result = await call_llm_json(system, user_prompt, temperature=0.1, max_tokens=2000)
        if not isinstance(result, list):
            return []
        entities: List[Entity] = []
        for item in result:
            if not isinstance(item, dict):
                continue
            raw_type = str(item.get("type", "")).lower().strip()
            value = str(item.get("value", "")).strip()
            if not value or not raw_type:
                continue
            mapped = _ENTITY_TYPE_MAP.get(raw_type, EntityType.COMPONENT)
            entities.append(Entity(
                entity_type=mapped,
                value=value[:200],
                start_pos=None,
                end_pos=None,
            ))
        return entities
    except Exception as e:
        logger.warning(f"LLM entity extraction failed: {e}")
        return []


async def extract_entities_hybrid(text: str) -> EntityExtractionResult:
    """混合抽取：正则 + LLM。LLM 失败时降级到纯正则。"""
    regex_result = regex_extractor(text)

    # LLM 抽取的实体（独立运行，不阻塞主流程）
    llm_entities: List[Entity] = []
    try:
        llm_entities = await asyncio.wait_for(llm_extract_entities(text), timeout=30.0)
    except asyncio.TimeoutError:
        logger.warning("LLM entity extraction timed out, using regex only")
    except Exception as e:
        logger.warning(f"LLM entity extraction failed: {e}")

    # 合并去重
    all_entities = regex_result.entities + llm_entities
    seen = set()
    unique: List[Entity] = []
    for e in all_entities:
        key = (e.entity_type.value, e.value.lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(e)

    return EntityExtractionResult(
        entities=unique,
        quantities=regex_result.quantities,
        relations=regex_result.relations,
    )


def extract_entities(text: str) -> EntityExtractionResult:
    """同步接口（仅正则），用于不需要 LLM 的快速场景。"""
    return regex_extractor(text)
