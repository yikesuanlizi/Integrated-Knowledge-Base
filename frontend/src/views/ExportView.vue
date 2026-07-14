<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { exportWiki, listWikiCards } from "@/api/client";
import type { WikiCardInfo } from "@/types";
import AppIcon from "@/components/AppIcon.vue";

const formats = [
  { key: "markdown", label: "Markdown", desc: "文档归档" },
  { key: "json", label: "JSON", desc: "结构数据" },
  { key: "jsonld", label: "JSON-LD", desc: "语义交换" },
  { key: "graphml", label: "GraphML", desc: "图分析" },
  { key: "llms", label: "llms.txt", desc: "模型上下文" },
  { key: "marp", label: "Marp", desc: "演示稿" },
] as const;

type FormatKey = typeof formats[number]["key"];

const selectedFormat = ref<FormatKey>("markdown");
const exporting = ref(false);
const exportedContent = ref<string | null>(null);
const error = ref<string | null>(null);
const copied = ref(false);
const scopeLoading = ref(false);
const allCards = ref<WikiCardInfo[]>([]);
const exportTotal = ref(0);
const selectedCardIds = ref<Set<string>>(new Set());
const selectAll = ref(true);
const showCardSelector = ref(false);

const selectedMeta = computed(() => formats.find((item) => item.key === selectedFormat.value) || formats[0]);

const effectiveContent = computed(() => {
  if (exportedContent.value) return exportedContent.value;
  const cards = selectedCardsForPreview.value;
  return buildDraftPreview(selectedFormat.value, cards, selectedCardIds.value.size);
});

const previewLines = computed(() => effectiveContent.value?.split("\n").slice(0, 200) || []);
const lineCount = computed(() => effectiveContent.value?.split("\n").length || 0);

const selectedCardsForPreview = computed(() => {
  if (selectedCardIds.value.size === 0) return [];
  return allCards.value.filter((c) => selectedCardIds.value.has(c.card_id));
});

const scopeSummary = computed(() => {
  if (scopeLoading.value && exportTotal.value === 0) return "加载中";
  const selected = selectedCardIds.value.size;
  if (selected === exportTotal.value) return `${exportTotal.value} 张已通过 Wiki 卡片（全选）`;
  return `已选 ${selected} / ${exportTotal.value} 张 Wiki 卡片`;
});

const previewCards = computed(() => {
  const selected = selectedCardsForPreview.value;
  if (selected.length > 0) return selected.slice(0, 6);
  return allCards.value.slice(0, 6);
});

const contentSize = computed(() => {
  const content = effectiveContent.value;
  if (!content) return "0 KB";
  const bytes = new Blob([content]).size;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
});

const isPreviewExported = computed(() => exportedContent.value !== null);

function selectFormat(format: FormatKey) {
  if (selectedFormat.value === format) return;
  selectedFormat.value = format;
  exportedContent.value = null;
  copied.value = false;
}

async function loadExportScope(force = false) {
  scopeLoading.value = true;
  try {
    const page = await listWikiCards(1, 5000, undefined, "approved", force);
    allCards.value = page.cards;
    exportTotal.value = page.total;
    if (selectAll.value) {
      selectedCardIds.value = new Set(page.cards.map((c) => c.card_id));
    }
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    scopeLoading.value = false;
  }
}

function toggleCard(cardId: string) {
  const next = new Set(selectedCardIds.value);
  if (next.has(cardId)) {
    next.delete(cardId);
    selectAll.value = false;
  } else {
    next.add(cardId);
    if (next.size === exportTotal.value) selectAll.value = true;
  }
  selectedCardIds.value = next;
  exportedContent.value = null;
}

function toggleSelectAll() {
  if (selectAll.value) {
    selectedCardIds.value = new Set();
    selectAll.value = false;
  } else {
    selectedCardIds.value = new Set(allCards.value.map((c) => c.card_id));
    selectAll.value = true;
  }
  exportedContent.value = null;
}

