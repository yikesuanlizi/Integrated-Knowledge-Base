from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".markdown"}


class DocumentMetadata(BaseModel):
    manual_type: Optional[str] = None
    aircraft_model: Optional[str] = None
    engine_model: Optional[str] = None
    ata_chapter: Optional[str] = None
    manual_revision: Optional[str] = None
    effective_date: Optional[str] = None
    applicability: Optional[str] = None
    language: Optional[str] = None
    confidentiality: Optional[str] = None

    def merged_with(self, inferred: "DocumentMetadata") -> "DocumentMetadata":
        data = inferred.model_dump()
        for key, value in self.model_dump().items():
            if value not in (None, ""):
                data[key] = value
        return DocumentMetadata(**data)


class IngestPathRequest(BaseModel):
    path: str
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    force: bool = False
    build_id: Optional[str] = None


class QueryRequest(BaseModel):
    question: str
    top_k: int = Field(default=8, ge=1, le=30)
    strict: bool = True
    build_id: Optional[str] = None
    filters: DocumentMetadata = Field(default_factory=DocumentMetadata)
    conversation_id: Optional[str] = None
    history: List["ConversationTurn"] = Field(default_factory=list, max_length=12)


class ConversationTurn(BaseModel):
    role: str
    content: str


class Citation(BaseModel):
    citation_id: int
    chunk_id: str
    doc_id: str
    file_name: str
    source_ref: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    section_path: Optional[str] = None
    block_type: Optional[str] = None
    score: float
    snippet: str
    parse_blocks: List[dict] = Field(default_factory=list)
    figures: List[dict] = Field(default_factory=list)
    card_id: Optional[str] = None


class QueryIntent(BaseModel):
    primary: str = "general_lookup"
    secondary: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    route: str = "evidence_lookup"
    keywords: List[str] = Field(default_factory=list)
    entities: dict = Field(default_factory=dict)
    safety_sensitive: bool = False
    expects_procedure: bool = False


class RetrievalTrace(BaseModel):
    strategy: str = "not_set"
    build_id: Optional[str] = None
    query_variants: List[str] = Field(default_factory=list)
    conversation_context: dict = Field(default_factory=dict)
    context_expanded: bool = False
    citations_used: List[int] = Field(default_factory=list)
    wiki_enabled: bool = False
    wiki_hits: List[dict] = Field(default_factory=list)
    evidence_sufficiency: dict = Field(default_factory=dict)
    grounding: dict = Field(default_factory=dict)
    intent: Optional[QueryIntent] = None
    mode: str = "online_observation"
    stages: List[dict] = Field(default_factory=list)
    channels: dict = Field(default_factory=dict)
    merged_count: int = 0
    reranked_count: int = 0
    selected_evidence: List[dict] = Field(default_factory=list)
    history_prompt_enforced: bool = True
    answer_requirements: dict = Field(default_factory=dict)
    applicability_filters: dict = Field(default_factory=dict)
    evidence_roles: dict = Field(default_factory=dict)
    applicability_stats: dict = Field(default_factory=dict)
    applicability_conflict: bool = False
    missing_requirements: List[str] = Field(default_factory=list)
    applicability_summary: str = ""


class QueryResponse(BaseModel):
    question: str
    answer: str
    needs_clarification: bool
    clarification_questions: List[str]
    citations: List[Citation]
    mode: str
    retrieval_trace: Optional[RetrievalTrace] = None
    sql_result: Optional[dict] = None


class IngestResult(BaseModel):
    path: str
    ingested: int
    skipped: int
    failed: int
    documents: List[dict]
    build_id: Optional[str] = None
    wiki: Optional[dict] = None


@dataclass(frozen=True)
class ParsedPage:
    page_no: int
    text: str


@dataclass(frozen=True)
class ParsedBlock:
    block_index: int
    page_no: Optional[int]
    block_type: str
    text: str
    section_path: Optional[str] = None
    bbox_json: Optional[str] = None
    table_json: Optional[str] = None
    raw_json: Optional[str] = None


@dataclass(frozen=True)
class ParsedArtifact:
    parser_name: str
    parser_version: Optional[str]
    source_format: str
    status: str
    page_count: int
    markdown: Optional[str] = None
    raw_json: Optional[dict] = None
    warnings: tuple = ()
    ocr_enabled: Optional[bool] = None


@dataclass(frozen=True)
class ParsedDocument:
    path: Path
    pages: List[ParsedPage]
    metadata: DocumentMetadata
    artifact: ParsedArtifact
    blocks: List[ParsedBlock]


@dataclass
class ChunkMetadata:
    block_type: Optional[str] = None
    section_path: Optional[str] = None
    page_numbers: Optional[List[int]] = None


@dataclass
class Chunk:
    chunk_id: str = ""
    doc_id: str = ""
    raw_content: str = ""
    search_content: str = ""
    embedding_content: str = ""
    content: str = ""
    source_file: Optional[str] = None
    metadata: ChunkMetadata = field(default_factory=ChunkMetadata)
    chunk_index: int = 0

    def __post_init__(self) -> None:
        legacy_content = self.content or ""
        if not self.raw_content:
            self.raw_content = legacy_content
        if not self.search_content:
            self.search_content = self.raw_content
        if not self.embedding_content:
            self.embedding_content = self.search_content
        self.content = self.raw_content


class EntityType(str, Enum):
    PART_NUMBER = "part_number"
    COMPONENT = "component"
    MATERIAL_CODE = "material_code"
    SERIAL_NUMBER = "serial_number"
    WORK_ORDER = "work_order"
    REVISION = "revision"
    ACTION = "action"
    WARNING = "warning"
    REQUIREMENT = "requirement"


class Entity(BaseModel):
    entity_type: EntityType
    value: str
    start_pos: Optional[int] = None
    end_pos: Optional[int] = None


class BuildInfo(BaseModel):
    build_id: str
    kind: str
    status: str
    document_count: int
    chunk_count: int
    wiki_card_count: int
    created_at: str
    finished_at: Optional[str] = None


class WikiCardInfo(BaseModel):
    card_id: str
    card_type: str
    title: str
    text: str
    source_ref: str
    confidence: float
    status: str
    created_at: str


class ReviewStatus(str, Enum):
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewInfo(BaseModel):
    review_id: str
    card_id: str
    status: str
    reviewer: str
    notes: str
    created_at: str


class EvalResult(BaseModel):
    build_id: str
    health_score: float
    citation_coverage: float
    retrieval_precision: float
    evidence_completeness: float
    report: str


class CompileRequest(BaseModel):
    build_id: Optional[str] = None
    force: bool = False


class CompileResult(BaseModel):
    build_id: str
    status: str
    wiki_card_count: int
    linked_chunks: int
