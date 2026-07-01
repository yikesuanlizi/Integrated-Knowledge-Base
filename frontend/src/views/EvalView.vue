<script setup lang="ts">
import { ref } from "vue";
import { runEval } from "@/api/client";
import type { EvalResult } from "@/types";
import RetrievalEvalPanel from "@/components/RetrievalEvalPanel.vue";
import AppIcon from "@/components/AppIcon.vue";

const results = ref<Record<string, EvalResult>>({});
const running = ref(false);
const error = ref<string | null>(null);

const kinds = [
  { key: "health", label: "知识库健康度", icon: "💪" },
  { key: "citation", label: "引用覆盖率", icon: "📎" },
  { key: "retrieval", label: "检索精度", icon: "🎯" },
  { key: "evidence", label: "证据链完整性", icon: "🧩" },
  { key: "full", label: "综合评测" },
];

async function doRun(kind: string) {
  running.value = true;
  error.value = null;
  try {
    results.value[kind] = await runEval(kind as any);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    running.value = false;
  }
}

function scoreColor(score: number): string {
  if (score >= 0.8) return "bg-blue-600";
  if (score >= 0.6) return "bg-amber-500";
  return "bg-red-500";
}

function scoreBg(score: number): string {
  if (score >= 0.8) return "bg-blue-600";
  if (score >= 0.6) return "bg-amber-500";
  return "bg-red-500";
}
</script>

<template>
  <div class="mx-auto max-w-5xl">
    <div class="mb-4">
      <h2 class="text-lg font-semibold text-slate-800 flex items-center gap-2">
        <span class="text-lg">评测仪表盘</span>
      </h2>
    </div>

    <div v-if="error" class="mb-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">{{ error }}</div>

    <!-- 评测快捷按钮 -->
    <div class="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
      <button
        v-for="k in kinds"
        :key="k.key"
        @click="doRun(k.key)"
        :disabled="running"
        class="rounded-lg border border-slate-200 bg-white p-2.5 hover:border-blue-400 transition-colors text-left disabled:opacity-60"
      >
        <div class="text-slate-400 mb-1" v-if="k.icon">
          <AppIcon name="line-chart" class="h-5 w-5" />
        </div>
        <div class="text-xs font-medium text-slate-800">{{ k.label }}</div>
      </button>
    </div>

    <!-- 结果展示 -->
    <div v-if="results['full'] || Object.keys(results).length > 0" class="space-y-4">
      <div v-for="k in kinds" :key="k.key" v-show="results[k.key]" class="rounded-lg border border-slate-200 bg-white p-4">
          <div class="flex items-center gap-2 mb-3">
            <AppIcon name="line-chart" class="h-5 w-5 text-slate-500" />
            <h3 class="text-sm font-semibold text-slate-800">{{ k.label }}</h3>
          </div>

        <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-4">
          <div v-for="(metric, mi) in [
            { key: 'health_score', label: '健康分数' },
            { key: 'citation_coverage', label: '引用覆盖率' },
            { key: 'retrieval_precision', label: '检索精度' },
            { key: 'evidence_completeness', label: '证据完整性' },
          ]" :key="mi">
            <div class="flex items-center justify-between mb-1">
              <span class="text-xs font-medium text-slate-700">{{ metric.label }}</span>
              <span class="text-xs font-semibold" :class="(results[k.key] as any)[metric.key] >= 0.8 ? 'text-blue-800' : (results[k.key] as any)[metric.key] >= 0.6 ? 'text-amber-800' : 'text-red-800'">
                {{ ((results[k.key] as any)[metric.key] * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="text-base font-semibold text-slate-800 mb-1">{{ ((results[k.key] as any)[metric.key] * 100).toFixed(1) }}%</div>
            <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div class="h-full rounded-full transition-all" :class="scoreBg((results[k.key] as any)[metric.key])" :style="{ width: ((results[k.key] as any)[metric.key] * 100) + '%' }"></div>
            </div>
          </div>
        </div>

        <div v-if="results[k.key].report" class="rounded-lg bg-slate-50 border border-slate-100 p-3 text-xs font-mono text-slate-700 whitespace-pre-wrap">
          {{ results[k.key].report }}
        </div>
      </div>
    </div>

    <div v-else class="py-16 text-center rounded-lg border border-slate-200 bg-white">
      <AppIcon name="line-chart" class="h-10 w-10 mx-auto text-slate-300" />
      <div class="text-sm font-semibold text-slate-800 mb-1">暂无评测结果</div>
      <div class="text-xs text-slate-600">点击上方按钮运行评测。</div>
    </div>

    <div class="mt-8">
      <RetrievalEvalPanel />
    </div>
  </div>
</template>
