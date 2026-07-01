"""LLM 调用辅助：JSON 解析容错、批处理。"""
from __future__ import annotations

import json
import re
from string import Template
from typing import Any, Dict, List, Optional

from app.clients.llm_client import llm_client
from app.core.log import logger


async def call_llm_json(
    system: str,
    user: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    max_retries: int = 2,
) -> Any:
    """调用 LLM 并解析 JSON 输出。失败时尝试修复。"""
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            content = await llm_client.generate(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return _parse_json(content)
        except Exception as e:
            last_error = e
            logger.warning(f"LLM call attempt {attempt + 1} failed: {e}")

    raise RuntimeError(f"LLM call failed after {max_retries + 1} attempts: {last_error}")


def _parse_json(content: str) -> Any:
    """从 LLM 输出中提取并解析 JSON。"""
    if not content:
        raise ValueError("Empty LLM output")

    content = content.strip()

    # 1) 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 2) 提取 ```json ... ``` 块
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", content)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3) 提取第一个 [...] 或 {...}
    bracket_match = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", content)
    if bracket_match:
        candidate = bracket_match.group(1)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # 4) 尝试修复常见问题（尾随逗号、单引号）
            fixed = _try_fix_json(candidate)
            if fixed is not None:
                return fixed

    raise ValueError(f"Failed to parse JSON from LLM output: {content[:200]}")


def _try_fix_json(text: str) -> Any:
    """尝试修复常见的 JSON 错误。"""
    # 去除尾随逗号
    fixed = re.sub(r",\s*([}\]])", r"\1", text)
    # 单引号替换为双引号（仅在 key/value 中）
    fixed = re.sub(r"'([^']*)'\s*:", r'"\1":', fixed)
    fixed = re.sub(r":\s*'([^']*)'", r': "\1"', fixed)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        return None


async def batch_call_llm_json(
    system: str,
    user_template: Template,
    items: List[Dict[str, Any]],
    *,
    concurrency: int = 5,
    **kwargs: Any,
) -> List[Any]:
    """批量并发调用 LLM JSON 接口。"""
    import asyncio

    semaphore = asyncio.Semaphore(concurrency)

    async def _call_one(item: Dict[str, Any]) -> Any:
        async with semaphore:
            try:
                user_prompt = user_template.substitute(item)
                return await call_llm_json(system, user_prompt, **kwargs)
            except Exception as e:
                logger.error(f"Batch LLM call failed for item: {e}")
                return None

    results = await asyncio.gather(*[_call_one(item) for item in items])
    return results
