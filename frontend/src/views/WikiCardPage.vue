<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { getWikiCard, getWikiCardMarkdown } from "@/api/client";
import type { WikiCardInfo } from "@/types";

const route = useRoute();
const router = useRouter();
const cardId = route.params.card_id as string;

const card = ref<WikiCardInfo | null>(null);
const markdown = ref("");
const loading = ref(true);
const error = ref<string | null>(null);

const backTarget = computed(() => {
  const from = route.query.from;
  if (from === "graph") return { path: "/graph" };
  if (from === "wiki") return { path: "/wiki", query: { tab: route.query.tab || "cards" } };
  return null;
});

const backLabel = computed(() => {
  const from = route.query.from;
  if (from === "graph") return "返回知识图谱";
  return "返回 Wiki 卡片列表";
});

function cardTypeLabel(cardType: string): string {
  if (cardType === "definition") return "定义";
  if (cardType === "concept") return "概念";
  if (cardType === "procedure") return "流程";
  if (cardType === "faq") return "问答";
  if (cardType === "fault") return "故障";
  return cardType;
}

function statusLabel(status: string): string {
  if (status === "approved") return "已自动通过";
  if (status === "review") return "待人工复核";
  if (status === "rejected") return "已驳回";
  return status;
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    [card.value, markdown.value] = await Promise.all([
      getWikiCard(cardId),
      getWikiCardMarkdown(cardId).catch(() => ""),
    ]);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

function goBack() {
  if (backTarget.value) {
    router.push(backTarget.value);
    return;
  }
  if (window.history.length > 1) {
    router.back();
    return;
  }
  router.push({ path: "/wiki", query: { tab: "cards" } });
}

onMounted(load);
</script>

<template>
  <div class="mx-auto max-w-5xl">
    <button @click="goBack" class="mb-4 flex items-center gap-1 text-sm text-slate-700 hover:text-blue-700">
      ← {{ backLabel }}
    </button>

    <div v-if="loading" class="py-20 text-center text-slate-700">加载中...</div>
    <div v-else-if="error" class="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">{{ error }}</div>
    <div v-else-if="card" class="bg-white rounded-lg border border-slate-200 overflow-hidden">
      <div class="bg-slate-800 text-white p-4">
        <div class="mb-2 flex flex-wrap items-center gap-2 text-xs opacity-90">
          <span class="px-2 py-0.5 rounded bg-white/20">{{ cardTypeLabel(card.card_type) }}</span>
          <span>{{ statusLabel(card.status) }}</span>
          <span v-if="card.score !== undefined">相关度 {{ ((card.score ?? 0) * 100).toFixed(0) }}%</span>
        </div>
        <h1 class="text-lg font-semibold mb-1">{{ card.title }}</h1>
        <div class="text-xs opacity-80">
          来源: {{ card.source_ref }}
        </div>
      </div>

      <div class="grid grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_260px]">
        <div class="min-w-0">
          <div v-if="markdown" class="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
            {{ markdown }}
          </div>
          <div v-else class="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">
            {{ card.content }}
          </div>
        </div>

        <div class="space-y-3">
          <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div class="text-xs font-medium text-slate-600">卡片状态</div>
            <div class="mt-1 text-sm font-semibold text-slate-800">{{ statusLabel(card.status) }}</div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div class="text-xs font-medium text-slate-600">关联切片</div>
            <div class="mt-1 text-xs leading-6 text-slate-800">
              <template v-if="card.linked_chunks?.length">
                {{ card.linked_chunks.join("，") }}
              </template>
              <template v-else>
                暂无关联切片
              </template>
            </div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-slate-50 p-3">
            <div class="text-xs font-medium text-slate-600">卡片 ID</div>
            <div class="mt-1 break-all text-xs font-mono text-slate-800">{{ card.card_id }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
