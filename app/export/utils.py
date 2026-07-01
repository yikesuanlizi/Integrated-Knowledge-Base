"""导出工具函数。"""
from datetime import datetime, timezone
from typing import Any, List

from app.compiler.wiki_cards import WikiCard


def card_to_dict(card: WikiCard) -> dict:
    """将 WikiCard 转为字典，移除 None 值和空容器。"""
    d = {
        "card_id": card.card_id,
        "card_type": card.card_type.value if hasattr(card.card_type, "value") else card.card_type,
        "title": card.title,
        "content": card.content,
        "source_ref": card.source_ref,
        "confidence": card.confidence,
        "status": card.status.value if hasattr(card.status, "value") else card.status,
        "facts": [
            {
                "statement": f.statement,
                "source_ref": f.source_ref,
                "confidence": f.confidence,
                "page_no": f.page_no,
            }
            for f in card.facts
        ],
        "references": card.references,
        "related_cards": card.related_cards,
        "metadata": card.metadata,
        "created_at": card.created_at,
        "updated_at": card.updated_at,
    }

    def clean(v: Any) -> Any:
        if isinstance(v, list):
            return [clean(x) for x in v]
        if isinstance(v, dict):
            return {k: clean(val) for k, val in v.items() if val not in (None, [], {})}
        return v

    return clean(d)


def iso_now() -> str:
    """返回当前 UTC 时间 ISO 格式字符串。"""
    return datetime.now(timezone.utc).isoformat()
