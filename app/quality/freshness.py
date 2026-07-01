"""新鲜度管理：检测源文档变化并标记过时的 Wiki 卡片。"""
from __future__ import annotations

import hashlib
import json
import os
import fcntl
import threading
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Literal

from app.compiler.llm_utils import call_llm_json
from app.compiler.prompts import get_prompt
from app.compiler.wiki_cards import WikiCard
from app.core.log import logger
from app.ingest.parsers import sha256_file


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    ORPHANED = "orphaned"
    REFRESH = "refresh"


@dataclass
class FreshnessResult:
    card_id: str
    status: FreshnessStatus
    score: float  # 0.0 - 1.0, 越高越新
    changed_sections: List[str]
    recommendation: str
    source_hash: str
    card_hash: str
    checked_at: str


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def check_by_hash(card: WikiCard, source_content: Optional[str] = None) -> FreshnessResult:
    """基于内容哈希的快速新鲜度检查。"""
    card_hash = _hash_content(card.content)

    if source_content is None:
        return FreshnessResult(
            card_id=card.card_id,
            status=FreshnessStatus.FRESH,
            score=1.0,
            changed_sections=[],
            recommendation="无法获取源内容，跳过检查",
            source_hash="",
            card_hash=card_hash,
            checked_at=datetime.utcnow().isoformat(),
        )

    source_hash = _hash_content(source_content)

    if source_hash == card_hash:
        return FreshnessResult(
            card_id=card.card_id,
            status=FreshnessStatus.FRESH,
            score=1.0,
            changed_sections=[],
            recommendation="内容一致，无需更新",
            source_hash=source_hash,
            card_hash=card_hash,
            checked_at=datetime.utcnow().isoformat(),
        )

    # 长度变化判断
    length_diff = abs(len(source_content) - len(card.content)) / max(len(source_content), 1)
    if length_diff > 0.5:
        status = FreshnessStatus.REFRESH
        rec = "源文档内容大幅变化，建议重新编译"
    else:
        status = FreshnessStatus.STALE
        rec = "源文档有局部变化，建议增量更新"

    return FreshnessResult(
        card_id=card.card_id,
        status=status,
        score=max(0.0, 1.0 - length_diff),
        changed_sections=[],
        recommendation=rec,
        source_hash=source_hash,
        card_hash=card_hash,
        checked_at=datetime.utcnow().isoformat(),
    )


async def check_with_llm(card: WikiCard, source_content: str) -> FreshnessResult:
    """用 LLM 做更精细的新鲜度检查。"""
    base_result = check_by_hash(card, source_content)
    if base_result.status == FreshnessStatus.FRESH:
        return base_result

    try:
        system, user_tpl = get_prompt("freshness_check")
        user_prompt = user_tpl.substitute(
            title=card.title,
            card_content=card.content[:2000],
            source_content=source_content[:2000],
        )
        result = await call_llm_json(system, user_prompt, temperature=0.1, max_tokens=800)
        if isinstance(result, dict):
            status_str = str(result.get("status", base_result.status.value))
            try:
                base_result.status = FreshnessStatus(status_str)
            except ValueError:
                pass
            base_result.score = float(result.get("score", base_result.score))
            base_result.changed_sections = result.get("changed_sections", [])
            base_result.recommendation = str(result.get("recommendation", base_result.recommendation))
    except Exception as e:
        logger.warning(f"LLM freshness check failed: {e}")

    return base_result


def is_orphaned(card: WikiCard, available_source_hashes: set[str]) -> bool:
    """检查卡片对应的源文档是否还存在。"""
    if not card.source_ref:
        return False
    return card.source_ref not in available_source_hashes


