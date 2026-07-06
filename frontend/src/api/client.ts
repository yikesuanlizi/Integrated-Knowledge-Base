import axios from "axios";
import type {
  IngestStatus,
  IngestResult,
  CompileRequest,
  CompileResult,
  CompileStatus,
  QueryRequest,
  QueryResponse,
  WikiCardInfo,
  WikiListResponse,
  ReviewInfo,
  ReviewStats,
  EvalResult,
  HealthStatus,
  Citation,
  RetrievalTrace,
  QueryIntent,
  SQLResult,
  NL2SQLStatus,
  QueryTraceListItem,
  QueryTraceDetail,
  LLMCallListItem,
  LLMCallDetail,
  MonitorStats,
  NL2SQLSeedResponse,
  NL2SQLQueryResponse,
  GoldenRetrievalCase,
  GoldenRetrievalReport,
  EvalFixturesResponse,
  KnowledgeOverview,
  IndexStatus,
  DocumentListResponse,
  ChunkListResponse,
  EntityListResponse,
  KnowledgeResetResponse,
} from "@/types";

const BASE_URL = import.meta.env.VITE_API_BASE || "";

const http = axios.create({
  baseURL: BASE_URL,
  timeout: 120_000,
});

type CacheEntry<T> = {
  expiresAt: number;
  value: T;
};

const apiCache = new Map<string, CacheEntry<unknown>>();
const STATUS_CACHE_TTL = 30_000;
const LIST_CACHE_TTL = 15_000;

async function cached<T>(key: string, ttlMs: number, loader: () => Promise<T>, force = false): Promise<T> {
  const now = Date.now();
  const hit = apiCache.get(key) as CacheEntry<T> | undefined;
  if (!force && hit && hit.expiresAt > now) return hit.value;
  const value = await loader();
  apiCache.set(key, { value, expiresAt: now + ttlMs });
  return value;
}

export function invalidateApiCache(prefix = "") {
  if (!prefix) {
    apiCache.clear();
    return;
  }
  for (const key of Array.from(apiCache.keys())) {
    if (key.startsWith(prefix)) apiCache.delete(key);
  }
}

function invalidateKnowledgeCaches() {
  invalidateApiCache("ingest:");
  invalidateApiCache("knowledge:");
  invalidateApiCache("wiki:");
  invalidateApiCache("review:");
  invalidateApiCache("chunk-review:");
}

