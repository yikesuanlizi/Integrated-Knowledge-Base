"""Services package.

Keep package imports lazy to avoid circular imports between graph/query/wiki
paths during module import time.
"""

from importlib import import_module

__all__ = [
    "IngestService",
    "CompileService",
    "QueryService",
    "EvalService",
    "ExportService",
    "chunk_review_service",
]


def __getattr__(name: str):
    if name == "IngestService":
        from app.services.ingest_service import IngestService

        return IngestService
    if name == "CompileService":
        from app.services.compile_service import CompileService

        return CompileService
    if name == "QueryService":
        from app.services.query_service import QueryService

        return QueryService
    if name == "EvalService":
        from app.services.eval_service import EvalService

        return EvalService
    if name == "ExportService":
        from app.services.export_service import ExportService

        return ExportService
    if name == "chunk_review_service":
        return import_module("app.services.chunk_review_service")
    raise AttributeError(name)
