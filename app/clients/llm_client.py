import json
import time
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.agent.trace import current_trace_id, record_llm_call
from app.conf.app_config import config
from app.core.log import logger


def _json_headers(api_key: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _gitee_headers(api_key: str) -> Dict[str, str]:
    headers = _json_headers(api_key)
    headers["X-Failover-Enabled"] = "true"
    return headers


class LLMClient:
    def __init__(self):
        self._client = httpx.AsyncClient(base_url=config.llm_api_base, timeout=300)
        self._api_key = config.llm_api_key
        self._model_name = config.llm_model_name

    async def generate(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        scene: str = "unknown",
    ) -> str:
        headers = _json_headers(self._api_key)
        payload = {
            "model": model or self._model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        system_prompt = next((m["content"] for m in messages if m.get("role") == "system"), "")
        user_prompt = next((m["content"] for m in messages if m.get("role") == "user"), "")
        trace_id = current_trace_id.get()
        t0 = time.perf_counter()
        try:
            response = await self._client.post("/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            completion = response.json()["choices"][0]["message"]["content"]
            usage = response.json().get("usage", {})
            duration_ms = int((time.perf_counter() - t0) * 1000)
            record_llm_call(
                trace_id=trace_id, scene=scene,
                system_prompt=system_prompt, user_prompt=user_prompt,
                completion=completion, model_name=model or self._model_name,
                duration_ms=duration_ms, status="success",
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )
            return completion
        except Exception as e:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            record_llm_call(
                trace_id=trace_id, scene=scene,
                system_prompt=system_prompt, user_prompt=user_prompt,
                completion="", model_name=model or self._model_name,
                duration_ms=duration_ms, status="error", error=str(e)[:500],
            )
            raise

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        headers = _json_headers(self._api_key)
        payload = {
            "model": model or self._model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        async with self._client.stream("POST", "/chat/completions", headers=headers, json=payload) as response:
            response.raise_for_status()
            async for chunk in response.aiter_lines():
                if chunk.startswith("data: "):
                    chunk = chunk[6:]
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        content = data["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except Exception:
                        continue

    async def close(self):
        await self._client.aclose()


class EmbeddingClient:
    def __init__(self):
        self._base_url = config.embedding_api_base
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=120) if self._base_url else None
        self._api_key = config.embedding_api_key
        self._model_name = config.embedding_model_name

    async def embed(self, texts: List[str]) -> List[List[float]]:
        """批量 embed。"""
        if not texts:
            return []
        if not self._client or not self._model_name:
            raise RuntimeError(
                "Gitee embedding is not configured. Set GITEE_API_KEY in the system "
                "environment; model configuration is managed by app_config.py."
            )
        # 截断过长文本，避免超出 token 限制
        truncated = [t[:8000] for t in texts]
        headers = _gitee_headers(self._api_key)
        payload = {
            "model": self._model_name,
            "input": truncated,
            "dimensions": config.embedding_dimensions,
            "extra_body": {
                "instruction": config.embedding_instruction,
            },
        }
        response = await self._client.post("/embeddings", headers=headers, json=payload)
        response.raise_for_status()
        return [item["embedding"] for item in response.json()["data"]]

    async def aembed_text(self, text: str) -> List[float]:
        """单文本 embed（async）。"""
        results = await self.embed([text])
        return results[0] if results else [0.0] * config.embedding_dimensions

    def embed_text(self, text: str) -> List[float]:
        """单文本 embed（sync 包装）。"""
        import asyncio
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aembed_text(text))
        raise RuntimeError(
            "Cannot use sync embed_text in async context. Use aembed_text instead."
        )

    async def close(self):
        if self._client:
            await self._client.aclose()


llm_client = LLMClient()
embedding_client = EmbeddingClient()
