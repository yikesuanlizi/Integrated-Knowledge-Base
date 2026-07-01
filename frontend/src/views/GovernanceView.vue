<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  approveChunkReview,
  approveChunkReviews,
  approveReview,
  approveReviews,
  getChunkReviewStats,
  getHealth,
  getIngestStatus,
  getNL2SQLStatus,
  getPing,
  getReviewStats,
  listChunkReviews,
  listReviews,
  rejectChunkReview,
  rejectChunkReviews,
  rejectReview,
  rejectReviews,
  resetKnowledgeStorage,
  runEval,
} from "@/api/client";
import type {
  EvalResult,
  HealthStatus,
  IngestStatus,
  KnowledgeResetResponse,
  NL2SQLStatus,
  ReviewInfo,
  ReviewStats,
} from "@/types";
import RetrievalEvalPanel from "@/components/RetrievalEvalPanel.vue";
import AppIcon from "@/components/AppIcon.vue";

type TabKey = "review" | "quality" | "runtime" | "indexes";
type ReviewScope = "chunk" | "wiki";

const route = useRoute();
const router = useRouter();
const tabs: Array<{ key: TabKey; label: string; description: string }> = [
  { key: "review", label: "审核队列", description: "决定 Wiki 卡片与关联切块是否可参与问答" },
  { key: "quality", label: "知识质量", description: "引用覆盖、检索精度、证据完整性与知识库健康评分" },
  { key: "runtime", label: "运行状态", description: "API、数据库、向量库、全文检索与模型服务连通性" },
  { key: "indexes", label: "索引状态", description: "Chunk、Card、实体和值索引的同步概览" },
];

const activeTab = ref<TabKey>("review");
const loading = ref(false);
const error = ref<string | null>(null);

const reviewStatus = ref("review");
const reviewScope = ref<ReviewScope>("chunk");
const reviews = ref<ReviewInfo[]>([]);
const reviewStats = ref<ReviewStats | null>(null);
const reviewPage = ref(1);
const reviewPageSize = ref(20);
const reviewTotal = ref(0);
const activeReviewId = ref("");
const reviewDetailOpen = ref(false);
const selectedReviewIds = ref<string[]>([]);

const evalResults = ref<Record<string, EvalResult>>({});
const evalKinds = [
  { key: "health", label: "知识库健康评分" },
  { key: "citation", label: "引用覆盖率" },
  { key: "retrieval", label: "检索精度" },
  { key: "evidence", label: "证据完整性" },
  { key: "full", label: "综合评测" },
];

const health = ref<HealthStatus | null>(null);
const ping = ref<string>("");
const ingestStatus = ref<IngestStatus | null>(null);
const nl2sqlStatus = ref<NL2SQLStatus | null>(null);
const resetLoading = ref(false);
const resetResult = ref<KnowledgeResetResponse | null>(null);

const activeMeta = computed(() => tabs.find((tab) => tab.key === activeTab.value) || tabs[0]);
const reviewScopeTabs = [
  { key: "chunk" as ReviewScope, label: "切片审核", description: "优先审核原文切片；通过后进入 ES / Milvus，并可触发后续知识编译。" },
  { key: "wiki" as ReviewScope, label: "Wiki 卡片审核", description: "审核编译后的知识卡片；Wiki 只保存在 PostgreSQL。" },
];
const activeReviewScope = computed(() => reviewScopeTabs.find((item) => item.key === reviewScope.value) || reviewScopeTabs[0]);
const selectableReviews = computed(() => reviews.value.filter((item) => item.status !== "approved" && item.status !== "rejected"));
const selectedReviews = computed(() => reviews.value.filter((item) => selectedReviewIds.value.includes(item.review_id)));
const allVisibleSelected = computed(() => selectableReviews.value.length > 0 && selectableReviews.value.every((item) => selectedReviewIds.value.includes(item.review_id)));
const someVisibleSelected = computed(() => selectedReviewIds.value.length > 0 && !allVisibleSelected.value);
const reviewTotalPages = computed(() => Math.max(1, Math.ceil(reviewTotal.value / reviewPageSize.value)));
const reviewRangeStart = computed(() => (reviewTotal.value === 0 ? 0 : (reviewPage.value - 1) * reviewPageSize.value + 1));
const reviewRangeEnd = computed(() => Math.min(reviewTotal.value, reviewPage.value * reviewPageSize.value));
const runtimeCards = computed(() => {
  const services = health.value?.services || {};
  return [
    {
      key: "api",
      label: "接口连通性",
      value: ping.value || "未知",
      tone: ping.value === "正常" ? "blue" : "amber",
      detail: "用于确认前后端链路是否在线",
    },
    {
      key: "runtime",
      label: "运行状态",
      value: health.value?.status === "healthy" ? "健康" : health.value?.status === "degraded" ? "降级" : "未知",
      tone: health.value?.status === "healthy" ? "blue" : "amber",
      detail: `版本 ${health.value?.version || "-"}`,
    },
    {
      key: "wiki",
      label: "Wiki 真相源",
      value: serviceCountLabel(services.wiki_pg, "cards"),
      tone: serviceOk(services.wiki_pg) ? "slate" : "amber",
      detail: "PostgreSQL 中的 Wiki 卡片与审核记录",
    },
    {
      key: "vector",
      label: "向量索引",
      value: serviceCountLabel(services.milvus, "chunks"),
      tone: serviceOk(services.milvus) ? "slate" : "amber",
      detail: "仅索引已通过审核的原文切片",
    },
    {
      key: "search",
      label: "全文索引",
      value: serviceCountLabel(services.elasticsearch, "chunks"),
      tone: serviceOk(services.elasticsearch) ? "slate" : "amber",
      detail: "BM25 检索索引与实体索引",
    },
    {
      key: "model",
      label: "模型服务",
      value: serviceModelLabel(services.llm, services.embedding),
      tone: serviceOk(services.llm) && serviceOk(services.embedding) ? "slate" : "amber",
      detail: "问答模型与向量模型联通状态",
    },
  ];
});

