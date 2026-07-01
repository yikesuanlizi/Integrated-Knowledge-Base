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
const exportCards = ref<WikiCardInfo[]>([]);
const exportTotal = ref(0);

const selectedMeta = computed(() => formats.find((item) => item.key === selectedFormat.value) || formats[0]);
const previewLines = computed(() => exportedContent.value?.split("\n").slice(0, 80) || []);
const lineCount = computed(() => exportedContent.value?.split("\n").length || 0);
const scopeSummary = computed(() => {
  if (scopeLoading.value && exportTotal.value === 0) return "加载中";
  return `${exportTotal.value.toLocaleString()} 张已通过 Wiki 卡片`;
});
const scopePreviewCards = computed(() => exportCards.value.slice(0, 6));
const draftPreview = computed(() => buildDraftPreview(selectedFormat.value, scopePreviewCards.value, exportTotal.value));
const draftPreviewLines = computed(() => draftPreview.value.split("\n").slice(0, 80));
const contentSize = computed(() => {
  if (!exportedContent.value) return "0 KB";
  const bytes = new Blob([exportedContent.value]).size;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
});

function selectFormat(format: FormatKey) {
  if (selectedFormat.value === format) return;
  selectedFormat.value = format;
  exportedContent.value = null;
  copied.value = false;
}

async function loadExportScope(force = false) {
  scopeLoading.value = true;
  try {
    const page = await listWikiCards(1, 6, undefined, "approved", force);
    exportCards.value = page.cards;
    exportTotal.value = page.total;
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    scopeLoading.value = false;
  }
}

function cardExcerpt(card: WikiCardInfo) {
  return (card.content || card.source_ref || card.card_id).replace(/\s+/g, " ").slice(0, 180);
}

function buildDraftPreview(format: FormatKey, cards: WikiCardInfo[], total: number) {
  if (!cards.length) return "暂无可导出内容";
  if (format === "json") {
    return JSON.stringify({
      export_scope: "approved_wiki_cards",
      total,
      preview_cards: cards.map((card) => ({
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
      "# 航空知识库",
      "",
      `> 已通过 Wiki 卡片 ${total} 张`,
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
      "# 航空知识库导出",
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
  exporting.value = true;
  error.value = null;
  exportedContent.value = null;
  copied.value = false;
  try {
    const content = await exportWiki(selectedFormat.value);
    exportedContent.value = normalizeExportContent(content, selectedFormat.value);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    exporting.value = false;
  }
}

function downloadContent() {
  if (!exportedContent.value) return;
  const blob = new Blob([exportedContent.value], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `wiki-export-${selectedFormat.value}-${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

function copyContent() {
  if (!exportedContent.value) return;
  navigator.clipboard.writeText(exportedContent.value);
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
          <span class="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700">
            全部已通过
          </span>
        </div>
        <div class="export-toolbar-actions">
          <div class="export-stats text-xs">
            <div class="rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5">
              <span class="text-slate-500">范围</span>
              <span class="ml-2 font-semibold text-slate-900">{{ exportTotal }}</span>
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
          :disabled="exporting"
            class="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-slate-800 disabled:opacity-60"
        >
          <AppIcon name="download" class="h-4 w-4" />
          {{ exporting ? "导出中..." : "开始导出" }}
        </button>
        </div>
      </div>
    </section>

    <section class="rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
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
            v-for="card in scopePreviewCards"
            :key="card.card_id"
            class="max-w-[220px] truncate rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700"
            :title="card.title || card.card_id"
          >
            {{ card.title || card.card_id }}
          </span>
          <span v-if="!scopeLoading && exportTotal > scopePreviewCards.length" class="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-500">
            另 {{ exportTotal - scopePreviewCards.length }} 张
          </span>
          <span v-if="!scopeLoading && exportTotal === 0" class="rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs text-amber-700">
            暂无可导出卡片
          </span>
        </div>
      </div>
    </section>

    <section class="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div class="flex flex-col gap-3 border-b border-slate-200 bg-slate-50/70 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div class="text-sm font-semibold text-slate-900">导出预览</div>
          <div class="mt-1 text-xs text-slate-500">{{ exportedContent ? `已生成 ${selectedMeta.label}，共 ${lineCount} 行` : `${selectedMeta.label} 预览 · ${scopeSummary}` }}</div>
        </div>
        <div class="flex gap-2">
          <button
            @click="copyContent"
            :disabled="!exportedContent"
            class="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <AppIcon name="copy" class="h-4 w-4" />
            {{ copied ? "已复制" : "复制" }}
          </button>
          <button
            @click="downloadContent"
            :disabled="!exportedContent"
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
      <div v-else-if="exportedContent" class="bg-slate-950 p-4">
        <pre class="max-h-[420px] overflow-auto whitespace-pre-wrap text-xs leading-6 text-slate-200">{{ previewLines.join('\n') }}</pre>
        <div v-if="lineCount > 80" class="mt-3 border-t border-slate-800 pt-3 text-xs text-slate-400">
          共 {{ lineCount }} 行，仅显示前 80 行。
        </div>
      </div>
      <div v-else class="bg-slate-950 p-4">
        <pre class="max-h-[420px] min-h-[220px] overflow-auto whitespace-pre-wrap text-xs leading-6 text-slate-200">{{ draftPreviewLines.join('\n') }}</pre>
      </div>
    </section>
  </div>
</template>

<style scoped>
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
}

.export-toolbar-actions {
  justify-content: flex-end;
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
