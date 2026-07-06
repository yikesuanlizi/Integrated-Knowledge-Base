from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.models.schemas import QueryIntent, RetrievalTrace


@dataclass
class AgentState:
    question: str = ""
    trace_id: str = ""
    answer: str = ""
    needs_clarification: bool = False
    clarification_questions: List[str] = field(default_factory=list)

    intent: Optional[QueryIntent] = field(default_factory=QueryIntent)
    query_features: dict = field(default_factory=dict)
    planner_route: str = "fact"
    keywords: List[str] = field(default_factory=list)
    entities: dict = field(default_factory=dict)

    wiki_results: List[dict] = field(default_factory=list)
    chunk_results: List[dict] = field(default_factory=list)
    entity_results: List[dict] = field(default_factory=list)
    structured_results: List[dict] = field(default_factory=list)
    sql_result: dict = field(default_factory=dict)
    metadata_sql_trace: dict = field(default_factory=dict)
    uses_structured_metadata: bool = False

    merged_results: List[dict] = field(default_factory=list)
    expanded_results: List[dict] = field(default_factory=list)
    reranked_results: List[dict] = field(default_factory=list)

    evidence_pack: dict = field(default_factory=dict)
    citations: List[dict] = field(default_factory=list)

    evidence_sufficiency: dict = field(default_factory=dict)

    retrieval_trace: RetrievalTrace = field(default_factory=RetrievalTrace)

    iteration: int = 0
    max_iterations: int = 3
