"""Incremental compile helpers."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceDelta:
    source_id: str
    old_hash: str | None
    new_hash: str | None
    changed: bool


def source_hash(content: str | bytes) -> str:
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def changed_sources(previous: dict[str, str], current: dict[str, str]) -> list[SourceDelta]:
    source_ids = sorted(set(previous) | set(current))
    return [
        SourceDelta(source_id=sid, old_hash=previous.get(sid), new_hash=current.get(sid), changed=previous.get(sid) != current.get(sid))
        for sid in source_ids
    ]
