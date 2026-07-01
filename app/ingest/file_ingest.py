"""File and URL ingestion helpers."""
from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

from app.services.ingest_service import IngestService


async def ingest_file_path(path: str | Path) -> dict:
    file_path = Path(path)
    return await IngestService().ingest_file(file_path.read_bytes(), file_path.name)


async def ingest_directory_path(path: str | Path, *, force: bool = False) -> dict:
    return await IngestService().ingest_directory(str(path), force=force)


async def ingest_url(url: str, *, filename: str | None = None, timeout: int = 30) -> dict:
    request = Request(url, headers={"User-Agent": "AgenticKnowledgeOS/0.1"})
    with urlopen(request, timeout=timeout) as response:
        data = response.read()
        inferred = filename or Path(response.url).name or "downloaded_source.txt"
    return await IngestService().ingest_file(data, inferred)
