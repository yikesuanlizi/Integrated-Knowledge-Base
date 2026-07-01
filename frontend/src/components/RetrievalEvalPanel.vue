<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getEvalFixtures, getLatestRetrievalReport, listRetrievalReports, runGoldenRetrievalEval } from "@/api/client";
import type { EvalFixturesResponse, GoldenRetrievalCase, GoldenRetrievalReport } from "@/types";

const latest = ref<GoldenRetrievalReport | null>(null);
const reports = ref<GoldenRetrievalReport[]>([]);
const fixtures = ref<EvalFixturesResponse | null>(null);
const loading = ref(false);
const fixtureLoading = ref(false);
const error = ref<string | null>(null);

const trend = computed(() => reports.value.slice(0, 8).reverse());
const goldenJson = computed(() => JSON.stringify(fixtures.value?.retrieval_cases || [], null, 2));

function pct(value?: number) {
  return `${(((value || 0) * 100)).toFixed(1)}%`;
}

function barWidth(value?: number) {
  return `${Math.max(3, Math.round((value || 0) * 100))}%`;
}

function metricValue(report: GoldenRetrievalReport, key: string) {
  return Number((report as unknown as Record<string, unknown>)[key] || 0);
}

function hitChannels(row: Record<string, unknown>) {
  const channels = row.hit_channels;
  return Array.isArray(channels) ? channels.join("、") : "";
}

async function refreshReports() {
  const [latestReport, history] = await Promise.all([getLatestRetrievalReport(), listRetrievalReports()]);
  latest.value = latestReport;
  reports.value = history;
}

async function refreshFixtures() {
  fixtureLoading.value = true;
  try {
    fixtures.value = await getEvalFixtures();
  } finally {
    fixtureLoading.value = false;
  }
}

async function runGoldenEval() {
  loading.value = true;
  error.value = null;
  try {
    const cases = fixtures.value?.retrieval_cases || [];
    if (!cases.length) throw new Error("当前固定测评集为空，请先导入样本文档或检查知识库数据。");
    latest.value = await runGoldenRetrievalEval(cases as GoldenRetrievalCase[], 10);
    await refreshReports();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void Promise.all([refreshReports(), refreshFixtures()]);
});
</script>