// ============ Ingest ============
export async function ingestFile(
  file: File,
  onUploadProgress?: (progress: number) => void,
): Promise<IngestResult> {
  const form = new FormData();
  form.append("file", file);
  const res = await http.post("/api/ingest/file", form, {
    headers: { "Content-Type": "multipart/form-data" },
    onUploadProgress: (e) => {
      if (onUploadProgress && e.total) onUploadProgress(e.loaded / e.total);
    },
  });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function ingestPath(path: string): Promise<IngestResult> {
  const res = await http.post("/api/ingest/path", { path, metadata: {}, force: false });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function getIngestStatus(force = false): Promise<IngestStatus> {
  return cached("ingest:status", STATUS_CACHE_TTL, async () => {
    const res = await http.get("/api/ingest/status");
    return res.data;
  }, force);
}

// ============ Compile ============
export async function compileKnowledge(build_id?: string): Promise<CompileResult> {
  const body: CompileRequest = { build_id, force: false };
  const res = await http.post("/api/compile/", body);
  invalidateKnowledgeCaches();
  return res.data;
}

export async function getCompileStatus(build_id: string): Promise<CompileStatus> {
  const res = await http.get(`/api/compile/${build_id}`);
  return res.data;
}

// ============ Query ============
export async function queryKnowledge(request: QueryRequest): Promise<QueryResponse> {
  const res = await http.post("/api/query/", request);
  return res.data;
}

/** SSE streaming query.
 *  - onToken(token, partial) 每收到一条流式文本片段就回调
 *  - onDone({ fullAnswer, citations, trace, intent }) 收到 done 事件或连接关闭时回调
 *  - onError(err) 收到 error 事件或连接错误时回调
 * 返回值：调用可主动终止流
 */
export function streamQuery(
  request: QueryRequest,
  onToken: (token: string, partial: string) => void,
  onDone: (payload: { fullAnswer: string; citations: Citation[]; trace?: RetrievalTrace; intent?: QueryIntent; sql_result?: SQLResult }) => void,
  onError: (err: Error) => void,
): () => void {
  const abortCtrl = new AbortController();
  const url = `${BASE_URL}/api/query/stream`;

  fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(request),
    signal: abortCtrl.signal,
  })
    .then(async (resp) => {
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const reader = resp.body?.getReader();
      if (!reader) throw new Error("No response body");
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let fullAnswer = "";
      let pendingIntent: QueryIntent | undefined;
      let pendingCitations: Citation[] = [];
      let pendingTrace: RetrievalTrace | undefined;
      let pendingSqlResult: SQLResult | undefined;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE 消息由空行分隔
        const messages = buffer.split("\n\n");
        buffer = messages.pop() || "";

        for (const msg of messages) {
          if (!msg.trim()) continue;

          let eventType = "";
          let data = "";
          for (const rawLine of msg.split("\n")) {
            const line = rawLine.trimEnd();
            if (!line) continue;
            if (line.startsWith("event:")) eventType = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
          }
          if (!data) continue;

          if (data === "[DONE]") {
            onDone({ fullAnswer, citations: pendingCitations, trace: pendingTrace, intent: pendingIntent, sql_result: pendingSqlResult });
            return;
          }

          try {
            const obj = JSON.parse(data);
            if (eventType === "answer") {
              const token: string = obj.token || obj.chunk || obj.content || obj.answer || obj.text || "";
              if (token) {
                fullAnswer += token;
                onToken(token, fullAnswer);
              }
            } else if (eventType === "done") {
              pendingCitations = obj.citations || [];
              pendingTrace = obj.trace;
              pendingSqlResult = obj.sql_result;
              onDone({ fullAnswer, citations: pendingCitations, trace: pendingTrace, intent: pendingIntent, sql_result: pendingSqlResult });
              return;
            } else if (eventType === "error") {
              throw new Error(obj.error || "Query failed");
            } else if (eventType === "intent") {
              pendingIntent = obj;
            }
            // 其他事件（config 等）忽略
          } catch (e) {
            // Non-JSON data; treat as plaintext token
            if (eventType === "answer") {
              fullAnswer += data;
              onToken(data, fullAnswer);
            }
          }
        }
      }

      // 连接自然关闭时也回调一次 done
      onDone({ fullAnswer, citations: pendingCitations, trace: pendingTrace, intent: pendingIntent, sql_result: pendingSqlResult });
    })
    .catch((err) => {
      if ((err as { name?: string }).name === "AbortError") return;
      onError(err as Error);
    });

  return () => abortCtrl.abort();
}

export async function classifyIntent(question: string) {
  const res = await http.post("/api/query/intent", { question });
  return res.data;
}

// ============ NL2SQL ============
export async function getNL2SQLStatus(): Promise<NL2SQLStatus> {
  return cached("nl2sql:status", STATUS_CACHE_TTL, async () => {
    const res = await http.get("/api/nl2sql/status");
    return res.data;
  });
}

export async function seedNL2SQL(): Promise<NL2SQLSeedResponse> {
  const res = await http.post("/api/nl2sql/seed");
  invalidateApiCache("nl2sql:");
  return res.data;
}

export async function queryNL2SQL(question: string, limit = 100): Promise<NL2SQLQueryResponse> {
  const res = await http.post("/api/nl2sql/query", { question, limit });
  return res.data;
}

// ============ Wiki ============
export async function listWikiCards(
  page = 1,
  page_size = 20,
  card_type?: string,
  status?: string,
  force = false,
): Promise<WikiListResponse> {
  const key = `wiki:list:${page}:${page_size}:${card_type || ""}:${status || ""}`;
  return cached(key, LIST_CACHE_TTL, async () => {
    const res = await http.get("/api/wiki/", { params: { page, page_size, card_type, status } });
    return res.data;
  }, force);
}