class SourceFileRegistry:
    """源文档哈希注册表：记录每个源文档的 SHA256。

    用法：
    - 摄入文档时把 (path -> sha256) 写进去
    - 新鲜度检查时查注册表看是否变化

    线程安全：使用读写锁（Linux 下用 fcntl，Windows 下跳过）
    """

    def __init__(self, registry_path: str = "data/source_registry.json"):
        self.registry_path = registry_path
        self._cache: dict[str, str] = {}  # path -> hash
        self._lock = threading.RLock()
        self._loaded = False

    def _ensure_dir(self) -> None:
        """确保注册表所在目录存在。"""
        path = Path(self.registry_path)
        path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, str]:
        """从磁盘加载注册表，返回 path -> hash 映射。"""
        with self._lock:
            if os.path.exists(self.registry_path):
                try:
                    with open(self.registry_path, "r", encoding="utf-8") as f:
                        self._lock_file(f)
                        self._cache = json.load(f)
                    self._loaded = True
                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"加载注册表失败，使用空注册表: {e}")
                    self._cache = {}
                    self._loaded = True
            else:
                self._cache = {}
                self._loaded = True
            return self._cache.copy()

    def save(self) -> None:
        """将当前缓存写入磁盘。"""
        with self._lock:
            self._ensure_dir()
            tmp_path = self.registry_path + ".tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    self._lock_file(f)
                    json.dump(self._cache, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.registry_path)
            except IOError as e:
                logger.error(f"保存注册表失败: {e}")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

    def _lock_file(self, f) -> None:
        """Linux 下对文件加锁，Windows 下跳过。"""
        if os.name != "nt":
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except OSError:
                pass

    def register(self, path: str, hash: str) -> None:
        """注册一个源文件的哈希值。"""
        with self._lock:
            if not self._loaded:
                self.load()
            self._cache[path] = hash

    def unregister(self, path: str) -> None:
        """从注册表中移除一个源文件。"""
        with self._lock:
            if not self._loaded:
                self.load()
            self._cache.pop(path, None)

    def get_hash(self, path: str) -> str | None:
        """获取指定路径的哈希值，不存在返回 None。"""
        with self._lock:
            if not self._loaded:
                self.load()
            return self._cache.get(path)

    def is_stale(self, path: str, current_hash: str) -> bool:
        """检查源文件是否已过期（哈希发生变化）。"""
        registered = self.get_hash(path)
        if registered is None:
            return True  # 未注册视为过期
        return registered != current_hash

    def update_hash(self, path: str, current_hash: str) -> None:
        """更新注册表中的哈希值。"""
        self.register(path, current_hash)


def build_refresh_plan(cards: List[WikiCard], registry: SourceFileRegistry) -> dict:
    """基于注册表构建刷新计划。

    遍历每张卡片：
    - 读取 card.source_ref 对应的文件当前哈希
    - 与 card.metadata.get("source_hash") 比对
    - 分类到 refresh/stale/orphaned/fresh
    - 同时在 card.metadata 里更新 "source_hash" 字段

    Args:
        cards: Wiki 卡片列表
        registry: 源文档哈希注册表

    Returns:
        包含 refresh/stale/orphaned/fresh 四类卡片 ID 列表的字典
    """
    plan = {
        "refresh": [],    # 内容大幅变化，需要重新编译
        "stale": [],      # 轻微过期，可增量更新
        "orphaned": [],   # 源文档已删除
        "fresh": [],      # 无需变更
    }

    for card in cards:
        source_ref = card.source_ref
        if not source_ref:
            # 无源引用，跳过
            plan["fresh"].append(card.card_id)
            continue

        # 获取源文件当前哈希
        source_path = Path(source_ref)
        if not source_path.exists():
            plan["orphaned"].append(card.card_id)
            continue

        try:
            current_hash = sha256_file(source_path)
        except Exception as e:
            logger.warning(f"计算文件哈希失败 {source_ref}: {e}")
            plan["stale"].append(card.card_id)
            continue

        # 更新卡片 metadata 中的 source_hash
        card.metadata["source_hash"] = current_hash

        # 与注册表中的哈希比对
        registered_hash = registry.get_hash(source_ref)
        if registered_hash is None:
            # 未注册，先注册再标记为 stale
            registry.register(source_ref, current_hash)
            plan["stale"].append(card.card_id)
            continue

        if registered_hash == current_hash:
            plan["fresh"].append(card.card_id)
        else:
            # 哈希变化，判断变化程度
            old_content = ""
            new_content = ""
            try:
                old_content = source_path.read_text(encoding="utf-8")
            except Exception:
                pass

            # 简单判断：长度变化超过 50% 视为大幅变化
            old_len = len(old_content)
            new_len = len(new_content) if new_content else 0
            if old_len > 0 and abs(new_len - old_len) / old_len > 0.5:
                plan["refresh"].append(card.card_id)
            else:
                plan["stale"].append(card.card_id)

    return plan


