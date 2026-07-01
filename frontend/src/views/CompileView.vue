<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { getCompileStatus, getIngestStatus, listWikiCards, listDocuments } from "@/api/client";
import type { CompileStatus, IngestStatus, WikiCardInfo, DocumentItem } from "@/types";
import AppIcon from "@/components/AppIcon.vue";

type CardStatusFilter = "all" | "approved" | "review" | "rejected";

const loading = ref(false);
const error = ref<string | null>(null);
const ingestStatus = ref<IngestStatus | null>(null);
const latestDocument = ref<DocumentItem | null>(null);
const compileStatus = ref<CompileStatus | null>(null);
const cards = ref<WikiCardInfo[]>([]);
const statusFilter = ref<CardStatusFilter>("all");
const currentPage = ref(1);
const pageSize = 6;

const latestBuildId = computed(() => latestDocument.value?.doc_id?.split(":")[0] || "");
const approvedCards = computed(() => cards.value.filter((card) => card.status === "approved"));
const reviewCards = computed(() => cards.value.filter((card) => card.status === "review"));
const rejectedCards = computed(() => cards.value.filter((card) => card.status === "rejected"));

const filterTabs = computed(() => [
  { key: "all" as CardStatusFilter, label: "全部卡片", count: cards.value.length },
  { key: "approved" as CardStatusFilter, label: "已自动通过", count: approvedCards.value.length },
  { key: "review" as CardStatusFilter, label: "待人工复核", count: reviewCards.value.length },
  { key: "rejected" as CardStatusFilter, label: "已驳回", count: rejectedCards.value.length },
]);

const filteredCards = computed(() => {
  if (statusFilter.value === "approved") return approvedCards.value;
  if (statusFilter.value === "review") return reviewCards.value;
  if (statusFilter.value === "rejected") return rejectedCards.value;
  return cards.value;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredCards.value.length / pageSize)));
const pagedCards = computed(() => {
  const start = (currentPage.value - 1) * pageSize;
  return filteredCards.value.slice(start, start + pageSize);
});

const compileMetrics = computed(() => [
  { label: "Milvus 原文切片", value: ingestStatus.value?.milvus_chunks ?? 0, tone: "slate" },
  { label: "ES 原文切片", value: ingestStatus.value?.elasticsearch_chunks ?? 0, tone: "slate" },
  { label: "PG 文档数", value: ingestStatus.value?.documents ?? 0, tone: "slate" },
  { label: "PG 切片数", value: ingestStatus.value?.pg_chunks ?? 0, tone: "slate" },
  { label: "卡片总数", value: cards.value.length, tone: "slate" },
  { label: "自动通过", value: approvedCards.value.length, tone: "blue" },
  { label: "待人工复核", value: reviewCards.value.length, tone: "amber" },
  { label: "已驳回", value: rejectedCards.value.length, tone: "rose" },
]);

const logLines = computed(() => [
  `[ingest] 批次：${latestBuildId.value || "暂无"}`,
  `[chunk] 原文切片：${ingestStatus.value?.pg_chunks ?? 0}`,
  `[index] Milvus=${ingestStatus.value?.milvus_chunks ?? 0} / ES=${ingestStatus.value?.elasticsearch_chunks ?? 0}`,
  `[compile] 状态：${formatStatus(compileStatus.value?.status)}`,
  `[wiki] 卡片总数：${cards.value.length}`,
  `[review] 自动通过=${approvedCards.value.length} / 待复核=${reviewCards.value.length} / 已驳回=${rejectedCards.value.length}`,
]);

watch(statusFilter, () => {
  currentPage.value = 1;
});

watch(totalPages, (value) => {
  if (currentPage.value > value) currentPage.value = value;
});

function formatStatus(status?: string) {
  if (status === "completed") return "已完成";
  if (status === "pending") return "等待中";
  if (status === "failed") return "失败";
  if (status === "no_chunks") return "无可编译切片";
  if (status === "no_pages") return "未生成卡片";
  return status || "未知";
}

function cardTypeLabel(cardType: string) {
  if (cardType === "definition") return "定义";
  if (cardType === "concept") return "概念";
  if (cardType === "procedure") return "流程";
  if (cardType === "faq") return "问答";
  if (cardType === "fault") return "故障";
  return cardType;
}

function statusClass(status: string) {
  if (status === "approved") return "border-blue-200 bg-blue-50 text-blue-700";
  if (status === "review") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "rejected") return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function metricToneClass(tone: string) {
  if (tone === "blue") return "border-blue-200 bg-blue-50 text-blue-800";
  if (tone === "amber") return "border-amber-200 bg-amber-50 text-amber-800";
  if (tone === "rose") return "border-rose-200 bg-rose-50 text-rose-800";
  return "border-slate-200 bg-slate-50 text-slate-900";
}

function changePage(next: number) {
  if (next < 1 || next > totalPages.value) return;
  currentPage.value = next;
}