function cardExcerpt(card: WikiCardInfo) {
  return (card.content || card.source_ref || card.card_id).replace(/\s+/g, " ").slice(0, 180);
}

function buildDraftPreview(format: FormatKey, cards: WikiCardInfo[], total: number) {
  if (!cards.length) return "暂无可导出内容，请先选择要导出的卡片";
  if (format === "json") {
    return JSON.stringify({
      export_scope: "selected_wiki_cards",
      total,
      cards: cards.map((card) => ({
        card_id: card.card_id,
        title: card.title,
        card_type: card.card_type,
        status: card.status,
        linked_chunks: card.linked_chunks || [],
        content: cardExcerpt(card),
      })),
    }, null, 2);
  }
  if (format === "jsonld") {
    return JSON.stringify({
      "@context": {
        title: "https://schema.org/name",
        content: "https://schema.org/text",
        source_ref: "https://schema.org/citation",
      },
      "@graph": cards.map((card) => ({
        "@id": card.card_id,
        "@type": "WikiCard",
        title: card.title,
        card_type: card.card_type,
        content: cardExcerpt(card),
      })),
    }, null, 2);
  }
  if (format === "graphml") {
    const nodes = cards.map((card) => `    <node id="${card.card_id}"><data key="title">${card.title || card.card_id}</data></node>`).join("\n");
    return `<graphml>\n  <graph edgedefault="undirected">\n${nodes}\n  </graph>\n</graphml>`;
  }
  if (format === "llms") {
    return [
      "# 航空维修知识库",
      "",
      `> 已选 Wiki 卡片 ${total} 张`,
      "",
      ...cards.flatMap((card) => [
        `## ${card.title || card.card_id}`,
        cardExcerpt(card),
        "",
      ]),
    ].join("\n");
  }
  if (format === "marp") {
    return [
      "---",
      "marp: true",
      "paginate: true",
      "---",
      "# 航空维修知识库导出",
      "",
      ...cards.flatMap((card) => [
        "---",
        `## ${card.title || card.card_id}`,
        cardExcerpt(card),
        "",
      ]),
    ].join("\n");
  }
  return cards.map((card) => [
    `## ${card.title || card.card_id}`,
    "",
    cardExcerpt(card),
  ].join("\n")).join("\n\n");
}

async function doExport() {
  if (selectedCardIds.value.size === 0) {
    error.value = "请至少选择一张卡片";
    return;
  }
  exporting.value = true;
  error.value = null;
  exportedContent.value = null;
  copied.value = false;
  try {
    const ids = Array.from(selectedCardIds.value);
    const content = await exportWiki(selectedFormat.value, ids);
    exportedContent.value = normalizeExportContent(content, selectedFormat.value);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    exporting.value = false;
  }
}

function downloadContent() {
  const content = effectiveContent.value;
  if (!content) return;
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const ext = selectedFormat.value === "markdown" ? "md" : selectedFormat.value === "marp" ? "md" : "txt";
  a.download = `wiki-export-${selectedFormat.value}-${Date.now()}.${ext}`;
  a.click();
  URL.revokeObjectURL(url);
}

function copyContent() {
  const content = effectiveContent.value;
  if (!content) return;
  navigator.clipboard.writeText(content);
  copied.value = true;
  window.setTimeout(() => {
    copied.value = false;
  }, 1600);
}

