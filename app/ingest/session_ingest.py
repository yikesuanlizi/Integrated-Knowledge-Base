"""Conversation/session ingestion helpers."""
from __future__ import annotations

import json
from pathlib import Path

from app.services.ingest_service import IngestService


def session_to_markdown(session: dict) -> str:
    title = session.get("title") or session.get("name") or "Imported Session"
    messages = session.get("messages") or session.get("conversation") or []
    parts = [f"# {title}", ""]
    for message in messages:
        role = message.get("role") or message.get("author") or "unknown"
        content = message.get("content") or message.get("text") or ""
        if isinstance(content, list):
            content = "\n".join(str(item) for item in content)
        parts.append(f"## {role}")
        parts.append(str(content))
        parts.append("")
    return "\n".join(parts)


async def ingest_session_file(path: str | Path) -> dict:
    session_path = Path(path)
    raw = session_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, list):
        markdown = "\n\n---\n\n".join(session_to_markdown(item) for item in data if isinstance(item, dict))
    elif isinstance(data, dict):
        markdown = session_to_markdown(data)
    else:
        raise ValueError("Unsupported session JSON shape")
    filename = f"{session_path.stem}.md"
    return await IngestService().ingest_file(markdown.encode("utf-8"), filename)