const indexCards = computed(() => [
  {
    key: "milvus",
    title: "Milvus 原文切片",
    value: countLabel(ingestStatus.value?.milvus_chunks),
    status: ingestStatus.value?.milvus_chunks ? "已构建" : "空",
    tone: ingestStatus.value?.milvus_chunks ? "blue" : "slate",
    description: "仅保存通过审核的向量化切片",
  },
  {
    key: "es",
    title: "ES 原文切片",
    value: countLabel(ingestStatus.value?.elasticsearch_chunks),
    status: ingestStatus.value?.elasticsearch_chunks ? "已构建" : "空",
    tone: ingestStatus.value?.elasticsearch_chunks ? "blue" : "slate",
    description: "用于关键词召回与精确匹配",
  },
  {
    key: "tables",
    title: "表协议",
    value: seededCountLabel(nl2sqlStatus.value?.metadata?.nl2sql_table_info, nl2sqlStatus.value?.seeded),
    status: seededStateLabel(nl2sqlStatus.value?.seeded, nl2sqlStatus.value?.metadata?.nl2sql_table_info),
    tone: nl2sqlStatus.value?.seeded ? "slate" : "amber",
    description: "结构化知识的表级语义定义",
  },
  {
    key: "columns",
    title: "字段协议",
    value: seededCountLabel(nl2sqlStatus.value?.metadata?.nl2sql_column_info, nl2sqlStatus.value?.seeded),
    status: seededStateLabel(nl2sqlStatus.value?.seeded, nl2sqlStatus.value?.metadata?.nl2sql_column_info),
    tone: nl2sqlStatus.value?.seeded ? "slate" : "amber",
    description: "字段名、类型、口径说明",
  },
  {
    key: "metrics",
    title: "指标口径",
    value: seededCountLabel(nl2sqlStatus.value?.metadata?.nl2sql_metric_info, nl2sqlStatus.value?.seeded),
    status: seededStateLabel(nl2sqlStatus.value?.seeded, nl2sqlStatus.value?.metadata?.nl2sql_metric_info),
    tone: nl2sqlStatus.value?.seeded ? "slate" : "amber",
    description: "业务指标计算语义",
  },
  {
    key: "values",
    title: "值域索引",
    value: seededCountLabel(nl2sqlStatus.value?.metadata?.nl2sql_value_info, nl2sqlStatus.value?.seeded),
    status: seededStateLabel(nl2sqlStatus.value?.seeded, nl2sqlStatus.value?.metadata?.nl2sql_value_info),
    tone: nl2sqlStatus.value?.seeded ? "slate" : "amber",
    description: "可被结构化召回的值集合",
  },
]);

function normalizeTab(raw: unknown): TabKey {
  return tabs.some((tab) => tab.key === raw) ? (raw as TabKey) : "review";
}

function setTab(tab: TabKey) {
  activeTab.value = tab;
  router.replace({ path: "/governance", query: { tab } });
  void refreshTab(tab, false);
}

async function refreshReviews(force = false) {
  const [queue, stats] = reviewScope.value === "chunk"
    ? await Promise.all([listChunkReviews(reviewStatus.value, reviewPage.value, reviewPageSize.value), getChunkReviewStats(force)])
    : await Promise.all([listReviews(reviewStatus.value, reviewPage.value, reviewPageSize.value), getReviewStats(force)]);
  reviews.value = queue.reviews;
  reviewTotal.value = queue.total;
  reviewPage.value = queue.page;
  reviewPageSize.value = queue.page_size;
  reviewStats.value = stats;
  selectedReviewIds.value = selectedReviewIds.value.filter((id) => reviews.value.some((item) => item.review_id === id));
  if (!reviews.value.find((item) => item.review_id === activeReviewId.value)) {
    activeReviewId.value = reviews.value[0]?.review_id || "";
    reviewDetailOpen.value = false;
  }
}

function setReviewScope(scope: ReviewScope) {
  if (reviewScope.value === scope) return;
  reviewScope.value = scope;
  activeReviewId.value = "";
  selectedReviewIds.value = [];
  reviewPage.value = 1;
  reviewDetailOpen.value = false;
  void refreshReviews(true);
}

function onReviewStatusChange() {
  reviewPage.value = 1;
  selectedReviewIds.value = [];
  void refreshReviews(true);
}

function onReviewPageSizeChange() {
  reviewPage.value = 1;
  selectedReviewIds.value = [];
  void refreshReviews(true);
}

function setReviewPage(page: number) {
  const nextPage = Math.min(Math.max(1, page), reviewTotalPages.value);
  if (nextPage === reviewPage.value) return;
  reviewPage.value = nextPage;
  selectedReviewIds.value = [];
  reviewDetailOpen.value = false;
  void refreshReviews(true);
}

async function refreshRuntime() {
  const [healthResult, pingResult] = await Promise.allSettled([getHealth(), getPing()]);
  if (healthResult.status === "fulfilled") health.value = healthResult.value;
  else health.value = null;
  if (pingResult.status === "fulfilled") ping.value = pingResult.value.pong ? "正常" : pingResult.value.status || "未知";
  else ping.value = "unreachable";
}

