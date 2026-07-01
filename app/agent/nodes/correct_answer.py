"""12. correct_answer - 证据不足时降级或重新检索。"""
from __future__ import annotations

from app.agent.state import AgentState
from app.agent.nodes.generate_answer import _finalize_answer_text
from app.core.log import logger


def correct_answer_node(state: AgentState) -> AgentState:
    state.iteration += 1

    if state.iteration >= state.max_iterations:
        # 已达最大迭代，输出降级答案
        items = state.reranked_results[:3]
        if items:
            parts = []
            for item in items:
                content = item.get("content", "")
                if content:
                    parts.append(_finalize_answer_text(str(content)[:300]))
            if len(parts) == 1:
                state.answer = parts[0]
            else:
                state.answer = "\n\n".join(parts)
        else:
            state.answer = "抱歉，没有找到相关信息。"
        return state

    logger.info(f"Correcting answer, iteration {state.iteration}/{state.max_iterations}")
    return state