async function refresh(force = false) {
  loading.value = true;
  error.value = null;
  try {
    ingestStatus.value = await getIngestStatus(force);
    const documents = await listDocuments("", 1, 1);
    latestDocument.value = documents.documents[0] || null;

    if (latestBuildId.value) {
      compileStatus.value = await getCompileStatus(latestBuildId.value);
      const wiki = await listWikiCards(1, 200, undefined, undefined);
      cards.value = wiki.cards
        .filter((card) => card.build_id === latestBuildId.value)
        .sort((a, b) => {
          const order = { review: 0, rejected: 1, approved: 2 } as Record<string, number>;
          return (order[a.status] ?? 9) - (order[b.status] ?? 9);
        });
    } else {
      compileStatus.value = null;
      cards.value = [];
    }
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

onMounted(refresh);
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-4 px-6 py-3">
    <div class="flex justify-end">
      <button
        @click="refresh(true)"
        :disabled="loading"
        class="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
      >
        <AppIcon name="refresh-cw" class="h-4 w-4" />
        <span>{{ loading ? "刷新中..." : "刷新状态" }}</span>
      </button>
    </div>

    <div v-if="error" class="rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
      {{ error }}
    </div>

    <div class="compile-layout">
      <aside class="compile-sidebar space-y-4">
        <section class="rounded-xl border border-slate-200 bg-white p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <div class="text-xs font-medium text-slate-500">当前批次</div>
              <div class="mt-1 font-mono text-sm text-slate-800">{{ latestBuildId || "尚无批次" }}</div>
            </div>
            <span class="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-700">
              {{ formatStatus(compileStatus?.status) }}
            </span>
          </div>
          <div class="mt-4">
            <div class="mb-2 flex items-center justify-between text-[11px] text-slate-500">
              <span>文档摄入</span>
              <span>自动编译</span>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-slate-100">
              <div class="h-full w-full bg-indigo-500"></div>
            </div>
          </div>
        </section>

        <section class="rounded-xl border border-slate-200 bg-white p-4">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-slate-800">概览</h3>
            <span class="text-[11px] text-slate-500">左侧速览</span>
          </div>
          <div class="grid gap-2">
            <div
              v-for="metric in compileMetrics"
              :key="metric.label"
              class="flex items-center justify-between rounded-lg border px-3 py-2.5"
              :class="metricToneClass(metric.tone)"
            >
              <span class="text-[11px] font-medium">{{ metric.label }}</span>
              <span class="text-base font-semibold">{{ metric.value }}</span>
            </div>
          </div>
        </section>

        <section class="rounded-xl border border-slate-200 bg-white p-4">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-slate-800">编译日志</h3>
            <span class="text-[11px] text-slate-500">只读</span>
          </div>
          <div class="space-y-2 rounded-lg bg-slate-950 p-3 font-mono text-[11px] leading-5 text-slate-200">
            <div v-for="line in logLines" :key="line">{{ line }}</div>
          </div>
        </section>
      </aside>

      <section class="compile-main rounded-xl border border-slate-200 bg-white">
        <div class="border-b border-slate-200 px-5 py-4">
          <div class="compile-toolbar flex flex-col gap-4">
            <div>
              <h3 class="text-sm font-semibold text-slate-800">卡片与来源切片</h3>
            </div>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="tab in filterTabs"
                :key="tab.key"
                @click="statusFilter = tab.key"
                class="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium transition-colors"
                :class="statusFilter === tab.key ? 'border-indigo-500 bg-indigo-50 text-indigo-700' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'"
              >
                <span>{{ tab.label }}</span>
                <span class="rounded-full bg-white/80 px-1.5 py-0.5 text-[10px] text-current">{{ tab.count }}</span>
              </button>
            </div>
          </div>
        </div>

        <div v-if="filteredCards.length === 0" class="p-10">
          <div class="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-12 text-center text-sm text-slate-500">
            当前筛选下没有 Wiki 卡片。
          </div>
        </div>

        <div v-else class="p-5">
          <div class="compile-card-grid grid grid-cols-1 gap-4">
            <article
              v-for="card in pagedCards"
              :key="card.card_id"
              class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                      {{ cardTypeLabel(card.card_type) }}
                    </span>
                    <span class="rounded-full border px-2 py-0.5 text-[11px] font-medium" :class="statusClass(card.status)">
                      {{ card.status === "approved" ? "已自动通过" : card.status === "review" ? "待人工复核" : "已驳回" }}
                    </span>
                  </div>
                  <h4 class="mt-2 text-sm font-semibold text-slate-900">{{ card.title }}</h4>
                  <p class="mt-2 line-clamp-3 text-xs leading-6 text-slate-600">{{ card.content }}</p>
                </div>
              </div>

              <div class="mt-4 grid gap-3 lg:grid-cols-[minmax(0,1fr)_200px]">
                <div class="rounded-lg bg-slate-50 p-3">
                  <div class="text-[11px] font-medium text-slate-600">来源引用</div>
                  <div class="mt-1 break-all text-xs text-slate-800">{{ card.source_ref }}</div>
                </div>
                <div class="rounded-lg bg-slate-50 p-3">
                  <div class="text-[11px] font-medium text-slate-600">关联切片</div>
                  <div class="mt-1 text-xs text-slate-800">
                    <template v-if="card.linked_chunks?.length">
                      {{ card.linked_chunks.join("，") }}
                    </template>
                    <template v-else>
                      未关联
                    </template>
                  </div>
                </div>
              </div>
            </article>
          </div>

          <div class="mt-5 flex flex-col gap-3 border-t border-slate-200 pt-4 sm:flex-row sm:items-center sm:justify-between">
            <div class="text-xs text-slate-500">
              当前显示第 {{ currentPage }} / {{ totalPages }} 页，共 {{ filteredCards.length }} 张卡片
            </div>
            <div class="flex items-center gap-2">
              <button
                @click="changePage(currentPage - 1)"
                :disabled="currentPage === 1"
                class="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                上一页
              </button>
              <span class="text-sm text-slate-600">{{ currentPage }}</span>
              <button
                @click="changePage(currentPage + 1)"
                :disabled="currentPage >= totalPages"
                class="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.compile-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.25rem;
}

.compile-sidebar,
.compile-main {
  min-width: 0;
}

.compile-card-grid {
  grid-template-columns: minmax(0, 1fr);
}

@media (min-width: 1024px) {
  .compile-layout {
    grid-template-columns: minmax(260px, 0.95fr) minmax(0, 3.05fr);
    align-items: start;
  }

  .compile-toolbar {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
  }
}

@media (min-width: 1536px) {
  .compile-card-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
