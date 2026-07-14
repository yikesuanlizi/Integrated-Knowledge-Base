"""检索结果重排：BM25 / 混合重排 / 去重合并 / 意图加权。"""
from __future__ import annotations

import math
from typing import Any, List, Optional

import requests

from app.conf.app_config import config
from app.core.log import logger


def _tokenize(text: str) -> List[str]:
    """简单按空白分词并小写。"""
    if not text:
        return []
    return [t for t in text.lower().split() if t]


def _nonempty(value) -> bool:
    """判断一个字段是不是"非空"（None / 空串 / 空列表都视为空）。"""
    if value is None:
        return False
    if isinstance(value, str):
        return len(value.strip()) > 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _external_rerank_client():
    """外部 rerank 客户端包装，方便测试时整体替换。"""

    class _Client:
        def post(self, url: str, headers: dict[str, str], json: dict[str, Any], timeout: int = 60):
            return requests.post(url, headers=headers, json=json, timeout=timeout)

    return _Client()


def _external_rerank_documents(query: str, documents: List[dict]) -> List[dict]:
    """调用 ai.gitee rerank；失败时抛出异常，交给本地排序回退。"""
    if not documents:
        return []
    api_key = config.rerank_api_key
    if not api_key:
        raise RuntimeError("Rerank API key is not configured")

    batch_size = 24
    all_ranked: list[dict] = []
    total = len(documents)
    any_batch_failed = False

    for batch_start in range(0, total, batch_size):
        batch_docs = documents[batch_start:batch_start + batch_size]
        payload = {
            "query": query,
            "documents": [
                doc.get("content", "") or doc.get("text", "") or doc.get("title", "") or doc.get("value", "")
                for doc in batch_docs
            ],
            "model": config.rerank_model_name,
            "instruction": config.rerank_instruction,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-Failover-Enabled": "true",
        }

        client = _external_rerank_client()
        try:
            response = client.post(f"{config.rerank_api_base}/rerank", headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            body = response.json()
        except Exception as e:
            logger.warning(f"External rerank batch failed (docs {batch_start}-{batch_start+len(batch_docs)}): {e}")
            any_batch_failed = True
            continue

        items = body.get("results") if isinstance(body, dict) else None
        if items is None and isinstance(body, dict):
            items = body.get("data")
        if items is None and isinstance(body, list):
            items = body
        if not isinstance(items, list):
            logger.warning(f"Unexpected rerank response shape: {type(body)}")
            any_batch_failed = True
            continue

        for position, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            local_index = item.get("index", item.get("document_index", item.get("documentIndex")))
            if local_index is None and position < len(batch_docs):
                local_index = position
            try:
                local_index = int(local_index)
            except (TypeError, ValueError):
                continue
            global_index = batch_start + local_index
            score = item.get("relevance_score", item.get("score", item.get("rerank_score", 0.0)))
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = float(len(items) - position)
            if 0 <= global_index < total:
                doc = documents[global_index].copy()
                doc["external_rerank_score"] = score
                all_ranked.append(doc)

    if not all_ranked:
        raise RuntimeError("Rerank API returned no valid results")
    all_ranked.sort(key=lambda d: d.get("external_rerank_score", 0.0), reverse=True)
    for i, doc in enumerate(all_ranked):
        doc["external_rerank_rank"] = i + 1
    if any_batch_failed:
        logger.warning(f"External rerank partial failure: {len(all_ranked)}/{total} docs ranked successfully")
    return all_ranked


def bm25_score(
    query: str,
    document: str,
    corpus: Optional[List[str]] = None,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """修正版 BM25：用 corpus 的平均长度做长度归一化；corpus 缺省时回退到 document 自身。

    IDF 采用 `log((N - n + 0.5) / (n + 0.5) + 1)` 的近似，无 corpus 时退化到与原实现一致。
    """
    query_terms = _tokenize(query)
    doc_terms = _tokenize(document)
    doc_length = len(doc_terms)

    if doc_length == 0 or not query_terms:
        return 0.0

    if corpus:
        corpus_lengths = [len(_tokenize(d)) for d in corpus if d]
        avg_doc_length = (sum(corpus_lengths) / len(corpus_lengths)) if corpus_lengths else float(doc_length)
        n_corpus = len(corpus_lengths)
    else:
        avg_doc_length = float(doc_length)
        n_corpus = 1

    term_freqs: dict[str, int] = {}
    for term in doc_terms:
        term_freqs[term] = term_freqs.get(term, 0) + 1

    if corpus:
        doc_term_sets: List[set[str]] = [set(_tokenize(d)) for d in corpus if d]
    else:
        doc_term_sets = [set(term_freqs.keys())]

    score = 0.0
    for term in query_terms:
        if term not in term_freqs:
            continue
        tf = term_freqs[term]
        n_with_term = sum(1 for s in doc_term_sets if term in s)
        idf = math.log((n_corpus - n_with_term + 0.5) / (n_with_term + 0.5) + 1.0)
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * doc_length / avg_doc_length)
        if denominator <= 0:
            continue
        score += idf * numerator / denominator

    return score


def keyword_overlap_score(query: str, document: str) -> float:
    """query 词项在 document 中的覆盖率 + 归一化词频，综合成 0–1 分数。"""
    query_terms = _tokenize(query)
    doc_terms = _tokenize(document)

    if not query_terms or not doc_terms:
        return 0.0

    term_freqs: dict[str, int] = {}
    for term in doc_terms:
        term_freqs[term] = term_freqs.get(term, 0) + 1

    covered = 0
    freq_sum = 0
    for term in query_terms:
        if term in term_freqs:
            covered += 1
            freq_sum += term_freqs[term]

    coverage = covered / len(query_terms)
    normalized_freq = min(freq_sum / len(doc_terms), 1.0)
    return 0.6 * coverage + 0.4 * normalized_freq


def source_quality_score(doc: dict) -> float:
    """按 source_type 评估文档元数据完整性，返回 0–1 分数。"""
    source_type = doc.get("source_type", "")
    content = doc.get("content", "") or doc.get("text", "") or doc.get("value", "")

    checks: int = 0
    passed: int = 0

    if source_type == "chunk":
        for key in ("page_numbers", "section_path", "source_file"):
            checks += 1
            if _nonempty(doc.get(key)):
                passed += 1
        checks += 1
        if _nonempty(content):
            passed += 1
    elif source_type == "wiki_card":
        for key in ("card_type", "source_ref"):
            checks += 1
            if _nonempty(doc.get(key)):
                passed += 1
        checks += 1
        if _nonempty(content):
            passed += 1
    elif source_type == "entity":
        checks += 1
        if _nonempty(doc.get("entity_type")):
            passed += 1
        checks += 1
        if _nonempty(content):
            passed += 1
    else:
        checks += 1
        if _nonempty(content):
            passed += 1

    return (passed / checks) if checks > 0 else 0.0


def _min_max_normalize(values: List[float]) -> List[float]:
    """对一组数值做 min-max 归一化到 [0, 1]；所有值相等时一律归 0.5。"""
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi - lo < 1e-9:
        return [0.5 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def bm25_rerank(query: str, documents: List[dict], top_k: int = 10) -> List[dict]:
    """用修正版 BM25 做纯关键词重排。"""
    corpus = [doc.get("content", "") or doc.get("text", "") for doc in documents]
    scored = []
    for doc in documents:
        content = doc.get("content", "") or doc.get("text", "")
        score = bm25_score(query, content, corpus=corpus)
        doc_with_score = doc.copy()
        doc_with_score["bm25_score"] = score
        scored.append(doc_with_score)

    scored.sort(key=lambda x: x["bm25_score"], reverse=True)
    return scored[:top_k]


def hybrid_rerank(
    query: str,
    documents: List[dict],
    semantic_weight: float = 0.5,
    bm25_weight: float = 0.5,
    keyword_weight: float = 0.15,
    quality_weight: float = 0.1,
    top_k: int = 10,
) -> List[dict]:
    """混合重排：优先外部 rerank，失败后回退 BM25 + 语义分 + 关键词覆盖 + 源质量。"""
    if not documents:
        return []

    external_ranked: list[dict] = []
    try:
        if len(documents) > 1:
            external_ranked = _external_rerank_documents(query, documents)
            logger.info(f"External rerank succeeded for {len(documents)} docs, got {len(external_ranked)} results")
    except Exception as exc:
        logger.warning(f"External rerank unavailable, falling back to local mix: {exc}")

    corpus = [doc.get("content", "") or doc.get("text", "") for doc in documents]

    raw_bm25: List[float] = []
    raw_semantic: List[float] = []
    raw_keyword: List[float] = []
    raw_quality: List[float] = []

    for doc in documents:
        content = doc.get("content", "") or doc.get("text", "")
        raw_bm25.append(bm25_score(query, content, corpus=corpus))
        raw_semantic.append(float(doc.get("score", 0.0)))
        raw_keyword.append(keyword_overlap_score(query, content))
        raw_quality.append(source_quality_score(doc))

    norm_bm25 = _min_max_normalize(raw_bm25)
    norm_semantic = _min_max_normalize(raw_semantic)
    norm_keyword = _min_max_normalize(raw_keyword)
    norm_quality = _min_max_normalize(raw_quality)
    external_scores = [0.0 for _ in documents]
    external_ranks = [0.0 for _ in documents]
    if external_ranked:
        order_map = {}
        score_map = {}
        for position, doc in enumerate(external_ranked):
            doc_id = _doc_primary_id(doc)
            order_map[doc_id] = position + 1
            score_map[doc_id] = float(doc.get("external_rerank_score", 0.0) or 0.0)
        for i, doc in enumerate(documents):
            doc_id = _doc_primary_id(doc)
            external_scores[i] = score_map.get(doc_id, 0.0)
            external_ranks[i] = float(order_map.get(doc_id, 0.0))
    norm_external = _min_max_normalize(external_scores) if any(external_scores) else [0.0 for _ in documents]

    weight_sum = semantic_weight + bm25_weight + keyword_weight + quality_weight
    if weight_sum <= 0:
        weight_sum = 1.0

    scored = []
    for i, doc in enumerate(documents):
        local_combined = (
            semantic_weight * norm_semantic[i]
            + bm25_weight * norm_bm25[i]
            + keyword_weight * norm_keyword[i]
            + quality_weight * norm_quality[i]
        ) / weight_sum
        combined = local_combined if not external_ranked else (0.65 * norm_external[i]) + (0.35 * local_combined)

        doc_with_score = doc.copy()
        doc_with_score["semantic_score"] = raw_semantic[i]
        doc_with_score["bm25_score"] = raw_bm25[i]
        doc_with_score["keyword_overlap"] = raw_keyword[i]
        doc_with_score["quality_score"] = raw_quality[i]
        doc_with_score["combined_score"] = combined
        if external_ranked:
            doc_with_score["external_rerank_score"] = external_scores[i]
            doc_with_score["external_rerank_rank"] = external_ranks[i]
        scored.append(doc_with_score)

    scored.sort(
        key=lambda x: (
            float(x.get("external_rerank_score", 0.0) or 0.0),
            float(x.get("combined_score", 0.0) or 0.0),
        ),
        reverse=True,
    )
    return scored[:top_k]


def reciprocal_rank_fusion(results: List[List[dict]], k: int = 60) -> List[dict]:
    """RRF：对多路排好序的列表做融合，返回带 fusion_score 的合并列表。"""
    fused_scores: dict[str, float] = {}

    for query_results in results:
        for position, doc in enumerate(query_results):
            doc_id = (
                doc.get("chunk_id")
                or doc.get("card_id")
                or doc.get("entity_id")
                or str(id(doc))
            )
            if doc_id not in fused_scores:
                fused_scores[doc_id] = 0.0
            fused_scores[doc_id] += 1 / (k + position)

    all_docs: dict[str, dict] = {}
    for query_results in results:
        for doc in query_results:
            doc_id = (
                doc.get("chunk_id")
                or doc.get("card_id")
                or doc.get("entity_id")
                or str(id(doc))
            )
            if doc_id not in all_docs:
                all_docs[doc_id] = doc

    scored = []
    for doc_id, score in fused_scores.items():
        doc = all_docs.get(doc_id, {})
        doc_with_score = doc.copy()
        doc_with_score["fusion_score"] = score
        scored.append(doc_with_score)

    scored.sort(key=lambda x: x["fusion_score"], reverse=True)
    return scored


def _doc_primary_id(doc: dict) -> str:
    """第一级去重 id：chunk_id / card_id / entity_id，否则 content[:100] 兜底。"""
    primary = (
        doc.get("chunk_id")
        or doc.get("card_id")
        or doc.get("entity_id")
    )
    if primary:
        return str(primary)
    content = doc.get("content", "") or doc.get("text", "") or doc.get("value", "")
    return "fallback:" + (content[:100] if content else str(id(doc)))


def _doc_secondary_key(doc: dict) -> str:
    """第二级去重 key：content[:60] + source_file 相同即视为重复。"""
    content = doc.get("content", "") or doc.get("text", "") or doc.get("value", "")
    source_file = doc.get("source_file", "") or doc.get("source_ref", "") or ""
    return content[:60] + "||" + str(source_file)


def _doc_score_for_merge(doc: dict) -> float:
    """合并阶段用的"分数"：优先取已有的 combined_score / score / fusion_score。"""
    for key in ("combined_score", "score", "fusion_score", "bm25_score"):
        value = doc.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


SOURCE_WEIGHTS: dict[str, float] = {
    "chunk": 1.0,
    "wiki_card": 1.2,
    "entity": 0.7,
}


def merge_and_deduplicate(documents: List[dict]) -> List[dict]:
    """两级去重合并：按 id 去重 + 按内容/来源二级去重，按 merge_score 保优。

    输出每个 doc 新增字段：source_weight / source_quality / merge_score。
    """
    if not documents:
        return []

    scored_docs: List[dict] = []
    for doc in documents:
        source_type = doc.get("source_type", "") or ""
        enriched = doc.copy()
        enriched["source_weight"] = float(SOURCE_WEIGHTS.get(source_type, 1.0))
        enriched["source_quality"] = float(source_quality_score(enriched))
        base_score = _doc_score_for_merge(enriched)
        enriched["merge_score"] = base_score * enriched["source_weight"]
        scored_docs.append(enriched)

    # 第一级：按主 id 去重，保留 merge_score 更高的
    primary_best: dict[str, dict] = {}
    for doc in scored_docs:
        pid = _doc_primary_id(doc)
        existing = primary_best.get(pid)
        if existing is None or doc.get("merge_score", 0.0) >= existing.get("merge_score", 0.0):
            primary_best[pid] = doc

    first_pass = list(primary_best.values())

    # 第二级：按 content[:60] + source_file 二级去重，保留 merge_score 更高的
    secondary_best: dict[str, dict] = {}
    for doc in first_pass:
        sk = _doc_secondary_key(doc)
        existing = secondary_best.get(sk)
        if existing is None or doc.get("merge_score", 0.0) >= existing.get("merge_score", 0.0):
            secondary_best[sk] = doc

    result = list(secondary_best.values())
    result.sort(key=lambda x: x.get("merge_score", 0.0), reverse=True)
    return result


def rerank_with_intent(
    query: str,
    documents: List[dict],
    intent_config: dict,
    top_k: int = 10,
) -> List[dict]:
    """按意图配置做混合重排：rerank_weight 越大越偏 BM25。"""
    if not intent_config:
        intent_config = {}
    rerank_weight = float(intent_config.get("rerank_weight", 0.5))

    if rerank_weight > 0:
        documents = hybrid_rerank(
            query,
            documents,
            semantic_weight=1 - rerank_weight,
            bm25_weight=rerank_weight,
            top_k=top_k * 2,
        )

    return documents[:top_k]
