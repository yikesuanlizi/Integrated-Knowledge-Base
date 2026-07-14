from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.models.schemas import QueryIntent, RetrievalTrace


@dataclass
class AgentState:
    question: str = ""
    original_question: str = ""
    raw_question: str = ""
    conversation_id: str = ""
    history: List[Dict[str, Any]] = field(default_factory=list)
    resolved_question: str = ""
    reference_entities: List[str] = field(default_factory=list)
    conversation_context: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    answer: str = ""
    needs_clarification: bool = False
    clarification_questions: List[str] = field(default_factory=list)
    rewrite_history: List[Dict[str, Any]] = field(default_factory=list)

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

    answer_requirements: dict = field(default_factory=lambda: {"procedure": False, "warning": False, "parameter": False, "applicability": False, "tooling": False})
    applicability_filters: dict = field(default_factory=lambda: {"aircraft_model": None, "manual_type": None, "ata_chapter": None})
    evidence_roles: Dict[str, List[str]] = field(default_factory=dict)
    applicability_stats: dict = field(default_factory=lambda: {"aircraft_models": set(), "manual_types": set(), "ata_chapters": set(), "revisions": set()})
    applicability_conflict: bool = False
    missing_requirements: List[str] = field(default_factory=list)
    applicability_summary: str = ""

    retrieval_trace: RetrievalTrace = field(default_factory=RetrievalTrace)

    iteration: int = 0
    max_iterations: int = 3

    retrieval_plan: Dict[str, Any] = field(default_factory=dict)
    planner_feedback: Dict[str, Any] = field(default_factory=dict)

    _node_executions: List[Dict[str, Any]] = field(default_factory=list, repr=False)
