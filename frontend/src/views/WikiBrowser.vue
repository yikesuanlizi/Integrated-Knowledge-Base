<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listWikiCards, searchWikiFulltext, getKnowledgeOverview, getIndexStatus, listDocuments, listChunks, listEntities } from "@/api/client";
import type { WikiCardInfo, KnowledgeOverview, IndexStatus, DocumentItem, ChunkItem, EntityItem } from "@/types";
import AppIcon from "@/components/AppIcon.vue";

const router = useRouter();
const route = useRoute();

type TabKey = "overview" | "documents" | "chunks" | "cards" | "entities" | "indexes";

const currentTab = ref<TabKey>((route.query.tab as TabKey) || "overview");

const tabs = [
  { key: "overview" as TabKey, label: "总览", icon: "bar-chart-3" },
  { key: "documents" as TabKey, label: "文档", icon: "file-text" },
  { key: "chunks" as TabKey, label: "原文切块", icon: "file-text" },
  { key: "cards" as TabKey, label: "Wiki 卡片", icon: "layers" },
  { key: "entities" as TabKey, label: "实体", icon: "network" },
  { key: "indexes" as TabKey, label: "索引状态", icon: "database" },
];

function overviewValue(value: number | undefined) {
  return value === undefined || value === null ? "--" : value;
}

const overviewMetricCards = computed(() => [
  { label: "文档", value: overviewValue(overview.value?.documents), icon: "file-text", tone: "slate" },
  { label: "原文切块", value: overviewValue(overview.value?.chunks), icon: "file-text", tone: "slate" },
  { label: "Wiki 卡片", value: overviewValue(overview.value?.wiki_cards), icon: "layers", tone: "slate" },
  { label: "实体", value: overviewValue(overview.value?.entities), icon: "network", tone: "slate" },
]);

const overviewReviewCards = computed(() => [
  { label: "待复核卡片", value: overviewValue(overview.value?.reviews?.pending), icon: "clock", tone: "amber" },
  { label: "已通过卡片", value: overviewValue(overview.value?.reviews?.approved), icon: "check-circle", tone: "blue" },
  { label: "已驳回", value: overviewValue(overview.value?.reviews?.rejected), icon: "x-circle", tone: "rose" },
  { label: "可问答切片", value: overviewValue(overview.value?.qa_ready?.approved_chunks), icon: "sparkles", tone: "indigo" },
]);