function normalizeExportContent(content: string, format: FormatKey): string {
  if (format !== "markdown") return content;
  return content
    .replace(/(##\s+[^\n#\[]+)(\[\/\/\]:)/g, "$1\n\n$2")
    .replace(/(\))(?=###\s+)/g, "$1\n\n")
    .replace(/(###\s+[^\n-]+)(?=-\s+)/g, "$1\n\n")
    .replace(/([^#\n])(?=##\s+)/g, "$1\n\n")
    .replace(/([。；;])(?=-\s+)/g, "$1\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

onMounted(() => {
  void loadExportScope();
});
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-3 px-6 pb-5 pt-4">
    <div v-if="error" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">{{ error }}</div>

    <section class="export-toolbar mt-4 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div class="export-toolbar-row">
        <div class="export-toolbar-main">
          <div class="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <AppIcon name="download" class="h-4 w-4 text-slate-500" />
            导出格式
          </div>
          <div class="export-format-tabs" role="tablist" aria-label="导出格式">
            <button
              v-for="f in formats"
              :key="f.key"
              @click="selectFormat(f.key)"
              class="export-format-tab"
              :class="selectedFormat === f.key ? 'is-active' : ''"
              role="tab"
              :aria-selected="selectedFormat === f.key"
              :title="f.desc"
            >
              {{ f.label }}
            </button>
          </div>
          <span class="text-xs text-slate-500">{{ selectedMeta.desc }}</span>
          <button
            @click="showCardSelector = !showCardSelector"
            class="inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs font-medium transition-colors"
            :class="showCardSelector ? 'border-blue-300 bg-blue-50 text-blue-700' : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100'"
          >
            <AppIcon name="layers" class="h-3.5 w-3.5" />
            {{ selectAll && selectedCardIds.size === exportTotal ? '全部已通过' : `已选 ${selectedCardIds.size} 张` }}
          </button>
        </div>
        <div class="export-toolbar-actions">
          <div class="export-stats text-xs">
            <div class="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5">
              <span class="text-slate-500">范围</span>
              <span class="ml-2 font-semibold text-slate-900">{{ selectedCardIds.size }}</span>
            </div>
            <div class="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5">
              <span class="text-slate-500">大小</span>
              <span class="ml-2 font-semibold text-slate-900">{{ contentSize }}</span>
            </div>
            <div class="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5">
              <span class="text-slate-500">行数</span>
              <span class="ml-2 font-semibold text-slate-900">{{ lineCount }}</span>
            </div>
          </div>
        <button
          @click="doExport"
          :disabled="exporting || selectedCardIds.size === 0"
            class="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-slate-800 disabled:opacity-60"
        >
          <AppIcon name="download" class="h-4 w-4" />
          {{ exporting ? "导出中..." : "开始导出" }}
        </button>
        </div>
      </div>
    </section>

    <section v-if="showCardSelector" class="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
      <div class="flex items-center justify-between border-b border-slate-200 bg-slate-50/70 px-5 py-3">
        <div class="flex items-center gap-3">
          <label class="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              :checked="selectAll"
              @change="toggleSelectAll"
              class="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            <span class="text-sm font-medium text-slate-700">全选</span>
          </label>
          <span class="text-xs text-slate-500">已选 {{ selectedCardIds.size }} / {{ exportTotal }} 张</span>
        </div>
        <button
          @click="showCardSelector = false"
          class="text-xs text-slate-500 hover:text-slate-700"
        >
          收起选择
        </button>
      </div>
      <div class="max-h-80 overflow-y-auto p-3">
        <div v-if="scopeLoading" class="py-8 text-center text-sm text-slate-400">加载中...</div>
        <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          <label
            v-for="card in allCards"
            :key="card.card_id"
            class="flex items-start gap-2 rounded-lg border p-2.5 cursor-pointer transition-colors"
            :class="selectedCardIds.has(card.card_id) ? 'border-blue-300 bg-blue-50/50' : 'border-slate-200 bg-white hover:bg-slate-50'"
          >
            <input
              type="checkbox"
              :checked="selectedCardIds.has(card.card_id)"
              @change="toggleCard(card.card_id)"
              class="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
            />
            <div class="min-w-0">
              <div class="text-sm font-medium text-slate-800 truncate" :title="card.title || card.card_id">
                {{ card.title || card.card_id }}
              </div>
              <div class="text-xs text-slate-500 mt-0.5 line-clamp-2">{{ cardExcerpt(card) }}</div>
            </div>
          </label>
        </div>
      </div>
    </section>

    <section v-else class="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div class="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div class="flex min-w-0 items-center gap-3">
          <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-500">
            <AppIcon name="layers" class="h-4 w-4" />
          </div>
          <div class="min-w-0">
            <div class="text-sm font-semibold text-slate-900">导出范围</div>
            <div class="mt-0.5 text-xs text-slate-500">{{ scopeSummary }}</div>
          </div>
        </div>
        <div class="flex min-w-0 flex-wrap gap-2">
          <span
            v-for="card in previewCards"
            :key="card.card_id"
            class="max-w-[220px] truncate rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700"
            :title="card.title || card.card_id"
          >
            {{ card.title || card.card_id }}
          </span>
          <span v-if="!scopeLoading && selectedCardIds.size > previewCards.length" class="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-500">
            另 {{ selectedCardIds.size - previewCards.length }} 张
          </span>
          <span v-if="!scopeLoading && selectedCardIds.size === 0" class="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs text-amber-700">
            请选择要导出的卡片
          </span>
        </div>
      </div>
    </section>

    <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div class="flex flex-col gap-3 border-b border-slate-200 bg-slate-50/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div class="text-sm font-semibold text-slate-900">导出预览</div>
          <div class="mt-1 text-xs text-slate-500">
            {{ isPreviewExported ? `已生成 ${selectedMeta.label}，共 ${lineCount} 行` : `${selectedMeta.label} 预览（基于选中卡片，点击开始导出可获取完整内容）` }}
          </div>
        </div>
        <div class="flex gap-2">
          <button
            @click="copyContent"
            :disabled="!effectiveContent"
            class="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <AppIcon name="copy" class="h-4 w-4" />
            {{ copied ? "已复制" : "复制" }}
          </button>
          <button
            @click="downloadContent"
            :disabled="!effectiveContent"
            class="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <AppIcon name="download" class="h-4 w-4" />
            下载
          </button>
        </div>
      </div>

      <div v-if="exporting" class="flex min-h-[220px] items-center justify-center text-sm font-medium text-slate-500">
        正在生成导出内容...
      </div>
      <div v-else class="bg-slate-950 p-4">
        <pre class="max-h-[480px] overflow-auto whitespace-pre-wrap text-xs leading-6 text-slate-200">{{ previewLines.join('\n') }}</pre>
        <div v-if="!isPreviewExported && selectedCardIds.size > previewCards.length" class="mt-3 border-t border-slate-800 pt-3 text-xs text-slate-400">
          当前为预览模式，仅展示前 {{ previewCards.length }} 张卡片内容。点击"开始导出"可生成全部 {{ selectedCardIds.size }} 张卡片的完整内容。
        </div>
        <div v-else-if="lineCount > 200" class="mt-3 border-t border-slate-800 pt-3 text-xs text-slate-400">
          共 {{ lineCount }} 行，仅显示前 200 行。
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.export-toolbar-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) max-content;
  align-items: center;
  gap: 0.75rem;
}

.export-toolbar-main,
.export-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.export-toolbar-main {
  min-width: 0;
  flex-wrap: wrap;
}

.export-toolbar-actions {
  justify-content: flex-end;
  flex-wrap: wrap;
}

.export-stats {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.export-format-tabs {
  display: inline-flex;
  width: max-content;
  max-width: min(100%, 34rem);
  overflow-x: auto;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  background: #f8fafc;
  padding: 0.1875rem;
  scrollbar-width: thin;
}

.export-format-tab {
  height: 1.875rem;
  white-space: nowrap;
  border: 1px solid #e2e8f0;
  border-color: transparent;
  border-radius: 0.375rem;
  padding: 0 0.65rem;
  color: #475569;
  font-size: 0.75rem;
  font-weight: 600;
  line-height: 1;
  transition: background-color 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
}

.export-format-tab:hover {
  background: #ffffff;
  color: #0f172a;
}

.export-format-tab.is-active {
  border: 1px solid #e2e8f0;
  background: #ffffff;
  color: #111827;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.08);
}

@media (max-width: 1180px) {
  .export-toolbar-row {
    grid-template-columns: 1fr;
  }

  .export-toolbar-main,
  .export-toolbar-actions {
    flex-wrap: wrap;
  }

  .export-toolbar-actions {
    justify-content: flex-start;
  }
}
</style>
