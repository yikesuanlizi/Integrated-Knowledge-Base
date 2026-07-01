export interface IngestStatus {
  milvus_chunks: number;
  elasticsearch_chunks: number;
  documents: number;
  pg_chunks: number;
  approved_chunks: number;
  review_chunks: number;
  rejected_chunks: number;
}

export interface IngestResult {
  path: string;
  ingested: number;
  skipped: number;
  failed: number;
  documents: Array<{
    filename: string;
    chunks?: number;
    status?: string;
    error?: string;
  }>;
  build_id?: string;
  wiki?: {
    status: string;
    reason?: string;
    build_id?: string;
    error?: string;
    wiki_card_count?: number;
    linked_chunks?: number;
  };
}

export interface CompileRequest {
  build_id?: string;
  force?: boolean;
}

export interface CompileResult {
  build_id: string;
  status: string;
  wiki_card_count: number;
  linked_chunks: number;
  pages?: number;
  concepts?: number;
  warnings?: string[];
  errors?: string[];
}

export interface CompileStatus {
  build_id: string;
  status: string;
  card_count: number;
  timestamp: string;
}

export interface QueryIntent {
  primary: string;
  secondary: string[];
  confidence: number;
  route: string;
  keywords: string[];
  entities: Record<string, unknown>;
  safety_sensitive: boolean;
  expects_procedure: boolean;
}

export interface RetrievalTrace {
  strategy: string;
  build_id?: string;
  query_variants?: string[];
  conversation_context?: Record<string, unknown>;
  context_expanded?: boolean;
  citations_used?: number[];
  wiki_enabled?: boolean;
  wiki_hits?: Array<Record<string, unknown>>;
  evidence_sufficiency?: Record<string, unknown>;
  grounding?: Record<string, unknown>;
  intent?: QueryIntent;
  mode?: "online_observation" | "golden_eval";
  stages?: RetrievalTraceStage[];
  channels?: Record<string, RetrievalTraceChannel>;
  merged_count?: number;
  reranked_count?: number;
  selected_evidence?: RetrievalTraceCandidate[];
}

export interface RetrievalTraceStage {
  name: string;
  label: string;
  [key: string]: unknown;
}

export interface RetrievalTraceCandidate {
  id: string;
  source_type: string;
  title: string;
  score: number;
  status?: string;
  freshness?: string;
  source?: string;
  selected?: boolean;
  snippet?: string;
}

export interface RetrievalTraceChannel {
  label: string;
  query?: string;
  used: boolean;
  hit_count: number;
  top_candidates: RetrievalTraceCandidate[];
  error?: string | null;
  decision?: Record<string, unknown> | null;
}

export interface QueryRequest {
  question: string;
  top_k?: number;
  strict?: boolean;
  build_id?: string;
  filters?: Record<string, unknown>;
  history?: Array<{ role: string; content: string }>;
}

export interface QueryResponse {
  question: string;
  answer: string;
  needs_clarification: boolean;
  clarification_questions: string[];
  citations: Citation[];
  mode: string;
  retrieval_trace?: RetrievalTrace;
  sql_result?: SQLResult;
}

export interface SQLResult {
  sql: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
}

export interface NL2SQLStatus {
  seeded: boolean;
  tables: Record<string, number>;
  metadata: Record<string, number>;
  indexes: Record<string, unknown>;
  warnings: string[];
}

export interface NL2SQLSeedResponse {
  status: string;
  tables: Record<string, number>;
  metadata: Record<string, number>;
  indexes: Record<string, unknown>;
  warnings: string[];
}

export interface NL2SQLQueryResponse {
  question: string;
  mode: "structured_lookup";
  sql: string;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count: number;
  explanation: string;
  trace: Record<string, unknown>;
}

export interface Citation {
  citation_id: number;
  chunk_id: string;
  doc_id: string;
  file_name: string;
  source_ref: string;
  page_start?: number;
  page_end?: number;
  section_path?: string;
  block_type?: string;
  score: number;
  snippet: string;
  parse_blocks?: Array<Record<string, unknown>>;
  figures?: Array<Record<string, unknown>>;
}

export interface WikiCardInfo {
  card_id: string;
  build_id?: string;
  card_type: string;
  title: string;
  content: string;
  source_ref: string;
  status: string;
  score?: number;
  linked_chunks?: string[];
  confidence?: number;
  created_at?: string;
  notes?: string;
}