function overviewCardTone(tone: string) {
  if (tone === "amber") return "border-amber-200/80 bg-amber-50/60 text-amber-700";
  if (tone === "blue") return "border-blue-200/80 bg-blue-50/60 text-blue-700";
  if (tone === "rose") return "border-rose-200/80 bg-rose-50/60 text-rose-700";
  if (tone === "indigo") return "border-indigo-200/80 bg-indigo-50/60 text-indigo-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

function switchTab(tab: TabKey) {
  currentTab.value = tab;
  router.replace({ path: "/wiki", query: { tab } });
}

watch(
  () => route.query.tab,
  (v) => {
    if (v && tabs.find((t) => t.key === v)) {
      currentTab.value = v as TabKey;
    }
  },
);

// ================ Cards Tab 状态 ================
const cards = ref<WikiCardInfo[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const keyword = ref("");
const statusFilter = ref("approved");
const loading = ref(false);
const error = ref<string | null>(null);

function statusColor(status: string): string {
  if (status === "approved") return "bg-blue-50 text-blue-700 border-blue-200";
  if (status === "review") return "bg-amber-50 text-amber-700 border-amber-200";
  if (status === "rejected") return "bg-rose-50 text-rose-700 border-rose-200";
  if (status === "draft") return "bg-slate-50 text-slate-600 border-slate-200";
  return "bg-slate-50 text-slate-600 border-slate-200";
}

function statusLabel(status: string): string {
  if (status === "approved") return "已审核";
  if (status === "review") return "待审核";
  if (status === "rejected") return "已驳回";
  if (status === "draft") return "草稿";
  return status;
}

function cardTypeLabel(cardType: string): string {
  if (cardType === "definition") return "定义";
  if (cardType === "concept") return "概念";
  if (cardType === "procedure") return "流程";
  if (cardType === "faq") return "问答";
  if (cardType === "fault") return "故障";
  return cardType;
}

async function doSearch() {
  if (!keyword.value.trim()) return doList();
  loading.value = true;
  error.value = null;
  try {
    cards.value = await searchWikiFulltext(keyword.value, 30, statusFilter.value);
    total.value = cards.value.length;
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

async function doList() {
  loading.value = true;
  error.value = null;
  try {
    const r = await listWikiCards(page.value, pageSize, undefined, statusFilter.value || undefined);
    cards.value = r.cards;
    total.value = r.total;
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

function openCard(card: WikiCardInfo) {
  router.push({ path: `/wiki/${card.card_id}`, query: { from: "wiki", tab: currentTab.value } });
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

function nextPage() {
  if (page.value < totalPages.value) { page.value++; doList(); }
}
function prevPage() {
  if (page.value > 1) { page.value--; doList(); }
}

// ================ Documents Tab 状态 ================
const documents = ref<DocumentItem[]>([]);
const docTotal = ref(0);
const docPage = ref(1);
const docKeyword = ref("");
const docLoading = ref(false);
const docError = ref<string | null>(null);

async function loadDocuments() {
  docLoading.value = true;
  docError.value = null;
  try {
    const r = await listDocuments(docKeyword.value, docPage.value, 20);
    documents.value = r.documents;
    docTotal.value = r.total;
  } catch (e) {
    docError.value = (e as Error).message;
  } finally {
    docLoading.value = false;
  }
}

function docNextPage() { if (docPage.value < Math.ceil(docTotal.value / 20)) { docPage.value++; loadDocuments(); } }
function docPrevPage() { if (docPage.value > 1) { docPage.value--; loadDocuments(); } }

// ================ Chunks Tab 状态 ================
const chunks = ref<ChunkItem[]>([]);
const chunkTotal = ref(0);
const chunkPage = ref(1);
const chunkKeyword = ref("");
const chunkStatus = ref("");
const chunkLoading = ref(false);
const chunkError = ref<string | null>(null);

async function loadChunks() {
  chunkLoading.value = true;
  chunkError.value = null;
  try {
    const r = await listChunks(chunkKeyword.value, chunkStatus.value, chunkPage.value, 20);
    chunks.value = r.chunks;
    chunkTotal.value = r.total;
  } catch (e) {
    chunkError.value = (e as Error).message;
  } finally {
    chunkLoading.value = false;
  }
}

function chunkNextPage() { if (chunkPage.value < Math.ceil(chunkTotal.value / 20)) { chunkPage.value++; loadChunks(); } }
function chunkPrevPage() { if (chunkPage.value > 1) { chunkPage.value--; loadChunks(); } }

// ================ Entities Tab 状态 ================
const entities = ref<EntityItem[]>([]);
const entityTotal = ref(0);
const entityPage = ref(1);
const entityKeyword = ref("");
const entityTypeFilter = ref("");
const entityLoading = ref(false);
const entityError = ref<string | null>(null);

const entityTypes = [
  { value: "", label: "全部类型" },
  { value: "component", label: "组件" },
  { value: "part_number", label: "件号" },
  { value: "symptom", label: "故障现象" },
  { value: "procedure", label: "维护程序" },
  { value: "standard", label: "技术标准" },
  { value: "document", label: "手册文档" },
];

async function loadEntities() {
  entityLoading.value = true;
  entityError.value = null;
  try {
    const r = await listEntities(entityKeyword.value, entityTypeFilter.value, entityPage.value, 20);
    entities.value = r.entities;
    entityTotal.value = r.total;
  } catch (e) {
    entityError.value = (e as Error).message;
  } finally {
    entityLoading.value = false;
  }
}

function entityNextPage() { if (entityPage.value < Math.ceil(entityTotal.value / 20)) { entityPage.value++; loadEntities(); } }
function entityPrevPage() { if (entityPage.value > 1) { entityPage.value--; loadEntities(); } }

// ================ Overview Tab 状态 ================
const overview = ref<KnowledgeOverview | null>(null);
const overviewLoading = ref(false);
const overviewError = ref<string | null>(null);

async function loadOverview(force = false) {
  overviewLoading.value = true;
  overviewError.value = null;
  try {
    overview.value = await getKnowledgeOverview(force);
  } catch (e) {
    overviewError.value = (e as Error).message;
  } finally {
    overviewLoading.value = false;
  }
}

// ================ Indexes Tab 状态 ================
const indexStatus = ref<IndexStatus | null>(null);
const indexLoading = ref(false);
const indexError = ref<string | null>(null);

async function loadIndexStatus(force = false) {
  indexLoading.value = true;
  indexError.value = null;
  try {
    indexStatus.value = await getIndexStatus(force);
  } catch (e) {
    indexError.value = (e as Error).message;
  } finally {
    indexLoading.value = false;
  }
}

// 通用刷新所有数据
function refreshAll() {
  loadOverview(true);
  loadDocuments();
  loadChunks();
  loadEntities();
  loadIndexStatus(true);
  doList();
}

watch(currentTab, (tab) => {
  if (tab === "overview" && !overview.value) loadOverview();
  if (tab === "indexes" && !indexStatus.value) loadIndexStatus();
  if (tab === "cards" && cards.value.length === 0 && !loading.value) doList();
  if (tab === "documents" && documents.value.length === 0 && !docLoading.value) loadDocuments();
  if (tab === "chunks" && chunks.value.length === 0 && !chunkLoading.value) loadChunks();
  if (tab === "entities" && entities.value.length === 0 && !entityLoading.value) loadEntities();
});

onMounted(() => {
  if (currentTab.value === "overview") loadOverview();
  else if (currentTab.value === "indexes") loadIndexStatus();
  else if (currentTab.value === "cards") doList();
  else if (currentTab.value === "documents") loadDocuments();
  else if (currentTab.value === "chunks") loadChunks();
  else if (currentTab.value === "entities") loadEntities();
});
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-4 px-6 py-3">
    <div class="flex justify-end">
      <button @click="refreshAll" class="flex items-center space-x-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-900 active:scale-95">
        <AppIcon name="refresh-cw" class="w-4 h-4" />
        <span>刷新数据</span>
      </button>
    </div>

    <!-- Tab 切换 -->
    <div class="wiki-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        @click="switchTab(tab.key)"
        class="wiki-tab"
        :class="currentTab === tab.key ? 'is-active' : ''"
      >
        <AppIcon :name="tab.icon" class="w-4 h-4" />
        <span>{{ tab.label }}</span>
      </button>
    </div>

    <!-- ============ Overview Tab ============ -->
    <div v-if="currentTab === 'overview'" class="pt-1">
      <div v-if="overviewError" class="mb-3 bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">{{ overviewError }}</div>
      <div class="space-y-6">
        <!-- 核心资产统计 -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div
            v-for="card in overviewMetricCards"
            :key="card.label"
            class="min-h-[108px] rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm sm:px-5"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <p class="text-xs font-medium tracking-wide text-slate-500">{{ card.label }}</p>
                <p class="mt-5 text-[2rem] font-semibold leading-none text-slate-900">{{ card.value }}</p>
              </div>
              <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-slate-600">
                <AppIcon :name="card.icon" class="h-4.5 w-4.5" />
              </div>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div
            v-for="card in overviewReviewCards"
            :key="card.label"
            class="min-h-[108px] rounded-xl border bg-white px-4 py-4 shadow-sm sm:px-5"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="min-w-0">
                <p class="text-xs font-medium tracking-wide" :class="overviewCardTone(card.tone).split(' ').slice(-1)[0]">{{ card.label }}</p>
                <p class="mt-5 text-[2rem] font-semibold leading-none" :class="overviewCardTone(card.tone).split(' ').slice(-1)[0]">{{ card.value }}</p>
              </div>
              <div
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border"
                :class="overviewCardTone(card.tone)"
              >
                <AppIcon :name="card.icon" class="h-4.5 w-4.5" />
              </div>
            </div>
          </div>
        </div>

        <!-- 索引同步 -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-slate-800">索引同步</h3>
            <span class="text-xs text-slate-500">仅已通过切片进入检索索引</span>
          </div>
          <div class="p-5 grid grid-cols-1 md:grid-cols-3 gap-4">
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">Milvus 原文切片</div>
              <div class="text-2xl font-bold text-slate-800">{{ overviewValue(overview?.indexes?.milvus_chunks) }}</div>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">ES 原文切片</div>
              <div class="text-2xl font-bold text-slate-800">{{ overviewValue(overview?.indexes?.es_chunks) }}</div>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">ES 实体索引</div>
              <div class="text-2xl font-bold text-slate-800">{{ overviewValue(overview?.indexes?.es_entities) }}</div>
            </div>
          </div>
        </div>

        <!-- 知识流向 -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 bg-slate-50/70 border-b border-slate-200">
            <h3 class="text-sm font-semibold text-slate-800">知识流向</h3>
          </div>
          <div class="p-6 flex items-center justify-between gap-2 overflow-x-auto">
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-slate-600 flex items-center justify-center mb-2">
                <AppIcon name="file-text" class="w-6 h-6" />
              </div>
              <div class="text-xs text-slate-500">原始文档</div>
              <div class="text-base font-bold text-slate-800">{{ overviewValue(overview?.documents) }}</div>
            </div>
            <AppIcon name="chevron-right" class="w-5 h-5 text-slate-300 flex-shrink-0" />
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-slate-600 flex items-center justify-center mb-2">
                <AppIcon name="file-text" class="w-6 h-6" />
              </div>
              <div class="text-xs text-slate-500">原文切块</div>
              <div class="text-base font-bold text-slate-800">{{ overviewValue(overview?.chunks) }}</div>
            </div>
            <AppIcon name="chevron-right" class="w-5 h-5 text-slate-300 flex-shrink-0" />
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-slate-600 flex items-center justify-center mb-2">
                <AppIcon name="layers" class="w-6 h-6" />
              </div>
              <div class="text-xs text-slate-500">Wiki 卡片</div>
              <div class="text-base font-bold text-slate-800">{{ overviewValue(overview?.wiki_cards) }}</div>
            </div>
            <AppIcon name="chevron-right" class="w-5 h-5 text-slate-300 flex-shrink-0" />
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-amber-600 flex items-center justify-center mb-2">
                <AppIcon name="check-circle" class="w-6 h-6" />
              </div>
              <div class="text-xs text-slate-500">Wiki 审核</div>
              <div class="text-base font-bold text-slate-800">{{ overviewValue(overview?.reviews?.approved) }} 张已通过</div>
            </div>
            <AppIcon name="chevron-right" class="w-5 h-5 text-slate-300 flex-shrink-0" />
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-indigo-600 flex items-center justify-center mb-2">
                <AppIcon name="sparkles" class="w-6 h-6" />
              </div>
              <div class="text-xs text-slate-500">切片证据</div>
              <div class="text-base font-bold text-slate-800">{{ overviewValue(overview?.qa_ready?.approved_chunks) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ Documents Tab ============ -->
    <div v-else-if="currentTab === 'documents'" class="pt-1">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div class="flex flex-wrap items-center gap-2.5 rounded-xl border border-slate-200 bg-white p-2.5 shadow-sm">
            <input
              v-model="docKeyword"
              @keydown.enter.prevent="docPage = 1; loadDocuments()"
              placeholder="搜索文件名/路径/手册类型..."
              class="min-w-[240px] flex-1 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 sm:w-80"
            />
            <button @click="docPage = 1; loadDocuments()" class="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900">搜索</button>
          </div>
          <span class="text-xs text-slate-500">共 {{ docTotal }} 份文档</span>
        </div>

        <div v-if="docError" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ docError }}</div>
        <div v-if="docLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>

        <div v-if="!docLoading && documents.length === 0 && !docError" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300">
            <AppIcon name="inbox" class="w-8 h-8" />
          </div>
          <h3 class="text-base font-semibold text-slate-800">当前没有文档</h3>
          <p class="text-sm text-slate-400 mt-1 max-w-md">没有已摄入的原始文档，请先完成文档摄入。</p>
        </div>

        <div v-if="!docLoading && documents.length > 0" class="divide-y divide-slate-100">
          <div
            v-for="doc in documents"
            :key="doc.doc_id"
            class="p-4 hover:bg-slate-50/50 transition-colors"
          >
            <div class="flex items-start justify-between mb-2">
              <div class="flex-1 min-w-0">
                <h4 class="text-sm font-semibold text-slate-800 truncate">{{ doc.file_name }}</h4>
                <p class="text-xs text-slate-500 truncate mt-0.5">{{ doc.source_path }}</p>
              </div>
              <span class="ml-3 text-[10px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 whitespace-nowrap border border-slate-200">{{ doc.manual_type || '未知类型' }}</span>
            </div>
            <div class="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500 mt-2">
              <span v-if="doc.aircraft_model">机型: {{ doc.aircraft_model }}</span>
              <span v-if="doc.ata_chapter">ATA: {{ doc.ata_chapter }}</span>
              <span v-if="doc.parser_name">解析器: {{ doc.parser_name }}</span>
              <span class="ml-auto text-indigo-600 font-medium">切片: {{ doc.chunk_count }} · 卡片: {{ doc.card_count }}</span>
            </div>
          </div>
        </div>

        <div v-if="Math.ceil(docTotal / 20) > 1" class="p-4 border-t border-slate-200 flex items-center justify-center gap-2">
          <button @click="docPrevPage" :disabled="docPage === 1" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">上一页</button>
          <span class="text-sm text-slate-600">第 {{ docPage }} / {{ Math.ceil(docTotal / 20) }} 页</span>
          <button @click="docNextPage" :disabled="docPage >= Math.ceil(docTotal / 20)" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">下一页</button>
        </div>
      </div>
    </div>

    <!-- ============ Chunks Tab ============ -->
    <div v-else-if="currentTab === 'chunks'" class="pt-1">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div class="flex flex-wrap items-center gap-2.5 rounded-xl border border-slate-200 bg-white p-2.5 shadow-sm">
            <select
              v-model="chunkStatus"
              @change="chunkPage = 1; loadChunks()"
              class="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            >
              <option value="">全部状态</option>
              <option value="approved">已审核</option>
              <option value="review">待审核</option>
              <option value="rejected">已驳回</option>
            </select>
            <input
              v-model="chunkKeyword"
              @keydown.enter.prevent="chunkPage = 1; loadChunks()"
              placeholder="搜索内容/章节/实体..."
              class="min-w-[240px] flex-1 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 sm:w-80"
            />
            <button @click="chunkPage = 1; loadChunks()" class="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900">搜索</button>
          </div>
          <span class="text-xs text-slate-500">共 {{ chunkTotal }} 条切块</span>
        </div>

        <div v-if="chunkError" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ chunkError }}</div>
        <div v-if="chunkLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>

        <div v-if="!chunkLoading && chunks.length === 0 && !chunkError" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300">
            <AppIcon name="inbox" class="w-8 h-8" />
          </div>
          <h3 class="text-base font-semibold text-slate-800">当前没有原文切块</h3>
          <p class="text-sm text-slate-400 mt-1 max-w-md">没有符合当前筛选条件的原文证据，请先完成文档摄入与切块。</p>
        </div>

        <div v-if="!chunkLoading && chunks.length > 0" class="divide-y divide-slate-100">
          <div
            v-for="chunk in chunks"
            :key="chunk.chunk_id"
            class="p-4 hover:bg-slate-50/50 transition-colors"
          >
            <div class="flex items-start justify-between mb-2">
              <div class="flex-1 min-w-0 flex items-center space-x-2">
                <span class="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">{{ chunk.block_type }}</span>
                <span class="text-[11px] text-slate-500 truncate">来源: {{ chunk.source_file }}</span>
              </div>
              <span
                class="text-[10px] font-medium px-2 py-0.5 rounded border"
                :class="statusColor(chunk.status)"
              >{{ statusLabel(chunk.status) }}</span>
            </div>
            <p class="text-xs text-slate-700 leading-relaxed line-clamp-3 mb-2">{{ chunk.content }}</p>
            <div class="flex items-center justify-between text-[11px] text-slate-500">
              <span class="truncate flex-1">{{ chunk.section_path }}</span>
              <span class="ml-2 text-indigo-600 font-medium whitespace-nowrap">相关度 {{ ((chunk.score || 0) * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>

        <div v-if="Math.ceil(chunkTotal / 20) > 1" class="p-4 border-t border-slate-200 flex items-center justify-center gap-2">
          <button @click="chunkPrevPage" :disabled="chunkPage === 1" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">上一页</button>
          <span class="text-sm text-slate-600">第 {{ chunkPage }} / {{ Math.ceil(chunkTotal / 20) }} 页</span>
          <button @click="chunkNextPage" :disabled="chunkPage >= Math.ceil(chunkTotal / 20)" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">下一页</button>
        </div>
      </div>
    </div>

    <!-- ============ Cards Tab ============ -->
    <div v-else-if="currentTab === 'cards'" class="pt-1">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div class="flex flex-wrap items-center gap-2.5 rounded-xl border border-slate-200 bg-white p-2.5 shadow-sm">
            <label class="pl-1 text-sm font-medium text-slate-600">状态:</label>
            <select
              v-model="statusFilter"
              @change="page = 1; keyword.trim() ? doSearch() : doList()"
              class="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            >
              <option value="approved">已审核</option>
              <option value="review">待审核</option>
              <option value="rejected">已驳回</option>
              <option value="">全部状态</option>
            </select>
            <input
              v-model="keyword"
              @keydown.enter.prevent="doSearch"
              placeholder="全文搜索..."
              class="min-w-[240px] flex-1 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 sm:w-80"
            />
            <button @click="doSearch" class="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900">搜索</button>
          </div>
          <span class="text-xs text-slate-500">共 {{ total }} 张卡片</span>
        </div>

        <div v-if="error" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ error }}</div>
        <div v-if="loading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>

        <div v-if="!loading && cards.length === 0 && !error" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300">
            <AppIcon name="inbox" class="w-8 h-8" />
          </div>
          <h3 class="text-base font-semibold text-slate-800">暂无 Wiki 卡片</h3>
          <p class="text-sm text-slate-400 mt-1 max-w-md">没有符合当前筛选的 Wiki 卡片，请先完成文档摄入与知识编译。</p>
        </div>

        <div v-if="!loading && cards.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
          <div
            v-for="card in cards"
            :key="card.card_id"
            @click="openCard(card)"
            class="bg-white rounded-lg border border-slate-200 hover:border-indigo-300 hover:shadow-sm transition-all cursor-pointer group"
          >
            <div class="p-4">
              <div class="flex items-start justify-between mb-2">
                <span class="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">{{ cardTypeLabel(card.card_type) }}</span>
                <span class="text-[10px] font-medium px-2 py-0.5 rounded border" :class="statusColor(card.status)">{{ statusLabel(card.status) }}</span>
              </div>
              <h3 class="text-sm font-medium text-slate-800 mb-1 line-clamp-2 group-hover:text-indigo-600 transition-colors">{{ card.title }}</h3>
              <p class="text-xs text-slate-600 leading-relaxed line-clamp-3 mb-3">{{ card.content }}</p>
              <div class="flex items-center justify-between text-[11px] text-slate-500">
                <span>相关度 {{ ((card.score ?? 0) * 100).toFixed(0) }}%</span>
                <span class="truncate ml-2">{{ card.source_ref }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="totalPages > 1" class="p-4 border-t border-slate-200 flex items-center justify-center gap-2">
          <button @click="prevPage" :disabled="page === 1" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">上一页</button>
          <span class="text-sm text-slate-600">第 {{ page }} / {{ totalPages }} 页</span>
          <button @click="nextPage" :disabled="page === totalPages" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">下一页</button>
        </div>
      </div>
    </div>

    <!-- ============ Entities Tab ============ -->
    <div v-else-if="currentTab === 'entities'" class="pt-1">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div class="flex flex-wrap items-center gap-2.5 rounded-xl border border-slate-200 bg-white p-2.5 shadow-sm">
            <select
              v-model="entityTypeFilter"
              @change="entityPage = 1; loadEntities()"
              class="rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            >
              <option v-for="t in entityTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
            <input
              v-model="entityKeyword"
              @keydown.enter.prevent="entityPage = 1; loadEntities()"
              placeholder="搜索实体名称..."
              class="min-w-[240px] flex-1 rounded-lg border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 sm:w-80"
            />
            <button @click="entityPage = 1; loadEntities()" class="rounded-lg bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-900">搜索</button>
          </div>
          <span class="text-xs text-slate-500">共 {{ entityTotal }} 个实体</span>
        </div>

        <div v-if="entityError" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ entityError }}</div>
        <div v-if="entityLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>

        <div v-if="!entityLoading && entities.length === 0 && !entityError" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300">
            <AppIcon name="inbox" class="w-8 h-8" />
          </div>
          <h3 class="text-base font-semibold text-slate-800">当前没有实体</h3>
          <p class="text-sm text-slate-400 mt-1 max-w-md">没有符合当前筛选条件的实体，请先完成知识编译与实体抽取。</p>
        </div>

        <div v-if="!entityLoading && entities.length > 0" class="divide-y divide-slate-100">
          <div
            v-for="entity in entities"
            :key="`${entity.entity_type}-${entity.value}`"
            class="p-4 hover:bg-slate-50/50 transition-colors flex items-center justify-between"
          >
            <div class="flex-1 min-w-0">
              <h4 class="text-sm font-semibold text-slate-800">{{ entity.value }}</h4>
              <div class="flex items-center gap-4 text-[11px] text-slate-500 mt-1">
                <span>关联 chunk: {{ entity.chunk_ids?.length || 0 }} 个</span>
                <span>出现次数: {{ entity.count }}</span>
              </div>
            </div>
            <span class="ml-3 text-[10px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200 whitespace-nowrap">{{ entity.entity_type }}</span>
          </div>
        </div>

        <div v-if="Math.ceil(entityTotal / 20) > 1" class="p-4 border-t border-slate-200 flex items-center justify-center gap-2">
          <button @click="entityPrevPage" :disabled="entityPage === 1" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">上一页</button>
          <span class="text-sm text-slate-600">第 {{ entityPage }} / {{ Math.ceil(entityTotal / 20) }} 页</span>
          <button @click="entityNextPage" :disabled="entityPage >= Math.ceil(entityTotal / 20)" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">下一页</button>
        </div>
      </div>
    </div>

    <!-- ============ Indexes Tab ============ -->
    <div v-else-if="currentTab === 'indexes'" class="pt-1">
      <div v-if="indexLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>
      <div v-else-if="indexError" class="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">{{ indexError }}</div>
      <div v-else-if="indexStatus" class="space-y-4">
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 border-b border-slate-200 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full" :class="indexStatus.milvus?.ok ? 'bg-blue-500' : 'bg-rose-500'"></span>
              <h3 class="text-sm font-semibold text-slate-800">Milvus 向量索引</h3>
            </div>
            <span class="text-[10px] font-medium px-2 py-0.5 rounded" :class="indexStatus.milvus?.ok ? 'bg-blue-50 text-blue-700' : 'bg-rose-50 text-rose-700'">{{ indexStatus.milvus?.ok ? '正常' : '异常' }}</span>
          </div>
          <div v-if="indexStatus.milvus?.ok" class="p-4 text-sm">
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">原文切片向量数</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.milvus.rag_chunks ?? 0 }}</div>
            </div>
          </div>
          <div v-else class="p-4 text-xs text-rose-600">{{ indexStatus.milvus?.error }}</div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 border-b border-slate-200 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full" :class="indexStatus.elasticsearch?.ok ? 'bg-blue-500' : 'bg-rose-500'"></span>
              <h3 class="text-sm font-semibold text-slate-800">Elasticsearch 全文索引</h3>
            </div>
            <span class="text-[10px] font-medium px-2 py-0.5 rounded" :class="indexStatus.elasticsearch?.ok ? 'bg-blue-50 text-blue-700' : 'bg-rose-50 text-rose-700'">{{ indexStatus.elasticsearch?.ok ? '正常' : '异常' }}</span>
          </div>
          <div v-if="indexStatus.elasticsearch?.ok" class="p-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">原文切片全文索引</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.elasticsearch.knowledge_chunks ?? 0 }}</div>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">实体索引</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.elasticsearch.entities ?? 0 }}</div>
            </div>
          </div>
          <div v-else class="p-4 text-xs text-rose-600">{{ indexStatus.elasticsearch?.error }}</div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 border-b border-slate-200 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full" :class="indexStatus.postgres?.ok ? 'bg-blue-500' : 'bg-rose-500'"></span>
              <h3 class="text-sm font-semibold text-slate-800">PostgreSQL 真相源</h3>
            </div>
            <span class="text-[10px] font-medium px-2 py-0.5 rounded" :class="indexStatus.postgres?.ok ? 'bg-blue-50 text-blue-700' : 'bg-rose-50 text-rose-700'">{{ indexStatus.postgres?.ok ? '正常' : '异常' }}</span>
          </div>
          <div v-if="indexStatus.postgres?.ok" class="p-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">文档数</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.postgres.documents ?? 0 }}</div>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">切片数</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.postgres.chunks ?? 0 }}</div>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">Wiki 卡片数</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.postgres.wiki_cards ?? 0 }}</div>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">Wiki 审核记录</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.postgres.wiki_reviews ?? 0 }}</div>
            </div>
          </div>
          <div v-else class="p-4 text-xs text-rose-600">{{ indexStatus.postgres?.error }}</div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 border-b border-slate-200 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full" :class="indexStatus.nl2sql?.ok ? 'bg-blue-500' : 'bg-rose-500'"></span>
              <h3 class="text-sm font-semibold text-slate-800">结构化元数据索引</h3>
            </div>
            <span class="text-[10px] font-medium px-2 py-0.5 rounded" :class="indexStatus.nl2sql?.ok ? 'bg-blue-50 text-blue-700' : 'bg-rose-50 text-rose-700'">{{ indexStatus.nl2sql?.ok ? '正常' : '异常' }}</span>
          </div>
          <div v-if="indexStatus.nl2sql?.ok" class="p-4 grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">表协议数</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.nl2sql.table_info ?? 0 }}</div>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">字段协议数</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.nl2sql.column_info ?? 0 }}</div>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">指标协议数</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.nl2sql.metric_info ?? 0 }}</div>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-100 bg-slate-50 px-4 py-3">
              <div class="text-xs font-medium text-slate-600">值域索引数</div>
              <div class="text-xl font-bold text-slate-800">{{ indexStatus.nl2sql.value_info ?? 0 }}</div>
            </div>
          </div>
          <div v-else class="p-4 text-xs text-rose-600">{{ indexStatus.nl2sql?.error }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wiki-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 0.75rem;
}

.wiki-tab {
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

.wiki-tab:hover {
  border-color: #cbd5e1;
  color: #0f172a;
  background: #f8fafc;
}

.wiki-tab.is-active {
  border-color: #818cf8;
  background: #eef2ff;
  color: #4338ca;
  font-weight: 600;
}
</style>