export async function getWikiCard(card_id: string): Promise<WikiCardInfo> {
  const res = await http.get(`/api/wiki/${card_id}`);
  return res.data;
}

export async function getWikiCardMarkdown(card_id: string): Promise<string> {
  const res = await http.get<{ card_id: string; markdown: string; title: string }>(
    `/api/wiki/${card_id}/markdown`,
  );
  return res.data.markdown || "";
}

/** 返回 Wiki 卡片数组。 */
export async function searchWikiFulltext(keyword: string, top_k = 10, status?: string): Promise<WikiCardInfo[]> {
  const res = await http.get("/api/wiki/search/fulltext", { params: { keyword, top_k, status: status || undefined } });
  return res.data;
}

// ============ Review ============
export async function listReviews(status = "review", page = 1, page_size = 20): Promise<{
  reviews: ReviewInfo[];
  total: number;
  page: number;
  page_size: number;
}> {
  const res = await http.get("/api/review/", { params: { status, page, page_size } });
  return res.data;
}

export async function approveReview(review_id: string, reviewer = "", notes = "") {
  const res = await http.post(`/api/review/${review_id}/approve`, { reviewer, notes });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function approveReviews(review_ids: string[], reviewer = "", notes = "") {
  const res = await http.post("/api/review/batch/approve", { review_ids, reviewer, notes });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function rejectReview(review_id: string, reviewer = "", notes = "") {
  const res = await http.post(`/api/review/${review_id}/reject`, { reviewer, notes });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function rejectReviews(review_ids: string[], reviewer = "", notes = "") {
  const res = await http.post("/api/review/batch/reject", { review_ids, reviewer, notes });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function getReviewStats(force = false): Promise<ReviewStats> {
  return cached("review:stats", STATUS_CACHE_TTL, async () => {
    const res = await http.get("/api/review/stats/overview");
    return res.data;
  }, force);
}

export async function listChunkReviews(status = "review", page = 1, page_size = 20): Promise<{
  reviews: ReviewInfo[];
  total: number;
  page: number;
  page_size: number;
}> {
  const res = await http.get("/api/chunk-review/", { params: { status, page, page_size } });
  return res.data;
}

export async function approveChunkReview(chunk_id: string, reviewer = "", notes = "") {
  const res = await http.post(`/api/chunk-review/${chunk_id}/approve`, { reviewer, notes });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function approveChunkReviews(chunk_ids: string[], reviewer = "", notes = "") {
  const res = await http.post("/api/chunk-review/batch/approve", { chunk_ids, reviewer, notes });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function rejectChunkReview(chunk_id: string, reviewer = "", notes = "") {
  const res = await http.post(`/api/chunk-review/${chunk_id}/reject`, { reviewer, notes });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function rejectChunkReviews(chunk_ids: string[], reviewer = "", notes = "") {
  const res = await http.post("/api/chunk-review/batch/reject", { chunk_ids, reviewer, notes });
  invalidateKnowledgeCaches();
  return res.data;
}

export async function getChunkReviewStats(force = false): Promise<ReviewStats> {
  return cached("chunk-review:stats", STATUS_CACHE_TTL, async () => {
    const res = await http.get("/api/chunk-review/stats/overview");
    return res.data;
  }, force);
}

// ============ Eval ============
export async function runEval(kind: "health" | "citation" | "retrieval" | "evidence" | "full", build_id?: string): Promise<EvalResult> {
  const res = await http.post(`/api/eval/${kind}`, { build_id });
  return res.data;
}

export async function runGoldenRetrievalEval(cases: GoldenRetrievalCase[], top_k = 10): Promise<GoldenRetrievalReport> {
  const res = await http.post("/api/eval/retrieval/run", { cases, top_k });
  return res.data;
}

export async function getLatestRetrievalReport(): Promise<GoldenRetrievalReport | null> {
  const res = await http.get("/api/eval/retrieval/report/latest");
  return res.data || null;
}

export async function listRetrievalReports(): Promise<GoldenRetrievalReport[]> {
  const res = await http.get("/api/eval/retrieval/reports");
  return res.data.reports || [];
}

export async function getEvalFixtures(buildId = ""): Promise<EvalFixturesResponse> {
  const res = await http.get("/api/eval/fixtures", { params: { build_id: buildId || undefined } });
  return res.data;
}

// ============ Health ============
export async function getHealth(): Promise<HealthStatus> {
  const res = await http.get("/api/health/");
  return res.data;
}

export async function getPing(): Promise<{ pong?: boolean; status?: string; timestamp?: string }> {
  const res = await http.get("/api/health/ping");
  return res.data;
}

// ============ Export ============
export async function exportWiki(
  format: "markdown" | "json" | "jsonld" | "graphml" | "llms" | "marp",
  card_ids?: string[],
): Promise<string> {
  const res = await http.post(`/api/export/${format}`, { card_ids: card_ids || [] });
  return res.data;
}

// ============ Knowledge ============
/** 知识库总览统计。 */
export async function getKnowledgeOverview(force = false): Promise<KnowledgeOverview> {
  return cached("knowledge:overview", STATUS_CACHE_TTL, async () => {
    const res = await http.get("/api/knowledge/overview");
    return res.data;
  }, force);
}

/** 索引状态。 */
export async function getIndexStatus(force = false): Promise<IndexStatus> {
  return cached("knowledge:indexes", STATUS_CACHE_TTL, async () => {
    const res = await http.get("/api/knowledge/indexes");
    return res.data;
  }, force);
}

/** 清空知识库测试数据和索引。 */
export async function resetKnowledgeStorage(): Promise<KnowledgeResetResponse> {
  const res = await http.post("/api/knowledge/reset");
  invalidateApiCache();
  return res.data;
}

/** 文档列表。 */
export async function listDocuments(keyword = "", page = 1, pageSize = 20): Promise<DocumentListResponse> {
  const res = await http.get("/api/knowledge/documents", { params: { keyword, page, page_size: pageSize } });
  return res.data;
}

/** 原文切块列表。 */
export async function listChunks(keyword = "", status = "", page = 1, pageSize = 20): Promise<ChunkListResponse> {
  const res = await http.get("/api/knowledge/chunks", { params: { keyword, status, page, page_size: pageSize } });
  return res.data;
}

/** 实体列表。 */
export async function listEntities(keyword = "", entityType = "", page = 1, pageSize = 20): Promise<EntityListResponse> {
  const res = await http.get("/api/knowledge/entities", { params: { keyword, entity_type: entityType, page, page_size: pageSize } });
  return res.data;
}

// ============ Monitor ============

/** 查询历史列表。 */
export async function listMonitorQueries(page = 1, pageSize = 20): Promise<{ items: QueryTraceListItem[]; total: number; page: number; page_size: number }> {
  const res = await http.get("/api/monitor/queries", { params: { page, page_size: pageSize } });
  return res.data;
}

/** 单次查询详情。 */
export async function getMonitorQueryDetail(traceId: string): Promise<QueryTraceDetail> {
  const res = await http.get(`/api/monitor/queries/${traceId}`);
  return res.data;
}

/** LLM 调用列表。 */
export async function listMonitorLLMCalls(page = 1, pageSize = 20, scene?: string): Promise<{ items: LLMCallListItem[]; total: number; page: number; page_size: number }> {
  const res = await http.get("/api/monitor/llm-calls", { params: { page, page_size: pageSize, scene } });
  return res.data;
}

/** 单次 LLM 调用详情。 */
export async function getMonitorLLMCallDetail(callId: string): Promise<LLMCallDetail> {
  const res = await http.get(`/api/monitor/llm-calls/${callId}`);
  return res.data;
}

/** 聚合统计。 */
export async function getMonitorStats(hours = 24): Promise<MonitorStats> {
  const res = await http.get("/api/monitor/stats", { params: { hours } });
  return res.data;
}