<template>
  <section class="space-y-5">
    <div class="rounded-xl border border-slate-200 bg-slate-50 p-5">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div class="text-base font-black text-slate-950">固定测评集召回率</div>
        </div>
        <div class="flex items-center gap-2">
          <button
            class="rounded-xl border border-slate-200 bg-white px-4 py-2 text-sm font-black text-slate-700 hover:bg-slate-50 disabled:bg-slate-100 disabled:text-slate-400"
            :disabled="fixtureLoading"
            @click="refreshFixtures"
          >
            {{ fixtureLoading ? "刷新题集中..." : "刷新题集" }}
          </button>
          <button
            class="rounded-xl bg-[#0b4ea2] px-4 py-2 text-sm font-black text-white hover:bg-[#073b7a] disabled:bg-slate-400"
            :disabled="loading || fixtureLoading"
            @click="runGoldenEval"
          >
            {{ loading ? "评测中" : "运行固定测评" }}
          </button>
        </div>
      </div>

      <div class="mt-4 grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div class="rounded-xl border border-slate-200 bg-white p-4">
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm font-black text-slate-900">试题清单</div>
            <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-[11px] font-black text-slate-700">
              {{ fixtures?.source === "corpus" ? "来自当前语料" : "回退样本" }}
            </span>
          </div>
          <div v-if="fixtureLoading" class="mt-4 text-sm text-slate-500">正在解析当前固定测评集...</div>
          <div v-else class="mt-4 space-y-2">
            <div
              v-for="item in fixtures?.retrieval_cases || []"
              :key="item.question"
              class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3"
            >
              <div class="text-sm font-semibold text-slate-900">{{ item.question }}</div>
              <div class="mt-1 text-[11px] text-slate-500">
                期望文档 {{ item.expected_doc_ids?.length || 0 }} / 切片 {{ item.expected_chunk_ids?.length || 0 }} / 卡片 {{ item.expected_card_ids?.length || 0 }}
              </div>
            </div>
            <div
              v-if="fixtures?.warnings?.length"
              class="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-6 text-amber-800"
            >
              {{ fixtures.warnings.join("；") }}
            </div>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-white p-4">
          <div class="flex items-center justify-between gap-3">
            <div class="text-sm font-black text-slate-900">标注命中目标</div>
            <span class="text-[11px] font-bold text-slate-500">doc / chunk / card</span>
          </div>
          <div class="mt-4 overflow-hidden rounded-xl border border-slate-200">
            <table class="min-w-full border-collapse text-xs">
              <thead class="bg-slate-50 text-slate-500">
                <tr>
                  <th class="border-b border-slate-200 px-3 py-2 text-left font-black">问题</th>
                  <th class="border-b border-slate-200 px-3 py-2 text-left font-black">文档</th>
                  <th class="border-b border-slate-200 px-3 py-2 text-left font-black">切片</th>
                  <th class="border-b border-slate-200 px-3 py-2 text-left font-black">卡片</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in fixtures?.retrieval_cases || []" :key="item.question" class="odd:bg-white even:bg-slate-50">
                  <td class="border-b border-slate-100 px-3 py-2 font-semibold text-slate-900">{{ item.question }}</td>
                  <td class="border-b border-slate-100 px-3 py-2 font-mono text-[11px] text-slate-600">{{ item.expected_doc_ids?.[0] || "-" }}</td>
                  <td class="border-b border-slate-100 px-3 py-2 font-mono text-[11px] text-slate-600">{{ item.expected_chunk_ids?.[0] || "-" }}</td>
                  <td class="border-b border-slate-100 px-3 py-2 font-mono text-[11px] text-slate-600">{{ item.expected_card_ids?.[0] || "-" }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <details class="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <summary class="cursor-pointer text-xs font-black text-slate-700">查看原始标注 JSON</summary>
            <pre class="mt-3 max-h-[240px] overflow-auto rounded-lg bg-slate-950 p-3 text-[11px] leading-6 text-slate-200">{{ goldenJson }}</pre>
          </details>
        </div>
      </div>

      <div v-if="error" class="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-bold text-red-700">{{ error }}</div>
    </div>

    <div v-if="latest" class="rounded-xl border border-slate-200 bg-white p-5">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div class="text-base font-black text-slate-950">最近一次评测</div>
          <div class="mt-1 text-xs font-bold text-slate-500">{{ latest.timestamp }} · {{ latest.total_queries }} 个问题</div>
        </div>
        <div class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-black text-slate-800">
          未命中 {{ latest.missed_count }}
        </div>
      </div>

      <div class="grid gap-3 sm:grid-cols-6">
        <div
          v-for="metric in [
            { key: 'recall_at_1', label: 'R@1' },
            { key: 'recall_at_3', label: 'R@3' },
            { key: 'recall_at_5', label: 'R@5' },
            { key: 'recall_at_10', label: 'R@10' },
            { key: 'mrr', label: 'MRR' },
            { key: 'hit_rate', label: '命中率' },
          ]"
          :key="metric.key"
          class="rounded-xl border border-slate-200 bg-slate-50 p-4"
        >
          <div class="text-xs font-black uppercase tracking-wide text-slate-500">{{ metric.label }}</div>
          <div class="mt-1 text-xl font-black text-slate-950">{{ pct(metricValue(latest, metric.key)) }}</div>
          <div class="mt-2 h-2 overflow-hidden rounded-full bg-white">
            <div class="h-full rounded-full bg-[#0b4ea2]" :style="{ width: barWidth(metricValue(latest, metric.key)) }"></div>
          </div>
        </div>
      </div>

      <div class="mt-5 grid gap-4 lg:grid-cols-2">
        <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div class="text-xs font-black uppercase tracking-wide text-slate-500">召回通道贡献</div>
          <div class="mt-3 flex flex-wrap gap-2">
            <span
              v-for="(count, channel) in latest.channel_contribution"
              :key="channel"
              class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-black text-slate-800"
            >
              {{ channel }} · {{ count }}
            </span>
          </div>
        </div>

        <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div class="text-xs font-black uppercase tracking-wide text-slate-500">最近趋势 R@5</div>
          <div class="mt-3 flex h-24 items-end gap-2">
            <div
              v-for="report in trend"
              :key="report.id"
              class="flex flex-1 flex-col items-center justify-end gap-1"
              :title="report.timestamp"
            >
              <div class="w-full rounded-t bg-[#0b4ea2]" :style="{ height: barWidth(report.recall_at_5) }"></div>
              <div class="text-[10px] font-black text-slate-500">{{ pct(report.recall_at_5) }}</div>
            </div>
          </div>
        </div>
      </div>

      <details class="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <summary class="cursor-pointer text-sm font-black text-slate-900">逐问题详情</summary>
        <div class="mt-3 overflow-x-auto">
          <table class="min-w-full border-collapse text-sm">
            <thead class="bg-white">
              <tr>
                <th class="border border-slate-200 px-3 py-2 text-left">问题</th>
                <th class="border border-slate-200 px-3 py-2 text-left">首个命中</th>
                <th class="border border-slate-200 px-3 py-2 text-left">R@10</th>
                <th class="border border-slate-200 px-3 py-2 text-left">通道</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in latest.details" :key="idx" class="odd:bg-white even:bg-slate-50">
                <td class="border border-slate-200 px-3 py-2 font-medium text-slate-900">{{ row.question }}</td>
                <td class="border border-slate-200 px-3 py-2 font-bold text-slate-700">{{ row.first_hit_rank || "-" }}</td>
                <td class="border border-slate-200 px-3 py-2 font-bold" :class="row.hit_at_10 ? 'text-blue-700' : 'text-red-700'">
                  {{ row.hit_at_10 ? "命中" : "未命中" }}
                </td>
                <td class="border border-slate-200 px-3 py-2 font-medium text-slate-700">{{ hitChannels(row) || "-" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
    </div>

    <div v-else class="rounded-xl border border-slate-200 bg-white p-10 text-center">
      <div class="text-base font-black text-slate-900">暂无固定测评报告</div>
      <div class="mt-1 text-sm font-medium text-slate-500">固定试题已经准备好，直接运行评测即可。</div>
    </div>
  </section>
</template>
