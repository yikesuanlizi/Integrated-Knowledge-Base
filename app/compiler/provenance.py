"""Source provenance helpers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProvenanceRef:
    source_file: str
    chunk_id: str = ""
    line_start: int | None = None
    line_end: int | None = None

    def as_source_ref(self) -> str:
        line_part = ""
        if self.line_start is not None:
            line_part = f":{self.line_start}"
            if self.line_end is not None and self.line_end != self.line_start:
                line_part += f"-{self.line_end}"
        chunk_part = f"#{self.chunk_id}" if self.chunk_id else ""
        return f"{self.source_file}{line_part}{chunk_part}"


def attach_provenance(item: dict, provenance: ProvenanceRef) -> dict:
    return {**item, "source_ref": provenance.as_source_ref(), "provenance": provenance.__dict__}
