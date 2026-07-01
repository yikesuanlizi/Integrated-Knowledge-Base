"""导出/导入 API。"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.compiler.wiki_cards import Fact, WikiCard, WikiCardStatus, WikiCardType
from app.core.log import logger
from app.export.graphml_export import export_cards_graphml
from app.export.json_export import export_cards_json, export_cards_jsonld
from app.export.llms_export import export_cards_llms_txt
from app.export.markdown_export import export_cards_markdown
from app.export.marp_export import export_cards_marp
from app.export.okf import export_okf, import_okf
from app.services.wiki_pg_service import list_pg_wiki_cards
from app.retrieval.es_repo import WikiCardESRepository
from app.retrieval.milvus_repo import WikiCardMilvusRepository

router = APIRouter(tags=["export"])

EXPORT_DIR = Path("wiki_output/exports")


class ExportRequest(BaseModel):
    card_type: Optional[str] = None
    limit: int = 1000
    format: str = "jsonl"  # jsonl / json / md / okf


class DirectExportRequest(BaseModel):
    card_ids: List[str] = []


@router.post("/run")
async def run_export(request: ExportRequest):
    """导出 Wiki 卡片。"""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    es_repo = WikiCardESRepository()
    try:
        await es_repo.create_index()
    except Exception:
        pass

    filters: dict = {}
    if request.card_type:
        filters["card_type"] = request.card_type
    try:
        results = await es_repo.search("", top_k=request.limit, filters=filters)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

    if request.format == "jsonl":
        out_path = EXPORT_DIR / f"wiki_export_{timestamp}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    elif request.format == "json":
        out_path = EXPORT_DIR / f"wiki_export_{timestamp}.json"
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    elif request.format == "md":
        out_path = EXPORT_DIR / f"wiki_export_{timestamp}.md"
        with out_path.open("w", encoding="utf-8") as f:
            for r in results:
                f.write(f"# {r.get('title', 'Untitled')}\n\n")
                f.write(f"{r.get('content', '')}\n\n---\n\n")
    elif request.format == "okf":
        out_path = EXPORT_DIR / f"wiki_export_{timestamp}.okf.json"
        out_path.write_text(export_okf(results), encoding="utf-8")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {request.format}")

    return {
        "path": str(out_path),
        "count": len(results),
        "format": request.format,
    }


def _row_to_wiki_card(row: dict) -> WikiCard:
    card_type = _enum_or_default(WikiCardType, str(row.get("card_type") or ""), WikiCardType.CONCEPT)
    status = _enum_or_default(WikiCardStatus, str(row.get("status") or ""), WikiCardStatus.APPROVED)
    facts = []
    for item in row.get("facts") or []:
        if isinstance(item, dict):
            facts.append(
                Fact(
                    statement=str(item.get("statement") or item.get("fact") or ""),
                    source_ref=str(item.get("source_ref") or ""),
                    confidence=float(item.get("confidence") or 1.0),
                    page_no=item.get("page_no"),
                )
            )
    return WikiCard(
        card_id=str(row.get("card_id") or ""),
        card_type=card_type,
        title=str(row.get("title") or ""),
        content=str(row.get("content") or row.get("text") or ""),
        source_ref=str(row.get("source_ref") or ""),
        confidence=float(row.get("confidence") or 0),
        status=status,
        facts=facts,
        references=[str(ref) for ref in (row.get("references") or [])],
        related_cards=[str(card_id) for card_id in (row.get("related_cards") or [])],
        linked_chunks=[str(chunk_id) for chunk_id in (row.get("linked_chunks") or [])],
        metadata=row.get("metadata") or {},
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
    )


def _enum_or_default(enum_cls, value: str, default):
    try:
        return enum_cls(value)
    except ValueError:
        return default


@router.get("/download")
async def download_export(path: str):
    """下载导出文件。"""
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    if not str(p.resolve()).startswith(str(EXPORT_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Path not allowed")
    return FileResponse(p, filename=p.name)


@router.post("/import")
async def import_export(file: UploadFile = File(...)):
    """导入 Wiki 卡片导出文件。"""
    contents = await file.read()
    text = contents.decode("utf-8")

    items: list[dict] = []
    if file.filename and file.filename.endswith(".jsonl"):
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    elif file.filename and (file.filename.endswith(".okf.json") or file.filename.endswith(".okf")):
        try:
            items = import_okf(text)
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Invalid OKF: {e}")
    elif file.filename and file.filename.endswith(".json"):
        try:
            raw = json.loads(text)
            if isinstance(raw, dict) and "cards" in raw:
                items = import_okf(text)
            else:
                items = raw
            if not isinstance(items, list):
                items = [items]
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file format (use .jsonl or .json)")

    # 写入 ES
    es_repo = WikiCardESRepository()
    try:
        await es_repo.create_index()
    except Exception:
        pass

    from app.compiler.wiki_cards import json_to_card
    imported = 0
    for item in items:
        if not isinstance(item, dict) or "card_id" not in item:
            continue
        try:
            await es_repo.index_card(item)
            imported += 1
        except Exception as e:
            logger.warning(f"Import card {item.get('card_id')} failed: {e}")

    return {
        "imported": imported,
        "total": len(items),
        "file": file.filename,
    }


@router.post("/{format}")
async def export_wiki_content(format: str, request: DirectExportRequest):
    """直接从 PostgreSQL 导出 Wiki 内容，返回文本内容。"""
    supported = {"markdown", "json", "jsonld", "graphml", "llms", "marp"}
    if format not in supported:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    rows, _ = await list_pg_wiki_cards(page=1, page_size=5000, status="approved")
    if request.card_ids:
        allowed = set(request.card_ids)
        rows = [row for row in rows if row.get("card_id") in allowed]
    cards = [_row_to_wiki_card(row) for row in rows]

    if format == "markdown":
        return export_cards_markdown(cards)
    if format == "json":
        return export_cards_json(cards)
    if format == "jsonld":
        return export_cards_jsonld(cards)
    if format == "graphml":
        return export_cards_graphml(cards)
    if format == "llms":
        return export_cards_llms_txt(cards)
    return export_cards_marp(cards)
