"""两阶段 LLM 编译 pipeline。

Phase 1: 从每个 chunk 提取概念列表
Phase 2: 对每个概念生成结构化页面
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.compiler.llm_utils import call_llm_json
from app.compiler.prompts import (
    CONCEPT_EXTRACTION_SYSTEM,
    CONCEPT_EXTRACTION_USER,
    PAGE_GENERATION_SYSTEM,
    PAGE_GENERATION_USER,
    get_prompt,
)
from app.compiler.wiki_cards import WikiCard, WikiCardStatus, WikiCardType
from app.core.log import logger
from app.models.schemas import Chunk


@dataclass
class CompiledConcept:
    name: str
    type: str
    summary: str
    source_text: str
    source_chunk_id: str
    source_doc_id: str


@dataclass
class CompiledPage:
    title: str
    summary: str
    sections: List[Dict[str, str]] = field(default_factory=list)
    key_facts: List[Dict[str, str]] = field(default_factory=list)
    safety_warnings: List[str] = field(default_factory=list)
    related_concepts: List[str] = field(default_factory=list)
    source_chunk_id: str = ""
    source_doc_id: str = ""


@dataclass
class PipelineResult:
    pages: List[CompiledPage] = field(default_factory=list)
    concepts: List[CompiledConcept] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _stable_card_id(title: str, card_type: str, build_id: str) -> str:
    raw = f"{build_id}::{card_type}::{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


async def phase1_extract_concepts(
    chunks: List[Chunk],
    *,
    max_concurrent: int = 5,
) -> List[CompiledConcept]:
    """阶段 1：批量从 chunks 中提取概念。"""
    import asyncio

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process(chunk: Chunk) -> List[CompiledConcept]:
        async with semaphore:
            try:
                system, user_tpl = get_prompt("concept_extraction")
                user_prompt = user_tpl.substitute(chunk_text=chunk.raw_content[:4000])
                result = await call_llm_json(system, user_prompt, temperature=0.1)
                if not isinstance(result, list):
                    return []
                concepts: List[CompiledConcept] = []
                for item in result:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("name", "")).strip()
                    if not name:
                        continue
                    concepts.append(CompiledConcept(
                        name=name[:200],
                        type=str(item.get("type", "component")).strip(),
                        summary=str(item.get("summary", "")).strip(),
                        source_text=str(item.get("source_text", ""))[:500],
                        source_chunk_id=chunk.chunk_id,
                        source_doc_id=chunk.doc_id,
                    ))
                return concepts
            except Exception as e:
                logger.warning(f"Phase1 extract failed for chunk {chunk.chunk_id}: {e}")
                return []

    results = await asyncio.gather(*[_process(c) for c in chunks])
    all_concepts: List[CompiledConcept] = []
    for batch in results:
        all_concepts.extend(batch)
    # 按 name 去重，保留最早出现的来源
    seen: Dict[str, CompiledConcept] = {}
    for c in all_concepts:
        if c.name not in seen:
            seen[c.name] = c
    return list(seen.values())


async def phase2_generate_pages(
    concepts: List[CompiledConcept],
    *,
    max_concurrent: int = 5,
) -> List[CompiledPage]:
    """阶段 2：为每个概念生成结构化页面。"""
    import asyncio

    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process(c: CompiledConcept) -> Optional[CompiledPage]:
        async with semaphore:
            try:
                system, user_tpl = get_prompt("page_generation")
                user_prompt = user_tpl.substitute(
                    concept_name=c.name,
                    concept_type=c.type,
                    concept_summary=c.summary,
                    source_text=c.source_text,
                )
                result = await call_llm_json(system, user_prompt, temperature=0.2, max_tokens=2000)
                if not isinstance(result, dict):
                    return None
                return CompiledPage(
                    title=str(result.get("title", c.name)).strip() or c.name,
                    summary=str(result.get("summary", "")).strip(),
                    sections=_normalize_sections(result.get("sections", [])),
                    key_facts=_normalize_facts(result.get("key_facts", [])),
                    safety_warnings=[str(w).strip() for w in result.get("safety_warnings", []) if w],
                    related_concepts=[str(r).strip() for r in result.get("related_concepts", []) if r],
                    source_chunk_id=c.source_chunk_id,
                    source_doc_id=c.source_doc_id,
                )
            except Exception as e:
                logger.warning(f"Phase2 generate failed for concept '{c.name}': {e}")
                return None

    results = await asyncio.gather(*[_process(c) for c in concepts])
    return [r for r in results if r is not None]


def _normalize_sections(raw: Any) -> List[Dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        heading = str(item.get("heading", "")).strip()
        body = str(item.get("body", "")).strip()
        if heading and body:
            out.append({"heading": heading[:120], "body": body[:4000]})
    return out


def _normalize_facts(raw: Any) -> List[Dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fact = str(item.get("fact", "")).strip()
        ref = str(item.get("source_ref", "")).strip()
        if fact:
            out.append({"fact": fact[:1000], "source_ref": ref})
    return out


def to_wiki_cards(
    pages: List[CompiledPage],
    *,
    build_id: str,
    source_ref: str = "",
) -> List[WikiCard]:
    """将 CompiledPage 转成 WikiCard。"""
    cards: List[WikiCard] = []
    for page in pages:
        card_type = _map_type_from_sections(page)
        body_md = _render_body(page)
        card_id = _stable_card_id(page.title, card_type, build_id)
        cards.append(WikiCard(
            card_id=card_id,
            card_type=card_type,
            title=page.title,
            content=body_md,
            source_ref=source_ref or page.source_chunk_id,
            confidence=0.85,
            status=WikiCardStatus.DRAFT,
            facts=[
                {"statement": f["fact"], "source_ref": f.get("source_ref", page.source_chunk_id), "confidence": 0.85, "page_no": None}
                for f in page.key_facts
            ],
            references=[],
            related_cards=page.related_concepts,
            linked_chunks=[page.source_chunk_id] if page.source_chunk_id else [],
            metadata={
                "summary": page.summary,
                "warnings": page.safety_warnings,
                "source_chunk_id": page.source_chunk_id,
                "source_doc_id": page.source_doc_id,
            },
            created_at=datetime.utcnow().isoformat(),
        ))
    return cards


def _map_type_from_sections(page: CompiledPage) -> WikiCardType:
    title_lower = page.title.lower()
    summary = page.summary.lower()
    body = "\n".join([page.summary] + [sec.get("body", "") for sec in page.sections]).lower()

    if any(kw in title_lower or kw in summary for kw in ["警告", "注意", "危险", "warning", "caution"]):
        return WikiCardType.FAULT
    if any(kw in title_lower for kw in ["步骤", "procedure", "操作", "拆卸", "安装"]):
        return WikiCardType.PROCEDURE
    if any(kw in title_lower or kw in body for kw in ["故障", "异常", "失效", "排故", "troubleshooting", "fault"]):
        return WikiCardType.FAULT
    if any(kw in title_lower for kw in ["区别", "对比", "比较", "difference", "comparison"]) or "常见问题" in title_lower:
        return WikiCardType.FAQ
    if any(kw in title_lower for kw in ["部件", "component", "组件", "零件", "装置"]):
        return WikiCardType.CONCEPT
    if any(kw in summary for kw in ["定义", "definition", "是指", "概念"]):
        return WikiCardType.DEFINITION
    return WikiCardType.CONCEPT


def _render_body(page: CompiledPage) -> str:
    """把 CompiledPage 渲染为 Markdown 正文。"""
    parts: List[str] = []
    if page.summary:
        parts.append(f"## 摘要\n\n{page.summary}\n")
    for sec in page.sections:
        parts.append(f"## {sec['heading']}\n\n{sec['body']}\n")
    if page.key_facts:
        parts.append("## 关键事实\n")
        for f in page.key_facts:
            ref = f.get("source_ref", "")
            ref_md = f" _(来源: {ref})_" if ref else ""
            parts.append(f"- {f['fact']}{ref_md}")
        parts.append("")
    if page.safety_warnings:
        parts.append("## ⚠️ 安全警告\n")
        for w in page.safety_warnings:
            parts.append(f"- {w}")
        parts.append("")
    if page.related_concepts:
        parts.append("## 相关概念\n")
        for r in page.related_concepts:
            parts.append(f"- [[{r}]]")
        parts.append("")
    return "\n".join(parts)


async def run_pipeline(
    chunks: List[Chunk],
    build_id: str,
    *,
    source_ref: str = "",
    max_concepts: int = 50,
) -> PipelineResult:
    """两阶段编译完整入口。"""
    if not chunks:
        return PipelineResult()

    # 阶段 1
    concepts = await phase1_extract_concepts(chunks)
    logger.info(f"Phase1 extracted {len(concepts)} concepts from {len(chunks)} chunks")

    if not concepts:
        return PipelineResult(warnings=["Phase 1 returned no concepts"])

    # 限制概念数量，避免 LLM 成本爆炸
    if len(concepts) > max_concepts:
        concepts = concepts[:max_concepts]

    # 阶段 2
    pages = await phase2_generate_pages(concepts)
    logger.info(f"Phase2 generated {len(pages)} pages from {len(concepts)} concepts")

    return PipelineResult(pages=pages, concepts=concepts)
