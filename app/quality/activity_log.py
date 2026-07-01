"""活动日志：记录所有 ingest / compile / query / review 操作。"""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from app.core.log import logger


class ActionType(str, Enum):
    INGEST_FILE = "ingest.file"
    INGEST_PATH = "ingest.path"
    COMPILE = "compile"
    QUERY = "query"
    REVIEW_APPROVE = "review.approve"
    REVIEW_REJECT = "review.reject"
    REVIEW_CREATE = "review.create"
    LINT = "lint"
    EXPORT = "export"
    IMPORT = "import"


class ActivityLog:
    def __init__(self, log_dir: str = "wiki_output/activity_log"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_file = self.log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"

    def record(
        self,
        action: ActionType,
        actor: str = "system",
        payload: Optional[dict] = None,
        result: str = "ok",
        error: Optional[str] = None,
    ) -> dict:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action.value,
            "actor": actor,
            "payload": payload or {},
            "result": result,
            "error": error,
        }
        try:
            with self.current_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write activity log: {e}")
        return entry

    def query(
        self,
        action: Optional[ActionType] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """查询日志。"""
        results: list[dict] = []
        files = sorted(self.log_dir.glob("*.jsonl"), reverse=True)
        for log_file in files:
            if start_date and log_file.stem < start_date:
                break
            if end_date and log_file.stem > end_date:
                continue
            try:
                with log_file.open("r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if action and entry.get("action") != action.value:
                            continue
                        results.append(entry)
                        if len(results) >= limit:
                            return results
            except Exception as e:
                logger.warning(f"Read log {log_file} failed: {e}")
        return results


# 全局单例
activity_log = ActivityLog()
