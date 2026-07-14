<script setup lang="ts">
import { ref, onMounted, computed, watch, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  BarChart3,
  FileText,
  Scissors,
  Layers,
  Tag,
  Database,
  X,
  ExternalLink,
} from "lucide-vue-next";
import {
  listWikiCards,
  searchWikiFulltext,
  getKnowledgeOverview,
  getIndexStatus,
  listDocuments,
  listChunks,
  listEntities,
  getDocumentDetail,
  getEntityDetail,
} from "@/api/client";
import AppIcon from "@/components/AppIcon.vue";
import type {
  WikiCardInfo,
  KnowledgeOverview,
  IndexStatus,
  DocumentItem,
  ChunkItem,
  EntityItem,
  DocumentDetail,
  EntityDetail,
} from "@/types";

const router = useRouter();
const route = useRoute();

type TabKey = "overview" | "documents" | "chunks" | "cards" | "entities" | "indexes";
type PreviewKind = "document" | "chunk" | "card" | "entity" | null;

const currentTab = ref<TabKey>((route.query.tab as TabKey) || "overview");

const tabs = [
  { key: "overview" as TabKey, label: "总览", icon: BarChart3 },
  { key: "documents" as TabKey, label: "文档", icon: FileText },
  { key: "chunks" as TabKey, label: "原文切块", icon: Scissors },
  { key: "cards" as TabKey, label: "Wiki 卡片", icon: Layers },
  { key: "entities" as TabKey, label: "实体", icon: Tag },
  { key: "indexes" as TabKey, label: "索引状态", icon: Database },
];