async function refreshIndexes(force = false) {
  const [ingestResult, nl2sqlResult] = await Promise.allSettled([getIngestStatus(force), getNL2SQLStatus()]);
  ingestStatus.value = ingestResult.status === "fulfilled" ? ingestResult.value : null;
  nl2sqlStatus.value = nl2sqlResult.status === "fulfilled" ? nl2sqlResult.value : null;
}

function hasTabData(tab: TabKey) {
  if (tab === "review") return reviewStats.value !== null || reviews.value.length > 0;
  if (tab === "runtime") return health.value !== null || ping.value !== "";
  if (tab === "indexes") return ingestStatus.value !== null || nl2sqlStatus.value !== null;
  return true;
}

async function refreshTab(tab = activeTab.value, force = false) {
  if (!force && hasTabData(tab)) return;
  loading.value = true;
  error.value = null;
  try {
    if (tab === "review") await refreshReviews(force);
    if (tab === "runtime") await refreshRuntime();
    if (tab === "indexes") await refreshIndexes(force);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

async function runQuality(kind: string) {
  loading.value = true;
  error.value = null;
  try {
    evalResults.value[kind] = await runEval(kind as "health" | "citation" | "retrieval" | "evidence" | "full");
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

async function doApprove(review: ReviewInfo) {
  error.value = null;
  try {
    if (reviewScope.value === "chunk") {
      await approveChunkReview(review.chunk_id || review.review_id, "", "");
    } else {
      await approveReview(review.review_id, "", "");
    }
    await refreshReviewRelatedData();
    reviewDetailOpen.value = false;
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function doReject(review: ReviewInfo) {
  error.value = null;
  try {
    if (reviewScope.value === "chunk") {
      await rejectChunkReview(review.chunk_id || review.review_id, "", "");
    } else {
      await rejectReview(review.review_id, "", "");
    }
    await refreshReviewRelatedData();
    reviewDetailOpen.value = false;
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function doBatchApprove() {
  await doBatchReviewAction("approve");
}

async function doBatchReject() {
  await doBatchReviewAction("reject");
}

async function doBatchReviewAction(action: "approve" | "reject") {
  const targets = selectedReviews.value.filter((item) => item.status !== "approved" && item.status !== "rejected");
  if (!targets.length || loading.value) return;
  const label = action === "approve" ? "通过" : "驳回";
  const confirmed = window.confirm(`确认批量${label}当前选中的 ${targets.length} 条${reviewScope.value === "chunk" ? "切片" : "Wiki 卡片"}审核记录？`);
  if (!confirmed) return;

  loading.value = true;
  error.value = null;
  try {
    let result: Record<string, unknown>;
    if (reviewScope.value === "chunk") {
      const chunkIds = targets.map((review) => review.chunk_id || review.review_id);
      result = action === "approve"
        ? await approveChunkReviews(chunkIds, "", "")
        : await rejectChunkReviews(chunkIds, "", "");
    } else {
      const reviewIds = targets.map((review) => review.review_id);
      result = action === "approve"
        ? await approveReviews(reviewIds, "", "")
        : await rejectReviews(reviewIds, "", "");
    }
    selectedReviewIds.value = [];
    await refreshReviewRelatedData();
    reviewDetailOpen.value = false;
    if (Number(result.failed_count || 0) > 0) {
      const total = Number(result.total || targets.length);
      const failedCount = Number(result.failed_count || 0);
      error.value = `批量${label}已完成，但有 ${failedCount} / ${total} 条处理失败。`;
    }
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

async function refreshReviewRelatedData() {
  await Promise.allSettled([
    refreshReviews(true),
    refreshRuntime(),
    refreshIndexes(true),
  ]);
}

async function clearKnowledgeData() {
  if (resetLoading.value) return;
  const confirmed = window.confirm("确认清空当前知识库测试数据、向量索引、全文索引、对象存储和本地导出缓存？此操作不可撤销。");
  if (!confirmed) return;

  resetLoading.value = true;
  error.value = null;
  resetResult.value = null;
  try {
    resetResult.value = await resetKnowledgeStorage();
    await refreshIndexes(true);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    resetLoading.value = false;
  }
}

function resetStepLabel(step: KnowledgeResetResponse["steps"][number]) {
  return [step.layer, step.table, step.bucket, step.path].filter(Boolean).join(" / ");
}

function pct(value: number | undefined) {
  return `${(((value || 0) * 100)).toFixed(1)}%`;
}

function countLabel(value: number | undefined) {
  if (value === undefined || value === null) return "--";
  return String(value);
}

function reviewCountLabel(key: keyof ReviewStats) {
  return countLabel(reviewStats.value?.[key]);
}

function seededCountLabel(value: number | undefined, seeded: boolean | undefined) {
  if (!seeded) return "未初始化";
  return countLabel(value);
}

function seededStateLabel(seeded: boolean | undefined, value: number | undefined) {
  if (!seeded) return "未初始化";
  return (value || 0) > 0 ? "已构建" : "空";
}

function serviceOk(service: unknown) {
  return Boolean(service && typeof service === "object" && (service as Record<string, unknown>).ok);
}

function serviceCountLabel(service: unknown, key: string) {
  if (!service || typeof service !== "object") return "不可用";
  const row = service as Record<string, unknown>;
  if (!row.ok) return "异常";
  const value = row[key];
  return value === undefined ? "在线" : String(value);
}

function serviceModelLabel(llmService: unknown, embeddingService: unknown) {
  const llmModel = llmService && typeof llmService === "object" ? (llmService as Record<string, unknown>).model : null;
  const embeddingModel = embeddingService && typeof embeddingService === "object" ? (embeddingService as Record<string, unknown>).model : null;
  if (!llmModel && !embeddingModel) return "不可用";
  if (llmModel && embeddingModel) return "双模型在线";
  return "部分在线";
}

function resultTone(value: number | undefined) {
  const score = value || 0;
  if (score >= 0.8) return "text-blue-700 bg-blue-50 border-blue-200";
  if (score >= 0.6) return "text-amber-700 bg-amber-50 border-amber-200";
  return "text-rose-700 bg-rose-50 border-rose-200";
}

const activeReview = computed(() => reviews.value.find((item) => item.review_id === activeReviewId.value) || null);

function openReviewDetail(review: ReviewInfo) {
  activeReviewId.value = review.review_id;
  reviewDetailOpen.value = true;
}

function closeReviewDetail() {
  reviewDetailOpen.value = false;
}

function isReviewSelected(review: ReviewInfo) {
  return selectedReviewIds.value.includes(review.review_id);
}

function toggleReviewSelection(review: ReviewInfo) {
  const exists = selectedReviewIds.value.includes(review.review_id);
  selectedReviewIds.value = exists
    ? selectedReviewIds.value.filter((id) => id !== review.review_id)
    : [...selectedReviewIds.value, review.review_id];
}

function toggleSelectAllVisible() {
  if (allVisibleSelected.value) {
    const visibleIds = new Set(selectableReviews.value.map((item) => item.review_id));
    selectedReviewIds.value = selectedReviewIds.value.filter((id) => !visibleIds.has(id));
    return;
  }
  const next = new Set(selectedReviewIds.value);
  selectableReviews.value.forEach((item) => next.add(item.review_id));
  selectedReviewIds.value = Array.from(next);
}

function reviewKindLabel(review: ReviewInfo) {
  if (reviewScope.value === "chunk") return review.block_type || "原文切片";
  return reviewCardTypeLabel(review.card_type);
}

function reviewTitle(review: ReviewInfo) {
  if (reviewScope.value === "chunk") {
    return review.file_name || review.section_path || review.chunk_id || review.review_id;
  }
  return review.card_title || review.card_id;
}

function reviewContent(review: ReviewInfo) {
  return reviewScope.value === "chunk"
    ? review.content || review.card_content || ""
    : review.card_content || review.content || "";
}

function reviewPrimaryId(review: ReviewInfo) {
  return reviewScope.value === "chunk" ? review.chunk_id || review.review_id : review.card_id;
}

function reviewSourceMeta(review: ReviewInfo) {
  if (reviewScope.value === "chunk") {
    return [review.section_path, review.build_id, review.doc_id].filter(Boolean).join(" / ") || "暂无章节路径";
  }
  return review.source_ref || "暂无来源引用";
}

function reviewStatusLabel(status: string) {
  if (status === "approved") return "已通过";
  if (status === "rejected") return "已驳回";
  return "待审核";
}

function reviewStatusTone(status: string) {
  if (status === "approved") return "border-blue-200 bg-blue-50 text-blue-700";
  if (status === "rejected") return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function reviewCardTypeLabel(type: string | undefined) {
  if (type === "definition") return "定义";
  if (type === "concept") return "概念";
  if (type === "procedure") return "流程";
  if (type === "faq") return "问答";
  if (type === "fault") return "故障";
  return type || "未知";
}

function surfaceToneClass(tone: string) {
  if (tone === "blue") return "border-blue-200 bg-blue-50/70 text-blue-800";
  if (tone === "amber") return "border-amber-200 bg-amber-50/70 text-amber-800";
  return "border-slate-200 bg-slate-50 text-slate-800";
}

watch(
  () => route.query.tab,
  (tab) => {
    activeTab.value = normalizeTab(tab);
    void refreshTab(activeTab.value, false);
  },
);

onMounted(() => {
  activeTab.value = normalizeTab(route.query.tab);
  void refreshTab(activeTab.value, false);
});
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-4 px-6 py-3">
    <div class="flex justify-end">
      <button
        class="flex items-center space-x-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-900 active:scale-95 disabled:opacity-60"
        :disabled="loading"
        @click="refreshTab(activeTab, true)"
      >
        <AppIcon name="refresh-cw" class="h-4 w-4" />
        <span>{{ loading ? "刷新中" : "刷新数据" }}</span>
      </button>
    </div>

    <div>
      <div class="governance-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="governance-tab"
          :class="activeTab === tab.key ? 'is-active' : ''"
          @click="setTab(tab.key)"
        >
          <AppIcon v-if="tab.key === 'review'" name="shield-check" class="h-4 w-4" />
          <AppIcon v-else-if="tab.key === 'quality'" name="award" class="h-4 w-4" />
          <AppIcon v-else-if="tab.key === 'runtime'" name="activity" class="h-4 w-4" />
          <AppIcon v-else name="database" class="h-4 w-4" />
          <span>{{ tab.label }}</span>
        </button>
      </div>
    </div>

    <div v-if="error" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">
      {{ error }}
    </div>

    <template v-if="activeTab === 'review'">
      <div class="flex justify-end">
        <div class="review-scope-tabs">
          <button
            v-for="scope in reviewScopeTabs"
            :key="scope.key"
            class="review-scope-tab"
            :class="reviewScope === scope.key ? 'is-active' : ''"
            @click="setReviewScope(scope.key)"
          >
            {{ scope.label }}
          </button>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="space-y-1">
            <p class="text-sm font-medium text-slate-500">{{ reviewScope === "chunk" ? "切片总数" : "卡片总数" }}</p>
            <p class="text-3xl font-bold text-slate-900">{{ reviewCountLabel("total") }}</p>
          </div>
          <div class="rounded-lg p-3 text-slate-600">
            <AppIcon name="folder" class="h-6 w-6" />
          </div>
        </div>
        <div class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="space-y-1">
            <p class="text-sm font-medium text-amber-600">{{ reviewScope === "chunk" ? "待审核切片" : "待审核卡片" }}</p>
            <p class="text-3xl font-bold text-amber-600">{{ reviewCountLabel("pending_review") }}</p>
          </div>
          <div class="rounded-lg p-3 text-amber-600">
            <AppIcon name="clock" class="h-6 w-6" />
          </div>
        </div>
        <div class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="space-y-1">
            <p class="text-sm font-medium text-blue-700">{{ reviewScope === "chunk" ? "已通过切片" : "已通过卡片" }}</p>
            <p class="text-3xl font-bold text-blue-700">{{ reviewCountLabel("approved") }}</p>
          </div>
          <div class="rounded-lg p-3 text-blue-700">
            <AppIcon name="check-circle" class="h-6 w-6" />
          </div>
        </div>
        <div class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div class="space-y-1">
            <p class="text-sm font-medium text-rose-600">{{ reviewScope === "chunk" ? "已驳回切片" : "已驳回卡片" }}</p>
            <p class="text-3xl font-bold text-rose-600">{{ reviewCountLabel("rejected") }}</p>
          </div>
          <div class="rounded-lg p-3 text-rose-600">
            <AppIcon name="x-circle" class="h-6 w-6" />
          </div>
        </div>
      </div>

      <div class="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div class="flex flex-col gap-3 border-b border-slate-200 p-4 xl:flex-row xl:items-center xl:justify-between">
          <div class="flex flex-wrap items-center gap-3">
            <span class="text-sm text-slate-500">状态筛选:</span>
            <select v-model="reviewStatus" class="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-sm text-slate-700" @change="onReviewStatusChange">
              <option value="review">待审核</option>
              <option value="approved">已通过</option>
              <option value="rejected">已驳回</option>
            </select>
            <span class="text-sm text-slate-500">每页:</span>
            <select v-model.number="reviewPageSize" class="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-sm text-slate-700" @change="onReviewPageSizeChange">
              <option :value="10">10</option>
              <option :value="20">20</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
            </select>
            <label class="inline-flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700">
              <input
                type="checkbox"
                class="h-4 w-4 rounded border-slate-300"
                :checked="allVisibleSelected"
                :indeterminate.prop="someVisibleSelected"
                :disabled="selectableReviews.length === 0"
                @change="toggleSelectAllVisible"
              />
              全选当前页
            </label>
            <span v-if="selectedReviewIds.length" class="text-xs font-medium text-blue-700">已选 {{ selectedReviewIds.length }} 条</span>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <template v-if="selectedReviewIds.length">
              <button
                class="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="loading"
                @click="doBatchApprove"
              >
                <AppIcon name="check2" class="h-4 w-4" />
                批量通过
              </button>
              <button
                class="inline-flex items-center gap-1.5 rounded-md bg-red-500 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-50"
                :disabled="loading"
                @click="doBatchReject"
              >
                <AppIcon name="x" class="h-4 w-4" />
                批量驳回
              </button>
            </template>
          </div>
        </div>

        <div v-if="!loading && reviews.length === 0" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="mb-4 flex h-16 w-16 items-center justify-center rounded-full border border-dashed border-slate-300 bg-slate-100 text-slate-400">
            <AppIcon name="inbox" class="h-7 w-7" />
          </div>
          <h3 class="text-base font-semibold text-slate-800">当前队列为空</h3>
          <p class="mt-1 max-w-md text-xs text-slate-400">没有符合当前筛选状态的审核记录，当有新的待处理知识提交时会显示在此处。</p>
        </div>

        <div v-if="!loading && reviews.length > 0" class="divide-y divide-slate-100">
          <article
            v-for="review in reviews"
            :key="review.review_id"
            class="review-row"
            :class="isReviewSelected(review) ? 'is-selected' : ''"
            @click="openReviewDetail(review)"
          >
            <div class="pt-1">
              <input
                type="checkbox"
                class="h-4 w-4 rounded border-slate-300"
                :checked="isReviewSelected(review)"
                @click.stop
                @change="toggleReviewSelection(review)"
              />
            </div>
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700">{{ reviewKindLabel(review) }}</span>
                <span class="rounded-lg border px-2.5 py-1 text-xs font-medium" :class="reviewStatusTone(review.status)">{{ reviewStatusLabel(review.status) }}</span>
                <span class="text-xs text-slate-400">{{ review.created_at }}</span>
              </div>
              <h3 class="mt-2 truncate text-base font-semibold text-slate-900">{{ reviewTitle(review) }}</h3>
              <p class="mt-2 review-line-clamp text-sm leading-6 text-slate-600">{{ reviewContent(review) || "暂无正文，点击查看审核记录详情。" }}</p>
              <div class="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                <span class="font-mono">{{ reviewScope === "chunk" ? "切片" : "卡片" }}：{{ reviewPrimaryId(review) }}</span>
                <span class="font-mono">审核单：{{ review.review_id }}</span>
                <span v-if="reviewScope === 'wiki'">关联切片 {{ (review.linked_chunks || []).length }} 个</span>
                <span class="max-w-[360px] truncate">来源：{{ reviewSourceMeta(review) }}</span>
              </div>
            </div>

            <div class="flex items-center justify-start gap-2 xl:justify-end">
              <button
                class="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"
                @click.stop="openReviewDetail(review)"
              >
                <AppIcon name="file-search" class="h-4 w-4" />
                查看详情
              </button>
              <button
                class="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-45"
                :disabled="loading || review.status === 'approved'"
                @click.stop="doApprove(review)"
              >
                <AppIcon name="check2" class="h-4 w-4" />
                通过
              </button>
              <button
                class="inline-flex items-center gap-1.5 rounded-md bg-red-500 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-45"
                :disabled="loading || review.status === 'rejected'"
                @click.stop="doReject(review)"
              >
                <AppIcon name="x" class="h-4 w-4" />
                驳回
              </button>
            </div>
          </article>
        </div>

        <div v-if="!loading && reviewTotal > 0" class="flex flex-col gap-3 border-t border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600 md:flex-row md:items-center md:justify-between">
          <div>
            显示 {{ reviewRangeStart }}-{{ reviewRangeEnd }} / 共 {{ reviewTotal }} 条
            <span v-if="selectedReviewIds.length" class="ml-2 font-medium text-blue-700">当前页已选 {{ selectedReviewIds.length }} 条</span>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="rounded-md border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-45"
              :disabled="loading || reviewPage <= 1"
              @click="setReviewPage(reviewPage - 1)"
            >
              上一页
            </button>
            <span class="rounded-md border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700">
              第 {{ reviewPage }} / {{ reviewTotalPages }} 页
            </span>
            <button
              class="rounded-md border border-slate-200 bg-white px-3 py-1.5 font-medium text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-45"
              :disabled="loading || reviewPage >= reviewTotalPages"
              @click="setReviewPage(reviewPage + 1)"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </template>

    <div v-if="activeTab === 'quality'" class="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="grid gap-3 sm:grid-cols-5">
        <button
          v-for="kind in evalKinds"
          :key="kind.key"
          class="rounded-lg border border-slate-200 bg-white p-2.5 text-left hover:border-blue-400 hover:bg-blue-50/30 transition-colors"
          :disabled="loading"
          @click="runQuality(kind.key)"
        >
          <div class="text-xs font-medium text-slate-800">{{ kind.label }}</div>
          <div class="mt-1 text-[11px] font-medium text-blue-800">运行评测</div>
        </button>
      </div>
      <div v-if="Object.keys(evalResults).length === 0" class="rounded-lg border border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-700">
        暂无知识质量结果，点击上方按钮运行评测。
      </div>
      <div class="space-y-3">
        <div v-for="kind in evalKinds" :key="kind.key" v-show="evalResults[kind.key]" class="rounded-lg border border-slate-200 p-4">
          <div class="mb-3 text-sm font-semibold text-slate-800">{{ kind.label }}</div>
          <div v-if="evalResults[kind.key]?.query_source || evalResults[kind.key]?.queries?.length" class="mb-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600">
            <span v-if="evalResults[kind.key]?.query_source === 'corpus'">本次使用当前知识库语料自动生成的冒烟问题。</span>
            <span v-else-if="evalResults[kind.key]?.query_source === 'fallback'">当前语料不足，本次退回到了内置测试问题。</span>
            <template v-if="evalResults[kind.key]?.queries?.length">
              <span class="ml-2 text-slate-500">问题集：{{ evalResults[kind.key]?.queries?.join("；") }}</span>
            </template>
          </div>
          <div class="grid gap-3 sm:grid-cols-4">
            <div class="rounded-lg border p-3" :class="resultTone(evalResults[kind.key]?.health_score)">
              <div class="text-xs font-medium">健康评分</div>
              <div class="mt-1 text-lg font-semibold">{{ pct(evalResults[kind.key]?.health_score) }}</div>
            </div>
            <div class="rounded-lg border p-3" :class="resultTone(evalResults[kind.key]?.citation_coverage)">
              <div class="text-xs font-medium">引用覆盖率</div>
              <div class="mt-1 text-lg font-semibold">{{ pct(evalResults[kind.key]?.citation_coverage) }}</div>
            </div>
            <div class="rounded-lg border p-3" :class="resultTone(evalResults[kind.key]?.retrieval_precision)">
              <div class="text-xs font-medium">检索精度</div>
              <div class="mt-1 text-lg font-semibold">{{ pct(evalResults[kind.key]?.retrieval_precision) }}</div>
            </div>
            <div class="rounded-lg border p-3" :class="resultTone(evalResults[kind.key]?.evidence_completeness)">
              <div class="text-xs font-medium">证据完整性</div>
              <div class="mt-1 text-lg font-semibold">{{ pct(evalResults[kind.key]?.evidence_completeness) }}</div>
            </div>
          </div>
          <div v-if="evalResults[kind.key]?.errors?.length" class="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
            {{ evalResults[kind.key]?.errors?.join("；") }}
          </div>
          <pre v-if="evalResults[kind.key]?.report" class="mt-3 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs leading-6 text-slate-200">{{ evalResults[kind.key].report }}</pre>
        </div>
      </div>
      <div class="mt-4">
        <RetrievalEvalPanel />
      </div>
    </div>

    <div v-if="activeTab === 'runtime'" class="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="card in runtimeCards"
          :key="card.key"
          class="rounded-xl border p-4"
          :class="surfaceToneClass(card.tone)"
        >
          <div class="text-xs font-medium">{{ card.label }}</div>
          <div class="mt-2 text-xl font-semibold">{{ card.value }}</div>
          <div class="mt-2 text-xs leading-5 opacity-80">{{ card.detail }}</div>
        </div>
      </div>
      <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <div class="text-sm font-semibold text-slate-800">服务明细</div>
        <div class="mt-3 grid gap-3 md:grid-cols-2">
          <div
            v-for="(value, key) in health?.services || {}"
            :key="key"
            class="rounded-lg border border-slate-200 bg-white px-4 py-3"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="text-xs font-medium text-slate-600">{{ key }}</div>
              <span
                class="rounded-full px-2 py-0.5 text-[10px] font-medium"
                :class="serviceOk(value) ? 'bg-blue-50 text-blue-700' : 'bg-amber-50 text-amber-700'"
              >
                {{ serviceOk(value) ? "在线" : "异常" }}
              </span>
            </div>
            <pre class="mt-2 overflow-x-auto whitespace-pre-wrap text-xs leading-6 text-slate-700">{{ JSON.stringify(value, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>

    <div v-if="activeTab === 'indexes'" class="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div class="flex flex-col gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 sm:flex-row sm:items-center sm:justify-between">
        <div class="min-w-0">
          <div class="flex items-center gap-2 text-sm font-semibold text-rose-800">
            <AppIcon name="trash" class="h-4 w-4" />
            清空知识库测试数据
          </div>
          <p class="mt-1 text-xs font-medium text-rose-700">
            清理 PostgreSQL、Milvus、Elasticsearch、MinIO 与本地 wiki_output 缓存，适合重新导入测试语料前使用。
          </p>
        </div>
        <button
          class="inline-flex items-center justify-center gap-2 rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-all hover:bg-rose-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="loading || resetLoading"
          @click="clearKnowledgeData"
        >
          <AppIcon name="trash" class="h-4 w-4" />
          <span>{{ resetLoading ? "清空中" : "清空数据" }}</span>
        </button>
      </div>

      <div
        v-if="resetResult"
        class="rounded-lg border p-4 text-sm"
        :class="resetResult.ok ? 'border-blue-200 bg-blue-50 text-blue-800' : 'border-amber-200 bg-amber-50 text-amber-800'"
      >
        <div class="font-semibold">
          {{ resetResult.ok ? "清库完成" : "清库完成但存在失败步骤" }}：共执行 {{ resetResult.steps.length }} 步
        </div>
        <div class="mt-3 grid gap-2 md:grid-cols-2">
          <div
            v-for="(step, index) in resetResult.steps"
            :key="`${step.layer}-${index}`"
            class="rounded-md border bg-white/70 px-3 py-2 text-xs"
            :class="step.ok ? 'border-blue-100 text-blue-800' : 'border-amber-200 text-amber-800'"
          >
            <div class="flex items-center justify-between gap-3">
              <span class="truncate font-medium">{{ resetStepLabel(step) }}</span>
              <span class="shrink-0 font-semibold">{{ step.ok ? "完成" : "失败" }}</span>
            </div>
            <div v-if="step.error" class="mt-1 break-words text-amber-700">{{ step.error }}</div>
          </div>
        </div>
      </div>

      <div class="grid gap-4">
        <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
          <div class="text-sm font-semibold text-slate-800">索引构建概览</div>
          <div class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <div
              v-for="card in indexCards"
              :key="card.key"
              class="rounded-xl border bg-white p-4"
              :class="surfaceToneClass(card.tone)"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="text-xs font-medium">{{ card.title }}</div>
                  <div class="mt-3 text-2xl font-semibold leading-none">{{ card.value }}</div>
                </div>
                <span class="rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-medium text-current">{{ card.status }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="nl2sqlStatus?.warnings?.length" class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {{ nl2sqlStatus.warnings.join("；") }}
        </div>
      </div>
    </div>

    <teleport to="body">
      <div v-if="reviewDetailOpen && activeReview" class="review-modal-backdrop" @click.self="closeReviewDetail">
        <section class="review-modal-panel">
          <header class="review-modal-header">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700">{{ reviewKindLabel(activeReview) }}</span>
                <span class="rounded-lg border px-2.5 py-1 text-xs font-medium" :class="reviewStatusTone(activeReview.status)">{{ reviewStatusLabel(activeReview.status) }}</span>
              </div>
              <h2 class="mt-2 truncate text-lg font-semibold text-slate-900">{{ reviewTitle(activeReview) }}</h2>
              <div class="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-500">
                <span>{{ reviewScope === "chunk" ? "切片 ID" : "卡片 ID" }}：{{ reviewPrimaryId(activeReview) }}</span>
                <span>审核单：{{ activeReview.review_id }}</span>
                <span>创建时间：{{ activeReview.created_at }}</span>
              </div>
            </div>
            <button
              class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-900"
              aria-label="关闭审核详情"
              @click="closeReviewDetail"
            >
              <AppIcon name="x" class="h-4 w-4" />
            </button>
          </header>

          <div class="review-modal-body">
            <div class="review-detail-grid">
              <div class="rounded-xl border border-slate-200 bg-white p-4">
                <div class="text-xs font-medium text-slate-500">{{ reviewScope === "chunk" ? "原文切片" : "卡片正文" }}</div>
                <div class="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-800">{{ reviewContent(activeReview) || "暂无正文内容" }}</div>
              </div>

              <div class="space-y-4">
                <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div class="text-xs font-medium text-slate-500">{{ reviewScope === "chunk" ? "切片来源" : "来源与置信度" }}</div>
                  <div class="mt-3 space-y-3 text-sm text-slate-700">
                    <template v-if="reviewScope === 'chunk'">
                      <div>
                        <div class="text-[11px] text-slate-500">文件名</div>
                        <div class="mt-1 break-all">{{ activeReview.file_name || "暂无" }}</div>
                      </div>
                      <div>
                        <div class="text-[11px] text-slate-500">章节路径</div>
                        <div class="mt-1 break-all">{{ activeReview.section_path || "暂无" }}</div>
                      </div>
                      <div>
                        <div class="text-[11px] text-slate-500">构建 / 文档</div>
                        <div class="mt-1 break-all">{{ [activeReview.build_id, activeReview.doc_id].filter(Boolean).join(" / ") || "暂无" }}</div>
                      </div>
                    </template>
                    <template v-else>
                    <div>
                      <div class="text-[11px] text-slate-500">来源引用</div>
                      <div class="mt-1 break-all">{{ activeReview.source_ref || "暂无" }}</div>
                    </div>
                    <div>
                      <div class="text-[11px] text-slate-500">置信度</div>
                      <div class="mt-1">{{ (((activeReview.confidence || 0) * 100)).toFixed(0) }}%</div>
                    </div>
                    </template>
                  </div>
                </div>

                <div v-if="reviewScope === 'wiki'" class="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div class="flex items-center justify-between gap-3">
                    <div class="text-xs font-medium text-slate-500">关联切片</div>
                    <span class="text-[11px] text-slate-500">{{ (activeReview.linked_chunks || []).length }} 个</span>
                  </div>
                  <div class="mt-3 flex max-h-48 flex-wrap gap-2 overflow-y-auto">
                    <span
                      v-for="chunkId in activeReview.linked_chunks || []"
                      :key="chunkId"
                      class="rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-mono text-slate-700"
                    >
                      {{ chunkId }}
                    </span>
                    <span v-if="!(activeReview.linked_chunks || []).length" class="text-sm text-slate-500">暂无关联切片</span>
                  </div>
                </div>

                <div v-if="activeReview.notes" class="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <div class="text-xs font-medium text-amber-700">审核备注</div>
                  <div class="mt-2 text-sm leading-6 text-amber-900">{{ activeReview.notes }}</div>
                </div>
              </div>
            </div>
          </div>

          <footer class="review-modal-footer">
            <div class="flex gap-2">
              <button
                class="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-45"
                :disabled="loading || activeReview.status === 'approved'"
                @click="doApprove(activeReview)"
              >
                <AppIcon name="check2" class="h-4 w-4" />
                通过
              </button>
              <button
                class="inline-flex items-center gap-1.5 rounded-md bg-red-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-600 disabled:cursor-not-allowed disabled:opacity-45"
                :disabled="loading || activeReview.status === 'rejected'"
                @click="doReject(activeReview)"
              >
                <AppIcon name="x" class="h-4 w-4" />
                驳回
              </button>
            </div>
          </footer>
        </section>
      </div>
    </teleport>
  </div>
</template>

<style scoped>
.governance-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 0.75rem;
}

.governance-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.75rem;
  background: #ffffff;
  color: #64748b;
  padding: 0.625rem 0.875rem;
  font-size: 0.875rem;
  font-weight: 500;
  transition: color 0.16s ease, border-color 0.16s ease, background-color 0.16s ease;
}

.governance-tab:hover {
  border-color: #cbd5e1;
  color: #0f172a;
  background: #f8fafc;
}

.governance-tab.is-active {
  border-color: #818cf8;
  background: #eef2ff;
  color: #4338ca;
  font-weight: 600;
}

.review-scope-tabs {
  display: inline-flex;
  gap: 0.25rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  background: #f8fafc;
  padding: 0.1875rem;
}

.review-scope-tab {
  height: 1.875rem;
  border: 1px solid transparent;
  border-radius: 0.375rem;
  background: transparent;
  padding: 0 0.75rem;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1;
  transition: background-color 0.16s ease, border-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.review-scope-tab:hover {
  background: #ffffff;
  color: #0f172a;
}

.review-scope-tab.is-active {
  border-color: #e2e8f0;
  background: #ffffff;
  color: #1d4ed8;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

.review-line-clamp {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.review-row {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  gap: 16px;
  padding: 16px 20px;
  cursor: pointer;
  transition: background-color 0.16s ease;
}

.review-row:hover {
  background: #f8fafc;
}

.review-row.is-selected {
  background: #eff6ff;
}

.review-modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.48);
}

.review-modal-panel {
  display: flex;
  flex-direction: column;
  width: min(1080px, 100%);
  max-height: 88vh;
  overflow: hidden;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.28);
}

.review-modal-header,
.review-modal-footer {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  border-bottom: 1px solid #e2e8f0;
  background: #ffffff;
}

.review-modal-footer {
  align-items: center;
  flex-wrap: wrap;
  border-top: 1px solid #e2e8f0;
  border-bottom: 0;
  background: #f8fafc;
}

.review-modal-body {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.review-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) 320px;
  gap: 16px;
}

@media (max-width: 1024px) {
  .review-row {
    grid-template-columns: 24px minmax(0, 1fr);
  }

  .review-row > :last-child {
    grid-column: 2;
    justify-content: flex-start;
  }

  .review-detail-grid {
    grid-template-columns: 1fr;
  }
}
</style>
