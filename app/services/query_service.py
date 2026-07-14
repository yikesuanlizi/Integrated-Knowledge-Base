"""问答服务：封装 query API 的业务逻辑。"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.agent.graph import run_agent_sync
from app.core.log import logger
from app.retrieval.intent import classify_intent, get_intent_config


class QueryService:
    """问答服务，封装 Agent 问答逻辑。"""

    def query(
        self,
        question: str,
        top_k: int = 8,
        strict: bool = True,
        build_id: Optional[str] = None,
        filters: Optional[dict] = None,
        history: Optional[List[dict]] = None,
    ) -> dict:
        """执行一次 Agent 问答。

        Args:
            question: 用户问题。
            top_k: 召回数量。
            strict: 是否严格模式。
            build_id: 可选的 build ID。
            filters: 可选的过滤条件。
            history: 可选的对话历史。

        Returns:
            问答结果 dict。
        """
        try:
            state = run_agent_sync(
                question,
                top_k=top_k,
                conversation_id=None,
                history=history or [],
            )
        except Exception as e:
            logger.error(f"Agent run failed: {e}", exc_info=True)
            return {
                "question": question,
                "answer": f"Agent 执行失败: {e}",
                "needs_clarification": False,
                "clarification_questions": [],
                "citations": [],
                "intent": None,
                "mode": "evidence_lookup",
                "retrieval_trace": None,
            }

        trace = state.retrieval_trace.model_dump() if state.retrieval_trace else None
        if trace is not None and state.intent:
            trace["intent"] = state.intent.model_dump()

        return {
            "question": question,
            "answer": state.answer or "",
            "needs_clarification": state.needs_clarification,
            "clarification_questions": state.clarification_questions,
            "citations": state.citations,
            "mode": "mixed" if state.uses_structured_metadata else "evidence_lookup",
            "retrieval_trace": trace,
            "sql_result": state.sql_result or None,
        }

    async def query_stream(
        self,
        question: str,
        top_k: int = 8,
    ) -> AsyncGenerator[str, None]:
        """流式问答，返回 SSE 格式的生成器。

        Args:
            question: 用户问题。
            top_k: 召回数量。

        Yields:
            SSE 格式的事件字符串。
        """
        try:
            intent = classify_intent(question)
            yield f"event: intent\ndata: {json.dumps(intent.model_dump(), ensure_ascii=False)}\n\n"

            config = get_intent_config(intent)
            yield f"event: config\ndata: {json.dumps(config, ensure_ascii=False)}\n\n"

            loop = asyncio.get_running_loop()
            state = await loop.run_in_executor(None, run_agent_sync, question, top_k, None, [])

            answer = state.answer or ""
            chunks = re.split(r"(\n\n+)", answer)
            for chunk in chunks:
                if not chunk:
                    continue
                yield f"event: answer\ndata: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"

            def _to_dict(x: Any) -> Any:
                if hasattr(x, "model_dump"):
                    return x.model_dump()
                return x

            citations_data = [_to_dict(c) for c in (state.citations or [])]
            trace_data = state.retrieval_trace.model_dump() if state.retrieval_trace else None
            yield f"event: done\ndata: {json.dumps({'citations': citations_data, 'trace': trace_data, 'mode': 'mixed' if state.uses_structured_metadata else 'evidence_lookup', 'sql_result': state.sql_result or None}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Stream query failed: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