function switchTab(tab: TabKey) {
  currentTab.value = tab;
  closePreview();
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

// ================ 预览抽屉状态 ================
interface PreviewState {
  kind: PreviewKind;
  loading: boolean;
  error: string | null;
  doc?: DocumentDetail;
  chunk?: ChunkItem;
  card?: WikiCardInfo;
  entity?: EntityDetail;
  rawText?: string;
  rawLoading?: boolean;
  rawError?: string | null;
}

const preview = ref<PreviewState>({
  kind: null,
  loading: false,
  error: null,
});

function closePreview() {
  preview.value = { kind: null, loading: false, error: null };
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") closePreview();
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onBeforeUnmount(() => window.removeEventListener("keydown", onKeydown));

async function openCardPreview(card: WikiCardInfo) {
  preview.value = { kind: "card", loading: false, error: null, card };
}

function openChunkPreview(chunk: ChunkItem) {
  preview.value = { kind: "chunk", loading: false, error: null, chunk };
}

async function openDocumentPreview(doc: DocumentItem) {
  preview.value = { kind: "document", loading: true, error: null };
  try {
    const detail = await getDocumentDetail(doc.doc_id);
    preview.value = { kind: "document", loading: false, error: null, doc: detail };
    const ext = (detail.file_ext || "").toLowerCase();
    const textExts = ["md", "markdown", "txt", "json", "xml", "csv", "html", "htm"];
    if (detail.has_raw && textExts.includes(ext)) {
      preview.value.rawLoading = true;
      preview.value.rawError = null;
      try {
        const rawUrl = `/api/knowledge/documents/${encodeURIComponent(detail.doc_id)}/raw`;
        const resp = await fetch(rawUrl);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const txt = await resp.text();
        if (preview.value.kind === "document" && preview.value.doc?.doc_id === detail.doc_id) {
          preview.value.rawText = txt;
          preview.value.rawLoading = false;
        }
      } catch (e) {
        if (preview.value.kind === "document" && preview.value.doc?.doc_id === detail.doc_id) {
          preview.value.rawError = (e as Error).message;
          preview.value.rawLoading = false;
        }
      }
    }
  } catch (e) {
    preview.value = { kind: "document", loading: false, error: (e as Error).message, doc: { ...doc, sample_chunks: [] } as DocumentDetail };
  }
}

async function openEntityPreview(entity: EntityItem) {
  preview.value = { kind: "entity", loading: true, error: null };
  try {
    const detail = await getEntityDetail(entity.entity_type, entity.value);
    preview.value = { kind: "entity", loading: false, error: null, entity: detail };
  } catch (e) {
    preview.value = { kind: "entity", loading: false, error: (e as Error).message };
  }
}

function openCardFullPage(card: WikiCardInfo) {
  router.push(`/wiki/${card.card_id}?from=wiki&tab=${currentTab.value}`);
}

function canInlinePreview(ext: string): boolean {
  if (!ext) return false;
  const e = ext.toLowerCase();
  return ["pdf", "md", "markdown", "txt", "png", "jpg", "jpeg", "gif", "html", "htm", "json", "xml", "csv"].includes(e);
}

function isTextPreview(ext: string): boolean {
  if (!ext) return false;
  return ["md", "markdown", "txt", "json", "xml", "csv"].includes(ext.toLowerCase());
}

function isImagePreview(ext: string): boolean {
  if (!ext) return false;
  return ["png", "jpg", "jpeg", "gif"].includes(ext.toLowerCase());
}

function isPdfPreview(ext: string): boolean {
  return (ext || "").toLowerCase() === "pdf";
}

function rawUrl(docId: string, download = false): string {
  const base = `/api/knowledge/documents/${encodeURIComponent(docId)}/raw`;
  return download ? `${base}?download=1` : base;
}

async function openChunkPreviewById(c: { chunk_id: string; content: string; source_file: string; section_path: string; block_type: string; page_numbers: number[] | null; status: string }) {
  const chunkItem: ChunkItem = {
    chunk_id: c.chunk_id,
    content: c.content,
    source_file: c.source_file,
    section_path: c.section_path,
    block_type: c.block_type,
    page_numbers: c.page_numbers,
    status: c.status,
    doc_id: "",
    score: 0,
  };
  preview.value = { kind: "chunk", loading: false, error: null, chunk: chunkItem };
}

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
  if (status === "approved") return "bg-emerald-50 text-emerald-700 border-emerald-200";
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

function cardTypeLabel(t: string): string {
  if (t === "definition") return "定义";
  if (t === "concept") return "概念";
  if (t === "procedure") return "流程";
  if (t === "faq") return "问答";
  if (t === "fault") return "故障";
  return t;
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

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

function nextPage() { if (page.value < totalPages.value) { page.value++; doList(); } }
function prevPage() { if (page.value > 1) { page.value--; doList(); } }

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

async function loadOverview() {
  overviewLoading.value = true;
  overviewError.value = null;
  try {
    overview.value = await getKnowledgeOverview();
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

async function loadIndexStatus() {
  indexLoading.value = true;
  indexError.value = null;
  try {
    indexStatus.value = await getIndexStatus();
  } catch (e) {
    indexError.value = (e as Error).message;
  } finally {
    indexLoading.value = false;
  }
}

function refreshAll() {
  loadOverview();
  loadDocuments();
  loadChunks();
  loadEntities();
  loadIndexStatus();
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
  <div class="mx-auto max-w-7xl space-y-4 px-6 py-3 relative">
    <div class="flex justify-end">
      <button
        @click="refreshAll"
        class="flex items-center space-x-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-900 active:scale-95 disabled:opacity-60"
      >
        <AppIcon name="refresh-cw" class="h-4 w-4" />
        <span>刷新数据</span>
      </button>
    </div>

    <div>
      <div class="governance-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="governance-tab"
          :class="currentTab === tab.key ? 'is-active' : ''"
          @click="switchTab(tab.key)"
        >
          <component :is="tab.icon" class="h-4 w-4" />
          <span>{{ tab.label }}</span>
        </button>
      </div>
    </div>

    <!-- ============ Overview Tab ============ -->
    <div v-if="currentTab === 'overview'">
      <div v-if="overviewLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>
      <div v-else-if="overviewError" class="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">{{ overviewError }}</div>
      <div v-else-if="overview" class="space-y-6">
        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div class="bg-white p-3 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-slate-500">文档</p>
              <p class="text-xl font-bold text-slate-900">{{ overview.documents }}</p>
            </div>
            <div class="p-1.5 text-slate-600"><AppIcon name="file-text" class="w-4 h-4" /></div>
          </div>
          <div class="bg-white p-3 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-slate-500">原文切块</p>
              <p class="text-xl font-bold text-slate-900">{{ overview.chunks }}</p>
            </div>
            <div class="p-1.5 text-slate-600"><AppIcon name="file-text" class="w-4 h-4" /></div>
          </div>
          <div class="bg-white p-3 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-slate-500">Wiki 卡片</p>
              <p class="text-xl font-bold text-slate-900">{{ overview.wiki_cards }}</p>
            </div>
            <div class="p-1.5 text-slate-600"><AppIcon name="layers" class="w-4 h-4" /></div>
          </div>
          <div class="bg-white p-3 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-slate-500">实体</p>
              <p class="text-xl font-bold text-slate-900">{{ overview.entities }}</p>
            </div>
            <div class="p-1.5 text-slate-600"><AppIcon name="network" class="w-4 h-4" /></div>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div class="bg-white p-3 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-amber-600">待审核</p>
              <p class="text-xl font-bold text-amber-600">{{ overview.reviews?.pending ?? 0 }}</p>
            </div>
            <div class="p-1.5 text-amber-600"><AppIcon name="clock" class="w-4 h-4" /></div>
          </div>
          <div class="bg-white p-3 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-emerald-600">已审核</p>
              <p class="text-xl font-bold text-emerald-600">{{ overview.reviews?.approved ?? 0 }}</p>
            </div>
            <div class="p-1.5 text-emerald-600"><AppIcon name="check-circle" class="w-4 h-4" /></div>
          </div>
          <div class="bg-white p-3 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-rose-600">已驳回</p>
              <p class="text-xl font-bold text-rose-600">{{ overview.reviews?.rejected ?? 0 }}</p>
            </div>
            <div class="p-1.5 text-rose-600"><AppIcon name="x-circle" class="w-4 h-4" /></div>
          </div>
          <div class="bg-white p-3 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-indigo-600">问答可用</p>
              <p class="text-xl font-bold text-indigo-600">{{ overview.qa_ready?.approved_cards ?? 0 }}</p>
            </div>
            <div class="p-1.5 text-indigo-600"><AppIcon name="sparkles" class="w-4 h-4" /></div>
          </div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-slate-800">索引同步</h3>
            <span class="text-xs text-slate-500">Milvus / Elasticsearch 双写</span>
          </div>
          <div class="p-5 grid grid-cols-2 md:grid-cols-5 gap-4">
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100">
              <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Milvus chunks</div>
              <div class="text-2xl font-bold text-slate-800">{{ overview.indexes?.milvus_chunks ?? 0 }}</div>
            </div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100">
              <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Milvus cards</div>
              <div class="text-2xl font-bold text-slate-800">{{ overview.indexes?.milvus_cards ?? 0 }}</div>
            </div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100">
              <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">ES chunks</div>
              <div class="text-2xl font-bold text-slate-800">{{ overview.indexes?.es_chunks ?? 0 }}</div>
            </div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100">
              <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">ES cards</div>
              <div class="text-2xl font-bold text-slate-800">{{ overview.indexes?.es_cards ?? 0 }}</div>
            </div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100">
              <div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">ES entities</div>
              <div class="text-2xl font-bold text-slate-800">{{ overview.indexes?.es_entities ?? 0 }}</div>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 bg-slate-50/70 border-b border-slate-200">
            <h3 class="text-sm font-semibold text-slate-800">知识流向</h3>
          </div>
          <div class="p-6 flex items-center justify-between gap-2 overflow-x-auto">
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-slate-600 flex items-center justify-center mb-2"><AppIcon name="file-text" class="w-6 h-6" /></div>
              <div class="text-xs text-slate-500">原始文档</div>
              <div class="text-base font-bold text-slate-800">{{ overview.documents }}</div>
            </div>
            <AppIcon name="chevron-right" class="w-5 h-5 text-slate-300 flex-shrink-0" />
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-slate-600 flex items-center justify-center mb-2"><AppIcon name="file-text" class="w-6 h-6" /></div>
              <div class="text-xs text-slate-500">原文切块</div>
              <div class="text-base font-bold text-slate-800">{{ overview.chunks }}</div>
            </div>
            <AppIcon name="chevron-right" class="w-5 h-5 text-slate-300 flex-shrink-0" />
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-slate-600 flex items-center justify-center mb-2"><AppIcon name="layers" class="w-6 h-6" /></div>
              <div class="text-xs text-slate-500">Wiki 卡片</div>
              <div class="text-base font-bold text-slate-800">{{ overview.wiki_cards }}</div>
            </div>
            <AppIcon name="chevron-right" class="w-5 h-5 text-slate-300 flex-shrink-0" />
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-amber-600 flex items-center justify-center mb-2"><AppIcon name="check-circle" class="w-6 h-6" /></div>
              <div class="text-xs text-slate-500">审核状态</div>
              <div class="text-base font-bold text-slate-800">{{ overview.reviews?.approved ?? 0 }} 审核通过</div>
            </div>
            <AppIcon name="chevron-right" class="w-5 h-5 text-slate-300 flex-shrink-0" />
            <div class="flex flex-col items-center min-w-[110px]">
              <div class="w-12 h-12 rounded-xl border border-slate-200 text-indigo-600 flex items-center justify-center mb-2"><AppIcon name="sparkles" class="w-6 h-6" /></div>
              <div class="text-xs text-slate-500">问答证据</div>
              <div class="text-base font-bold text-slate-800">{{ overview.qa_ready?.approved_cards ?? 0 }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ Documents Tab ============ -->
    <div v-else-if="currentTab === 'documents'">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div class="flex items-center space-x-3">
            <input
              v-model="docKeyword"
              @keydown.enter.prevent="docPage = 1; loadDocuments()"
              placeholder="搜索文件名/路径/手册类型..."
              class="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 w-72"
            />
            <button @click="docPage = 1; loadDocuments()" class="bg-slate-800 hover:bg-slate-900 text-white px-4 py-1.5 rounded-lg text-sm font-medium">搜索</button>
          </div>
          <span class="text-xs text-slate-500">共 {{ docTotal }} 份文档 · 点击查看详情与切块内容</span>
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
            @click="() => openDocumentPreview(doc)"
            class="p-4 hover:bg-slate-50 transition-colors cursor-pointer"
            :class="preview.kind === 'document' && preview.doc?.doc_id === doc.doc_id ? 'bg-indigo-50/50' : ''"
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
              <span class="ml-auto text-indigo-600 font-medium">Chunks: {{ doc.chunk_count }} · 卡片: {{ doc.card_count }}</span>
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
    <div v-else-if="currentTab === 'chunks'">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div class="flex items-center space-x-3">
            <select v-model="chunkStatus" @change="chunkPage = 1; loadChunks()" class="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
              <option value="">全部状态</option>
              <option value="approved">已审核</option>
              <option value="review">待审核</option>
              <option value="rejected">已驳回</option>
            </select>
            <input
              v-model="chunkKeyword"
              @keydown.enter.prevent="chunkPage = 1; loadChunks()"
              placeholder="搜索内容/章节/实体..."
              class="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 w-72"
            />
            <button @click="chunkPage = 1; loadChunks()" class="bg-slate-800 hover:bg-slate-900 text-white px-4 py-1.5 rounded-lg text-sm font-medium">搜索</button>
          </div>
          <span class="text-xs text-slate-500">共 {{ chunkTotal }} 条切块 · 点击查看完整内容</span>
        </div>

        <div v-if="chunkError" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ chunkError }}</div>
        <div v-if="chunkLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>

        <div v-if="!chunkLoading && chunks.length === 0 && !chunkError" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300"><AppIcon name="inbox" class="w-8 h-8" /></div>
          <h3 class="text-base font-semibold text-slate-800">当前没有原文切块</h3>
          <p class="text-sm text-slate-400 mt-1 max-w-md">没有符合当前筛选条件的原文证据，请先完成文档摄入与切块。</p>
        </div>

        <div v-if="!chunkLoading && chunks.length > 0" class="divide-y divide-slate-100">
          <div
            v-for="chunk in chunks"
            :key="chunk.chunk_id"
            @click="() => openChunkPreview(chunk)"
            class="p-4 hover:bg-slate-50 transition-colors cursor-pointer"
            :class="preview.kind === 'chunk' && preview.chunk?.chunk_id === chunk.chunk_id ? 'bg-emerald-50/50' : ''"
          >
            <div class="flex items-start justify-between mb-2">
              <div class="flex-1 min-w-0 flex items-center space-x-2">
                <span class="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">{{ chunk.block_type }}</span>
                <span class="text-[11px] text-slate-500 truncate">来源: {{ chunk.source_file }}</span>
              </div>
              <span class="text-[10px] font-medium px-2 py-0.5 rounded border" :class="statusColor(chunk.status)">{{ statusLabel(chunk.status) }}</span>
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
    <div v-else-if="currentTab === 'cards'">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div class="flex items-center space-x-3">
            <label class="text-sm font-medium text-slate-600">状态:</label>
            <select v-model="statusFilter" @change="page = 1; keyword.trim() ? doSearch() : doList()" class="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
              <option value="approved">已审核</option>
              <option value="review">待审核</option>
              <option value="rejected">已驳回</option>
              <option value="">全部状态</option>
            </select>
            <input v-model="keyword" @keydown.enter.prevent="doSearch" placeholder="全文搜索..." class="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 w-72" />
            <button @click="doSearch" class="bg-slate-800 hover:bg-slate-900 text-white px-4 py-1.5 rounded-lg text-sm font-medium">搜索</button>
          </div>
          <span class="text-xs text-slate-500">共 {{ total }} 张卡片 · 点击预览 · 双击或面板内按钮打开完整页</span>
        </div>

        <div v-if="error" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ error }}</div>
        <div v-if="loading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>

        <div v-if="!loading && cards.length === 0 && !error" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300"><AppIcon name="inbox" class="w-8 h-8" /></div>
          <h3 class="text-base font-semibold text-slate-800">暂无 Wiki 卡片</h3>
          <p class="text-sm text-slate-400 mt-1 max-w-md">没有符合当前筛选的 Wiki 卡片，请先完成文档摄入与知识编译。</p>
        </div>

        <div v-if="!loading && cards.length > 0" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 p-4">
          <div
            v-for="card in cards"
            :key="card.card_id"
            @click="() => openCardPreview(card)"
            @dblclick="() => openCardFullPage(card)"
            class="bg-white rounded-lg border border-slate-200 hover:border-indigo-300 hover:shadow-sm transition-all cursor-pointer group"
            :class="preview.kind === 'card' && preview.card?.card_id === card.card_id ? 'border-indigo-500 ring-2 ring-indigo-200' : ''"
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
    <div v-else-if="currentTab === 'entities'">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div class="flex items-center space-x-3">
            <select v-model="entityTypeFilter" @change="entityPage = 1; loadEntities()" class="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500">
              <option v-for="t in entityTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
            <input v-model="entityKeyword" @keydown.enter.prevent="entityPage = 1; loadEntities()" placeholder="搜索实体名称..." class="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 w-72" />
            <button @click="entityPage = 1; loadEntities()" class="bg-slate-800 hover:bg-slate-900 text-white px-4 py-1.5 rounded-lg text-sm font-medium">搜索</button>
          </div>
          <span class="text-xs text-slate-500">共 {{ entityTotal }} 个实体 · 点击查看关联切块内容</span>
        </div>

        <div v-if="entityError" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ entityError }}</div>
        <div v-if="entityLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>

        <div v-if="!entityLoading && entities.length === 0 && !entityError" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300"><AppIcon name="inbox" class="w-8 h-8" /></div>
          <h3 class="text-base font-semibold text-slate-800">当前没有实体</h3>
          <p class="text-sm text-slate-400 mt-1 max-w-md">没有符合当前筛选条件的实体，请先完成知识编译与实体抽取。</p>
        </div>

        <div v-if="!entityLoading && entities.length > 0" class="divide-y divide-slate-100">
          <div
            v-for="entity in entities"
            :key="`${entity.entity_type}-${entity.value}`"
            @click="() => openEntityPreview(entity)"
            class="p-4 hover:bg-slate-50 transition-colors cursor-pointer flex items-center justify-between"
            :class="preview.kind === 'entity' && preview.entity?.value === entity.value && preview.entity?.entity_type === entity.entity_type ? 'bg-amber-50/50' : ''"
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
    <div v-else-if="currentTab === 'indexes'">
      <div v-if="indexLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>
      <div v-else-if="indexError" class="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">{{ indexError }}</div>
      <div v-else-if="indexStatus" class="space-y-4">
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 border-b border-slate-200 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full" :class="indexStatus.milvus?.ok ? 'bg-emerald-500' : 'bg-rose-500'"></span>
              <h3 class="text-sm font-semibold text-slate-800">Milvus</h3>
            </div>
            <span class="text-[10px] font-medium px-2 py-0.5 rounded" :class="indexStatus.milvus?.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'">{{ indexStatus.milvus?.ok ? '正常' : '异常' }}</span>
          </div>
          <div v-if="indexStatus.milvus?.ok" class="p-4 grid grid-cols-2 gap-3 text-sm">
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">rag_chunks</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.milvus.rag_chunks ?? 0 }}</div></div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">wiki_cards</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.milvus.wiki_cards ?? 0 }}</div></div>
          </div>
          <div v-else class="p-4 text-xs text-rose-600">{{ indexStatus.milvus?.error }}</div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 border-b border-slate-200 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full" :class="indexStatus.elasticsearch?.ok ? 'bg-emerald-500' : 'bg-rose-500'"></span>
              <h3 class="text-sm font-semibold text-slate-800">Elasticsearch</h3>
            </div>
            <span class="text-[10px] font-medium px-2 py-0.5 rounded" :class="indexStatus.elasticsearch?.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'">{{ indexStatus.elasticsearch?.ok ? '正常' : '异常' }}</span>
          </div>
          <div v-if="indexStatus.elasticsearch?.ok" class="p-4 grid grid-cols-3 gap-3 text-sm">
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">knowledge_chunks</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.elasticsearch.knowledge_chunks ?? 0 }}</div></div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">wiki_cards</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.elasticsearch.wiki_cards ?? 0 }}</div></div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">entities</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.elasticsearch.entities ?? 0 }}</div></div>
          </div>
          <div v-else class="p-4 text-xs text-rose-600">{{ indexStatus.elasticsearch?.error }}</div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 border-b border-slate-200 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full" :class="indexStatus.postgres?.ok ? 'bg-emerald-500' : 'bg-rose-500'"></span>
              <h3 class="text-sm font-semibold text-slate-800">PostgreSQL</h3>
            </div>
            <span class="text-[10px] font-medium px-2 py-0.5 rounded" :class="indexStatus.postgres?.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'">{{ indexStatus.postgres?.ok ? '正常' : '异常' }}</span>
          </div>
          <div v-if="indexStatus.postgres?.ok" class="p-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">documents</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.postgres.documents ?? 0 }}</div></div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">chunks</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.postgres.chunks ?? 0 }}</div></div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">wiki_cards</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.postgres.wiki_cards ?? 0 }}</div></div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">wiki_reviews</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.postgres.wiki_reviews ?? 0 }}</div></div>
          </div>
          <div v-else class="p-4 text-xs text-rose-600">{{ indexStatus.postgres?.error }}</div>
        </div>

        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 border-b border-slate-200 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full" :class="indexStatus.nl2sql?.ok ? 'bg-emerald-500' : 'bg-rose-500'"></span>
              <h3 class="text-sm font-semibold text-slate-800">NL2SQL metadata</h3>
            </div>
            <span class="text-[10px] font-medium px-2 py-0.5 rounded" :class="indexStatus.nl2sql?.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'">{{ indexStatus.nl2sql?.ok ? '正常' : '异常' }}</span>
          </div>
          <div v-if="indexStatus.nl2sql?.ok" class="p-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">table_info</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.nl2sql.table_info ?? 0 }}</div></div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">column_info</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.nl2sql.column_info ?? 0 }}</div></div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">metric_info</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.nl2sql.metric_info ?? 0 }}</div></div>
            <div class="bg-slate-50 rounded-lg p-3 border border-slate-100"><div class="text-[10px] uppercase tracking-wider text-slate-500 mb-1">value_info</div><div class="text-xl font-bold text-slate-800">{{ indexStatus.nl2sql.value_info ?? 0 }}</div></div>
          </div>
          <div v-else class="p-4 text-xs text-rose-600">{{ indexStatus.nl2sql?.error }}</div>
        </div>
      </div>
    </div>

    <!-- ============ 预览遮罩 + 抽屉 ============ -->
    <Teleport to="body">
      <Transition name="preview-fade">
        <div v-if="preview.kind" class="fixed bg-slate-900/30 z-[90]" style="top:0;right:0;bottom:0;left:0;" @click="closePreview"></div>
      </Transition>
      <Transition name="preview-drawer">
        <aside
          v-if="preview.kind"
          class="preview-drawer-panel fixed bg-white shadow-2xl z-[95] flex flex-col rounded-xl border border-slate-200 overflow-hidden"
          style="top: 16px; right: 16px; bottom: 16px; width: min(860px, calc(100vw - 32px)); left: unset; margin: 0;"
        >
          <!-- 加载中 -->
          <div v-if="preview.loading" class="flex-1 flex items-center justify-center text-slate-400 text-sm">
            <div class="text-center">
              <div class="inline-block w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mb-3"></div>
              <div>加载预览...</div>
            </div>
          </div>

          <!-- 错误 -->
          <template v-else-if="preview.error">
            <div class="flex items-center justify-between p-3 border-b border-slate-200 shrink-0">
              <h3 class="text-sm font-semibold text-slate-800">预览失败</h3>
              <button @click="closePreview" class="p-1.5 rounded hover:bg-slate-100 text-slate-500"><X class="w-4 h-4" /></button>
            </div>
            <div class="p-4 text-sm text-rose-600">{{ preview.error }}</div>
          </template>

          <!-- 文档预览（原文件为主） -->
          <template v-else-if="preview.kind === 'document' && preview.doc">
            <div class="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 bg-slate-50 shrink-0">
              <div class="flex items-center gap-2 min-w-0">
                <FileText class="w-4 h-4 text-indigo-600 shrink-0" />
                <span class="text-xs text-slate-500 shrink-0">文档预览</span>
                <span class="text-sm font-semibold text-slate-800 truncate">{{ preview.doc.file_name }}</span>
                <span class="text-[10px] px-1.5 py-0.5 rounded bg-white border border-slate-200 text-slate-500 uppercase">{{ preview.doc.file_ext || 'file' }}</span>
              </div>
              <button @click="closePreview" class="p-1.5 rounded hover:bg-white text-slate-500"><X class="w-4 h-4" /></button>
            </div>

            <!-- 原文件预览区（占据主要空间） -->
            <div class="relative bg-slate-100 border-b border-slate-200 shrink-0 overflow-hidden flex flex-col" style="flex: 1 1 auto; min-height: 0;">
              <!-- 工具栏 -->
              <div class="flex items-center justify-between px-3 py-1.5 bg-white border-b border-slate-200 shrink-0">
                <span class="text-[11px] text-slate-500">原文件预览</span>
                <div class="flex items-center gap-1">
                  <a v-if="preview.doc.has_raw" :href="rawUrl(preview.doc.doc_id)" target="_blank" rel="noopener"
                     class="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] text-slate-600 hover:bg-slate-100" title="在新窗口打开">
                    <ExternalLink class="w-3 h-3" /> 新窗口打开
                  </a>
                  <a v-if="preview.doc.has_raw" :href="rawUrl(preview.doc.doc_id, true)"
                     class="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] text-slate-600 hover:bg-slate-100" title="下载原文件">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3"/></svg>
                    下载
                  </a>
                </div>
              </div>

              <!-- PDF -->
              <template v-if="preview.doc.has_raw && isPdfPreview(preview.doc.file_ext)">
                <embed :src="rawUrl(preview.doc.doc_id)" type="application/pdf" class="w-full flex-1 min-h-0 bg-white" />
              </template>

              <!-- 图片 -->
              <template v-else-if="preview.doc.has_raw && isImagePreview(preview.doc.file_ext)">
                <div class="flex-1 min-h-0 flex items-center justify-center overflow-auto bg-slate-50 p-4">
                  <img :src="rawUrl(preview.doc.doc_id)" :alt="preview.doc.file_name" class="max-w-full max-h-full object-contain" />
                </div>
              </template>

              <!-- HTML -->
              <template v-else-if="preview.doc.has_raw && ['html','htm'].includes((preview.doc.file_ext||'').toLowerCase())">
                <iframe :src="rawUrl(preview.doc.doc_id)" class="w-full flex-1 min-h-0 border-0 bg-white" :title="preview.doc.file_name"></iframe>
              </template>

              <!-- 文本类：fetch 后 <pre> 渲染 -->
              <template v-else-if="preview.doc.has_raw && isTextPreview(preview.doc.file_ext)">
                <div v-if="preview.rawLoading" class="flex-1 min-h-0 flex items-center justify-center text-slate-400 text-xs">
                  <div class="inline-block w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mr-2"></div>
                  加载原文件...
                </div>
                <div v-else-if="preview.rawError" class="flex-1 min-h-0 flex items-center justify-center text-rose-500 text-xs p-4 text-center">
                  <div>
                    <p class="mb-2">文本加载失败：{{ preview.rawError }}</p>
                    <a :href="rawUrl(preview.doc.doc_id, true)" class="text-indigo-600 hover:underline">下载文件查看</a>
                  </div>
                </div>
                <pre v-else-if="preview.rawText !== undefined" class="flex-1 min-h-0 overflow-auto m-0 p-4 bg-white text-[12px] leading-relaxed text-slate-800 whitespace-pre-wrap break-words font-mono">{{ preview.rawText }}</pre>
                <div v-else class="flex-1 min-h-0 flex items-center justify-center text-slate-400 text-xs">正在加载...</div>
              </template>

              <!-- 不支持内嵌 -->
              <template v-else-if="preview.doc.has_raw">
                <div class="flex-1 min-h-0 flex items-center justify-center">
                  <div class="text-center">
                    <div class="w-16 h-16 mx-auto mb-3 rounded-xl bg-white border border-slate-200 flex items-center justify-center">
                      <FileText class="w-8 h-8 text-slate-400" />
                    </div>
                    <p class="text-sm text-slate-600 mb-1">{{ (preview.doc.file_ext || '').toUpperCase() }} 文件不支持浏览器内嵌预览</p>
                    <p class="text-xs text-slate-400 mb-3">请下载后使用对应软件打开</p>
                    <a :href="rawUrl(preview.doc.doc_id, true)"
                       class="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium">
                      下载原文件
                    </a>
                  </div>
                </div>
              </template>

              <!-- 无原文件 -->
              <template v-else>
                <div class="flex-1 min-h-0 flex items-center justify-center">
                  <div class="text-center">
                    <div class="w-16 h-16 mx-auto mb-3 rounded-xl bg-white border border-slate-200 flex items-center justify-center">
                      <FileText class="w-8 h-8 text-slate-400" />
                    </div>
                    <p class="text-sm text-slate-500">原文件未存储或已丢失</p>
                    <p class="text-xs text-slate-400 mt-1">仅展示元数据与切块</p>
                  </div>
                </div>
              </template>
            </div>

            <!-- 元数据 + 切块（下方收窄，固定高度滚动） -->
            <div class="shrink-0 bg-white border-t border-slate-200 overflow-y-auto" style="height: 220px;">
              <div class="p-3 space-y-2 text-xs">
                <div class="flex gap-1.5 flex-wrap">
                  <span class="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700">Chunks {{ preview.doc.chunk_count }}</span>
                  <span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">卡片 {{ preview.doc.card_count }}</span>
                  <span v-if="preview.doc.manual_type" class="px-2 py-0.5 rounded bg-slate-100 text-slate-700">{{ preview.doc.manual_type }}</span>
                  <span v-if="preview.doc.language" class="px-2 py-0.5 rounded bg-slate-100 text-slate-600">{{ preview.doc.language }}</span>
                </div>

                <div class="grid grid-cols-3 gap-2">
                  <div v-if="preview.doc.ata_chapter" class="bg-slate-50 rounded px-2 py-1 border border-slate-100">
                    <div class="text-[10px] text-slate-500">ATA 章节</div>
                    <div class="text-xs font-medium text-slate-800 truncate">{{ preview.doc.ata_chapter }}</div>
                  </div>
                  <div v-if="preview.doc.aircraft_model" class="bg-slate-50 rounded px-2 py-1 border border-slate-100">
                    <div class="text-[10px] text-slate-500">机型</div>
                    <div class="text-xs font-medium text-slate-800 truncate">{{ preview.doc.aircraft_model }}</div>
                  </div>
                  <div v-if="preview.doc.engine_model" class="bg-slate-50 rounded px-2 py-1 border border-slate-100">
                    <div class="text-[10px] text-slate-500">发动机</div>
                    <div class="text-xs font-medium text-slate-800 truncate">{{ preview.doc.engine_model }}</div>
                  </div>
                  <div v-if="preview.doc.manual_revision" class="bg-slate-50 rounded px-2 py-1 border border-slate-100">
                    <div class="text-[10px] text-slate-500">修订版本</div>
                    <div class="text-xs font-medium text-slate-800 truncate">{{ preview.doc.manual_revision }}</div>
                  </div>
                  <div v-if="preview.doc.effective_date" class="bg-slate-50 rounded px-2 py-1 border border-slate-100">
                    <div class="text-[10px] text-slate-500">生效日期</div>
                    <div class="text-xs font-medium text-slate-800 truncate">{{ preview.doc.effective_date }}</div>
                  </div>
                  <div v-if="preview.doc.parser_name" class="bg-slate-50 rounded px-2 py-1 border border-slate-100">
                    <div class="text-[10px] text-slate-500">解析器</div>
                    <div class="text-xs font-medium text-slate-800 truncate">{{ preview.doc.parser_name }} {{ preview.doc.parser_version }}</div>
                  </div>
                </div>

                <div v-if="preview.doc.sample_chunks.length > 0">
                  <div class="flex items-center gap-1.5 mb-1">
                    <Scissors class="w-3 h-3 text-slate-500" />
                    <span class="text-xs font-semibold text-slate-800">关联切块（{{ preview.doc.sample_chunks.length }}/{{ preview.doc.chunk_count }}）— 点击查看详情</span>
                  </div>
                  <div class="space-y-1">
                    <div v-for="c in preview.doc.sample_chunks" :key="c.chunk_id"
                         class="bg-slate-50 rounded px-2 py-1 border border-slate-100 hover:bg-indigo-50 hover:border-indigo-200 cursor-pointer transition-colors"
                         @click="openChunkPreviewById(c)">
                      <div class="flex items-center justify-between text-[10px] text-slate-500 mb-0.5">
                        <span class="font-medium truncate mr-2">{{ c.section_path || c.block_type || '未分类' }}</span>
                        <span :class="statusColor(c.status)" class="px-1 py-px rounded border text-[10px] shrink-0">{{ statusLabel(c.status) }}</span>
                      </div>
                      <p class="text-xs text-slate-700 leading-relaxed whitespace-pre-wrap line-clamp-2">{{ c.content }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <!-- Chunk 预览 -->
          <template v-else-if="preview.kind === 'chunk' && preview.chunk">
            <div class="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 bg-slate-50 shrink-0">
              <div class="flex items-center gap-2 min-w-0">
                <Scissors class="w-4 h-4 text-emerald-600 shrink-0" />
                <span class="text-xs text-slate-500 shrink-0">原文切块</span>
                <span class="text-sm font-semibold text-slate-800 truncate">{{ preview.chunk.source_file || '未知来源' }}</span>
              </div>
              <button @click="closePreview" class="p-1.5 rounded hover:bg-white text-slate-500"><X class="w-4 h-4" /></button>
            </div>
            <div class="flex-1 overflow-y-auto p-4 space-y-3">
              <div class="flex flex-wrap gap-1.5 text-[11px]">
                <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">{{ preview.chunk.block_type }}</span>
                <span :class="statusColor(preview.chunk.status)" class="px-2 py-0.5 rounded border">{{ statusLabel(preview.chunk.status) }}</span>
                <span v-if="preview.chunk.score !== undefined" class="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700">相关度 {{ ((preview.chunk.score || 0) * 100).toFixed(0) }}%</span>
                <span v-if="preview.chunk.page_numbers?.length" class="px-2 py-0.5 rounded bg-slate-100 text-slate-600">页码: {{ preview.chunk.page_numbers.join(',') }}</span>
              </div>
              <div v-if="preview.chunk.section_path" class="text-xs text-slate-600 bg-slate-50 rounded px-2 py-1.5 border border-slate-100">📁 {{ preview.chunk.section_path }}</div>
              <div class="bg-white border border-slate-200 rounded-lg p-3">
                <p class="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">{{ preview.chunk.content }}</p>
              </div>
              <div class="text-[10px] text-slate-400 font-mono truncate">ID: {{ preview.chunk.chunk_id }}</div>
            </div>
          </template>

          <!-- Wiki 卡片预览 -->
          <template v-else-if="preview.kind === 'card' && preview.card">
            <div class="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 bg-slate-50 shrink-0">
              <div class="flex items-center gap-2 min-w-0">
                <Layers class="w-4 h-4 text-violet-600 shrink-0" />
                <span class="text-xs text-slate-500 shrink-0">Wiki 卡片 · {{ cardTypeLabel(preview.card.card_type) }}</span>
                <span :class="preview.card.status === 'approved' ? 'bg-emerald-100 text-emerald-700' : preview.card.status === 'review' ? 'bg-amber-100 text-amber-700' : 'bg-rose-100 text-rose-700'" class="px-1.5 py-px rounded text-[10px] shrink-0">{{ statusLabel(preview.card.status) }}</span>
                <span class="text-sm font-semibold text-slate-800 truncate">{{ preview.card.title }}</span>
              </div>
              <button @click="closePreview" class="p-1.5 rounded hover:bg-white text-slate-500"><X class="w-4 h-4" /></button>
            </div>
            <div class="flex-1 overflow-y-auto p-4 space-y-3">
              <div class="flex flex-wrap gap-1.5 text-[11px]">
                <span v-if="preview.card.confidence !== undefined" class="px-2 py-0.5 rounded bg-slate-100 text-slate-700">置信度 {{ (preview.card.confidence * 100).toFixed(0) }}%</span>
                <span v-if="preview.card.score !== undefined" class="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700">相关度 {{ ((preview.card.score ?? 0) * 100).toFixed(0) }}%</span>
                <span v-if="preview.card.created_at" class="px-2 py-0.5 rounded bg-slate-100 text-slate-600">{{ preview.card.created_at.slice(0, 10) }}</span>
              </div>
              <div class="bg-white border border-slate-200 rounded-lg p-3">
                <p class="text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">{{ preview.card.content }}</p>
              </div>
              <div v-if="preview.card.notes" class="bg-amber-50 border border-amber-200 rounded-lg p-2">
                <div class="text-[10px] font-medium text-amber-700 mb-0.5">审核备注</div>
                <p class="text-xs text-amber-800 leading-relaxed whitespace-pre-wrap">{{ preview.card.notes }}</p>
              </div>
              <div v-if="preview.card.linked_chunks?.length" class="flex items-center justify-between pt-2 border-t border-slate-200">
                <div class="text-xs text-slate-500">关联切块 {{ preview.card.linked_chunks.length }}</div>
                <button @click="openCardFullPage(preview.card!)" class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium">
                  打开详情页 <ExternalLink class="w-3 h-3" />
                </button>
              </div>
            </div>
          </template>

          <!-- 实体预览 -->
          <template v-else-if="preview.kind === 'entity' && preview.entity">
            <div class="flex items-center justify-between px-4 py-2.5 border-b border-slate-200 bg-slate-50 shrink-0">
              <div class="flex items-center gap-2 min-w-0">
                <Tag class="w-4 h-4 text-orange-600 shrink-0" />
                <span class="text-xs text-slate-500 shrink-0">实体 · {{ preview.entity.entity_type }}</span>
                <span class="text-sm font-semibold text-slate-800 truncate">{{ preview.entity.value }}</span>
              </div>
              <button @click="closePreview" class="p-1.5 rounded hover:bg-white text-slate-500"><X class="w-4 h-4" /></button>
            </div>
            <div class="flex-1 overflow-y-auto p-4 space-y-3">
              <div class="flex gap-1.5 text-[11px] flex-wrap">
                <span class="px-2 py-0.5 rounded bg-indigo-50 text-indigo-700">关联 chunks {{ preview.entity.chunk_ids.length }}</span>
                <span class="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">出现次数 {{ preview.entity.count }}</span>
              </div>
              <div v-if="preview.entity.source_files.length > 0">
                <div class="text-[11px] font-semibold text-slate-700 mb-1">来源文档</div>
                <div class="flex flex-wrap gap-1">
                  <span v-for="f in preview.entity.source_files" :key="f" class="text-[11px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 max-w-full truncate">{{ f }}</span>
                </div>
              </div>
              <div v-if="preview.entity.sample_chunks.length > 0">
                <div class="text-[11px] font-semibold text-slate-700 mb-1">所在切块片段</div>
                <div class="space-y-1.5">
                  <div v-for="c in preview.entity.sample_chunks" :key="c.chunk_id" class="bg-slate-50 rounded px-2 py-1.5 border border-slate-100">
                    <div class="flex items-center justify-between text-[10px] text-slate-500 mb-0.5">
                      <span class="truncate mr-2 font-medium">{{ c.source_file }}</span>
                      <span :class="statusColor(c.status)" class="px-1 py-px rounded border text-[10px] shrink-0">{{ statusLabel(c.status) }}</span>
                    </div>
                    <div v-if="c.section_path" class="text-[10px] text-slate-500 mb-0.5">📁 {{ c.section_path }}</div>
                    <p class="text-xs text-slate-800 leading-relaxed whitespace-pre-wrap">{{ c.content }}</p>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </aside>
      </Transition>
    </Teleport>
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
  cursor: pointer;
  font-family: inherit;
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

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>

<style>
.preview-fade-enter-active,
.preview-fade-leave-active {
  transition: opacity 0.18s ease;
}
.preview-fade-enter-from,
.preview-fade-leave-to {
  opacity: 0;
}

.preview-drawer-enter-active,
.preview-drawer-leave-active {
  transition: opacity 0.2s ease, transform 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}
.preview-drawer-enter-from,
.preview-drawer-leave-to {
  opacity: 0;
  transform: translateX(24px) scale(0.985);
  transform-origin: right center;
}

.preview-drawer-panel {
  transform: translateX(0) scale(1);
  opacity: 1;
}
</style>