export interface WikiListResponse {
  cards: WikiCardInfo[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReviewInfo {
  review_id: string;
  card_id: string;
  chunk_id?: string;
  build_id?: string;
  doc_id?: string;
  file_name?: string;
  card_title?: string;
  card_type?: string;
  card_content?: string;
  content?: string;
  source_ref?: string;
  confidence?: number;
  linked_chunks?: string[];
  status: string;
  reviewer: string;
  notes: string;
  created_at: string;
  section_path?: string;
  block_type?: string;
}

export interface ReviewStats {
  total: number;
  pending_review: number;
  approved: number;
  rejected: number;
}

export interface EvalResult {
  build_id: string;
  health_score: number;
  citation_coverage: number;
  retrieval_precision: number;
  evidence_completeness: number;
  report: string;
  overall_score?: number;
  queries?: string[];
  query_source?: string;
  errors?: string[];
  health?: Record<string, unknown>;
  citation?: Record<string, unknown>;
  retrieval?: Record<string, unknown>;
  evidence?: Record<string, unknown>;
  timestamp?: string;
}

export interface GoldenRetrievalCase {
  question: string;
  expected_doc_ids?: string[];
  expected_chunk_ids?: string[];
  expected_card_ids?: string[];
  intent?: string;
  tags?: string[];
}

export interface EvalFixturesResponse {
  source: "corpus" | "fallback";
  questions: string[];
  retrieval_cases: GoldenRetrievalCase[];
  warnings: string[];
}

export interface GoldenRetrievalReport {
  id: string;
  timestamp: string;
  mode: "golden_eval";
  total_queries: number;
  recall_at_1: number;
  recall_at_3: number;
  recall_at_5: number;
  recall_at_10: number;
  mrr: number;
  hit_rate: number;
  missed_queries: string[];
  missed_count: number;
  channel_contribution: Record<string, number>;
  intent_breakdown: Record<string, { total: number; recall_at_10: number }>;
  details: Array<Record<string, unknown>>;
}

export interface HealthStatus {
  status: string;
  version: string;
  timestamp: string;
  services?: Record<string, unknown>;
}

// 知识库总览
export interface KnowledgeOverview {
  documents: number;
  chunks: number;
  wiki_cards: number;
  entities: number;
  reviews: {
    pending: number;
    approved: number;
    rejected: number;
  };
  indexes: {
    milvus_chunks: number;
    es_chunks: number;
    es_entities: number;
  };
  qa_ready: {
    approved_cards: number;
    approved_chunks: number;
  };
}

// 索引状态
export interface IndexStatus {
  milvus: { ok: boolean; rag_chunks?: number; error?: string };
  elasticsearch: { ok: boolean; knowledge_chunks?: number; entities?: number; error?: string };
  postgres: { ok: boolean; documents?: number; chunks?: number; wiki_cards?: number; wiki_reviews?: number; error?: string };
  nl2sql: { ok: boolean; table_info?: number; column_info?: number; metric_info?: number; value_info?: number; seeded?: boolean; warnings?: string[]; error?: string };
}

export interface KnowledgeResetStep {
  layer: string;
  table?: string;
  path?: string;
  bucket?: string;
  ok: boolean;
  error?: string;
}

export interface KnowledgeResetResponse {
  ok: boolean;
  steps: KnowledgeResetStep[];
}

// 文档列表
export interface DocumentItem {
  doc_id: string;
  file_name: string;
  source_path: string;
  manual_type: string;
  aircraft_model: string;
  engine_model: string;
  ata_chapter: string;
  manual_revision: string;
  effective_date: string;
  applicability: string;
  language: string;
  confidentiality: string;
  parser_name: string;
  parser_version: string;
  created_at: string;
  chunk_count: number;
  card_count: number;
}

export interface DocumentListResponse {
  documents: DocumentItem[];
  total: number;
  page: number;
  page_size: number;
}

// 原文切块
export interface ChunkItem {
  chunk_id: string;
  doc_id: string;
  content: string;
  source_file: string;
  section_path: string;
  block_type: string;
  page_numbers: number[] | null;
  status: string;
  score: number;
}

export interface ChunkListResponse {
  chunks: ChunkItem[];
  total: number;
  page: number;
  page_size: number;
}

// 实体
export interface EntityItem {
  entity_type: string;
  value: string;
  chunk_ids: string[];
  count: number;
  score: number;
}

export interface EntityListResponse {
  entities: EntityItem[];
  total: number;
  page: number;
  page_size: number;
}
