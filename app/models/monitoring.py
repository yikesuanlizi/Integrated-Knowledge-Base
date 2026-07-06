"""监控 ORM 模型：查询链路、LLM 调用、节点执行追踪。"""
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB

from app.core.database import Base


class QueryTrace(Base):
    """查询链路持久化：每次问答的完整检索 trace。"""
    __tablename__ = "query_traces"

    trace_id = Column(String, primary_key=True)
    question = Column(Text, nullable=False)
    answer_summary = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    node_count = Column(Integer, default=0)
    llm_call_count = Column(Integer, default=0)
    status = Column(String, default="success")
    intent = Column(String, default="")
    stages_json = Column(JSONB, default=list)
    channels_json = Column(JSONB, default=dict)
    selected_evidence_json = Column(JSONB, default=list)
    evidence_sufficiency = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LLMCall(Base):
    """LLM 调用记录：每次 LLM 调用的完整输入输出。"""
    __tablename__ = "llm_calls"

    call_id = Column(String, primary_key=True)
    trace_id = Column(String, nullable=True, index=True)
    scene = Column(String, default="unknown")
    system_prompt = Column(Text, default="")
    user_prompt = Column(Text, default="")
    completion = Column(Text, default="")
    model_name = Column(String, default="")
    duration_ms = Column(Integer, default=0)
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    status = Column(String, default="success")
    error = Column(Text, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NodeExecution(Base):
    """节点执行追踪：Agent Graph 每个 node 的执行明细。"""
    __tablename__ = "node_executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trace_id = Column(String, nullable=False, index=True)
    node_name = Column(String, nullable=False)
    input_summary = Column(Text, default="")
    output_summary = Column(Text, default="")
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), onupdate=func.now())
    duration_ms = Column(Integer, default=0)
    status = Column(String, default="success")
    error = Column(Text, default="")