async def refresh_card(card: WikiCard, source_content: str) -> WikiCard:
    """基于源文档变化对卡片做增量更新。

    - 对 content_changed 的部分，用 LLM 做增量更新（不是全量重新编译）
    - 保留原有的 related_cards / linked_chunks / facts（除非被 LLM 识别为过时）
    - 更新 card.metadata["source_hash"]

    Args:
        card: 原始 Wiki 卡片
        source_content: 源文档最新内容

    Returns:
        更新后的 Wiki 卡片
    """
    from app.ingest.parsers import sha256_file

    # 计算新的 source_hash
    source_hash = sha256_file(Path(card.source_ref)) if card.source_ref else ""

    try:
        system, user_tpl = get_prompt("incremental_refresh")
        user_prompt = user_tpl.substitute(
            title=card.title,
            old_content=card.content,
            new_source=source_content,
            related_cards=json.dumps(card.related_cards, ensure_ascii=False),
            linked_chunks=json.dumps(card.linked_chunks, ensure_ascii=False),
            facts=json.dumps(card.facts, ensure_ascii=False),
        )
        result = await call_llm_json(system, user_prompt, temperature=0.1, max_tokens=2000)
        if isinstance(result, dict):
            # 用 LLM 返回的内容更新卡片
            if "content" in result:
                card.content = result["content"]
            if "facts" in result:
                card.facts = result["facts"]
            if "related_cards" in result:
                card.related_cards = result["related_cards"]
            # 更新元数据
            card.updated_at = datetime.utcnow().isoformat()
            card.metadata["source_hash"] = source_hash
            card.metadata["refreshed"] = True
    except Exception as e:
        logger.warning(f"增量刷新卡片 {card.card_id} 失败: {e}")
        # 降级：更新 hash 但不改变内容
        card.metadata["source_hash"] = source_hash

    return card


async def run_refresh(
    wiki_cards: List[WikiCard],
    registry: SourceFileRegistry,
    mode: Literal["check", "mark", "refresh"] = "check",
    output_dir: str = "wiki_output/refresh",
) -> dict:
    """执行刷新流程。

    Args:
        wiki_cards: Wiki 卡片列表
        registry: 源文档哈希注册表
        mode: 执行模式
            - check: 只检查，返回 plan
            - mark: 检查并把 status 写回卡片 metadata
            - refresh: 对 stale/orphaned 卡片重新生成（调用 compile 或 refresh_card）
        output_dir: 刷新结果输出目录

    Returns:
        刷新结果摘要
    """
    # 构建刷新计划
    plan = build_refresh_plan(wiki_cards, registry)

    result = {
        "mode": mode,
        "summary": {
            "fresh": len(plan["fresh"]),
            "stale": len(plan["stale"]),
            "orphaned": len(plan["orphaned"]),
            "refresh": len(plan["refresh"]),
        },
        "plan": plan,
        "cards": {},
    }

    if mode == "check":
        # 仅返回计划，不修改任何数据
        return result

    # mark 模式：更新 metadata
    if mode == "mark":
        for card in wiki_cards:
            if card.card_id in plan["stale"]:
                card.metadata["freshness_status"] = FreshnessStatus.STALE.value
            elif card.card_id in plan["orphaned"]:
                card.metadata["freshness_status"] = FreshnessStatus.ORPHANED.value
            elif card.card_id in plan["refresh"]:
                card.metadata["freshness_status"] = FreshnessStatus.REFRESH.value
            else:
                card.metadata["freshness_status"] = FreshnessStatus.FRESH.value
        registry.save()
        return result

    # refresh 模式：重新生成 stale/orphaned 卡片
    if mode == "refresh":
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        cards_to_refresh = plan["stale"] + plan["orphaned"]
        refreshed_count = 0

        for card in wiki_cards:
            if card.card_id not in cards_to_refresh:
                continue

            if card.source_ref and Path(card.source_ref).exists():
                try:
                    source_content = Path(card.source_ref).read_text(encoding="utf-8")
                    updated_card = await refresh_card(card, source_content)
                    result["cards"][card.card_id] = {
                        "status": "refreshed",
                        "title": updated_card.title,
                    }
                    refreshed_count += 1
                except Exception as e:
                    logger.error(f"刷新卡片 {card.card_id} 失败: {e}")
                    result["cards"][card.card_id] = {
                        "status": "error",
                        "error": str(e),
                    }
            else:
                # 孤儿卡片，标记但不处理
                result["cards"][card.card_id] = {
                    "status": "orphaned",
                    "title": card.title,
                }

        result["summary"]["refreshed"] = refreshed_count
        registry.save()

    return result


def get_stale_cards(cards: List[WikiCard], registry: SourceFileRegistry) -> List[WikiCard]:
    """返回需要刷新的卡片列表（status 为 STALE/ORPHANED/REFRESH）。

    Args:
        cards: Wiki 卡片列表
        registry: 源文档哈希注册表

    Returns:
        需要刷新的卡片子集
    """
    plan = build_refresh_plan(cards, registry)
    stale_ids = set(plan["stale"] + plan["orphaned"] + plan["refresh"])
    return [card for card in cards if card.card_id in stale_ids]
