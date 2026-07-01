"""评测：健康度评估。"""
from __future__ import annotations


def evaluate_health(chunk_count: int, card_count: int, es_count: int) -> dict:
    """根据 chunk/card/ES 数量计算健康分。

    评分规则：
    - 质量分（权重 0.4）：chunk/card/es 三项各自独立判断是否有数据（>=1 为有），
      三项都有满分，有一项缺失扣 20%，最低 0 分。
    - 总量分（权重 0.6）：总数据量达到 1000 满分，最低 0 分。
    - 综合分 = 质量分 * 0.4 + 总量分 * 0.6
    """
    # 质量维度
    quality_items = [
        chunk_count >= 1,
        card_count >= 1,
        es_count >= 1,
    ]
    quality_score = sum(quality_items) / 3.0  # 0.0 ~ 1.0

    # 总量维度
    total = chunk_count + card_count + es_count
    volume_score = min(total / 1000.0, 1.0)

    # 综合分
    score = quality_score * 0.4 + volume_score * 0.6

    return {
        "score": round(score, 4),
        "chunk_count": chunk_count,
        "card_count": card_count,
        "es_count": es_count,
        "total": total,
        "level": "excellent" if score >= 0.8 else "good" if score >= 0.5 else "fair" if score >= 0.2 else "poor",
        "quality_score": round(quality_score, 4),
        "volume_score": round(volume_score, 4),
        "details": {
            "chunks_per_card_ratio": round(chunk_count / max(card_count, 1), 2),
            "es_chunks_present": es_count > 0,
            "chunk_present": chunk_count > 0,
            "card_present": card_count > 0,
        },
    }
