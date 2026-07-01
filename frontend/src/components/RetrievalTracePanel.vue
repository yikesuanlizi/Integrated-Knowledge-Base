<script setup lang="ts">
import { computed } from "vue";
import type { RetrievalTrace, RetrievalTraceCandidate } from "@/types";

const props = defineProps<{ trace?: RetrievalTrace }>();

const channels = computed(() => Object.entries(props.trace?.channels || {}));
const selectedEvidence = computed(() => props.trace?.selected_evidence || []);
const maxHits = computed(() => Math.max(1, ...channels.value.map(([, channel]) => channel.hit_count || 0)));
const dedupedStages = computed(() => {
  const stages = props.trace?.stages || [];
  const seen = new Set<string>();
  const result: Array<Record<string, unknown>> = [];
  for (const stage of stages) {
    const key = [
      stage.name,
      stage.label,
      String(stage.hit_count ?? ""),
      String(stage.output_total ?? ""),
      String(stage.sufficient ?? ""),
      String(stage.score ?? ""),
    ].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(stage);
  }
  return result;
});

function pct(value?: number) {
  return `${Math.round((value || 0) * 100)}%`;
}

function width(count: number) {
  return `${Math.max(4, Math.round((count / maxHits.value) * 100))}%`;
}

function sourceLabel(sourceType: string) {
  const labels: Record<string, string> = {
    chunk: "原文",
    wiki_card: "Wiki",
    entity: "实体",
    structured_metadata: "结构化",
  };
  return labels[sourceType] || sourceType || "未知";
}

function candidateKey(item: RetrievalTraceCandidate, index: number) {
  return `${item.id || item.title || "candidate"}-${index}`;
}

function decisionText(decision?: Record<string, unknown> | null) {
  if (!decision) return "";
  return String(decision.reason || decision.source || "");
}

function stageValue(stage: Record<string, unknown>, key: string) {
  return stage[key];
}

function evidenceSufficient() {
  return Boolean(props.trace?.evidence_sufficiency?.sufficient);
}

function evidenceScore() {
  return Number(props.trace?.evidence_sufficiency?.score || 0);
}
</script>

<template>
  <section v-if="trace" class="mt-4 rounded-lg border border-slate-200 bg-white p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <div class="text-sm font-semibold text-slate-800">召回诊断</div>
        <div class="mt-1 text-xs font-medium text-slate-600">
          线上召回观测，不等同于黄金集召回率
        </div>
      </div>
      <div class="flex flex-wrap gap-2 text-xs font-medium">
        <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-800">
          Merge {{ trace.merged_count || 0 }}
        </span>
        <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-800">
          Rerank {{ trace.reranked_count || 0 }}
        </span>
        <span class="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-slate-800">
          Evidence {{ selectedEvidence.length }}
        </span>
      </div>
    </div>

    <div class="mt-4 grid gap-4 lg:grid-cols-[1fr_1fr]">
      <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div class="text-xs font-semibold uppercase tracking-wide text-slate-700">四路召回命中</div>
        <div class="mt-3 space-y-3">
          <div v-for="[key, channel] in channels" :key="key">
            <div class="mb-1 flex items-center justify-between text-xs font-medium text-slate-800">
              <span>{{ channel.label || key }}</span>
              <span>{{ channel.hit_count || 0 }}</span>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-white">
              <div class="h-full rounded-full bg-blue-600" :style="{ width: width(channel.hit_count || 0) }"></div>
            </div>
            <div v-if="channel.decision" class="mt-1 text-[11px] font-medium text-slate-700">
              {{ decisionText(channel.decision) }}
            </div>
            <div v-if="channel.error" class="mt-1 text-[11px] font-medium text-red-700">
              {{ channel.error }}
            </div>
          </div>
        </div>
      </div>

      <div class="rounded-lg border border-slate-200 bg-slate-50 p-4">
        <div class="text-xs font-semibold uppercase tracking-wide text-slate-700">阶段流水</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <span
            v-for="stage in dedupedStages"
            :key="stage.name + String(stage.hit_count || stage.output_total || '')"
            class="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-800"
          >
            {{ stage.label }}
            <span v-if="stageValue(stage, 'hit_count') !== undefined" class="text-slate-600">· {{ stageValue(stage, 'hit_count') }}</span>
            <span v-else-if="stageValue(stage, 'output_total') !== undefined" class="text-slate-600">· {{ stageValue(stage, 'output_total') }}</span>
          </span>
        </div>
        <div v-if="trace.evidence_sufficiency" class="mt-4 grid grid-cols-2 gap-2 text-xs">
          <div class="rounded-lg border border-slate-200 bg-white p-3">
            <div class="font-medium text-slate-700">证据充分性</div>
            <div class="mt-1 font-semibold text-slate-900">{{ evidenceSufficient() ? "充分" : "不足" }}</div>
          </div>
          <div class="rounded-lg border border-slate-200 bg-white p-3">
            <div class="font-medium text-slate-700">充分性得分</div>
            <div class="mt-1 font-semibold text-slate-900">{{ pct(evidenceScore()) }}</div>
          </div>
        </div>
      </div>
    </div>

    <details class="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4">
      <summary class="cursor-pointer text-sm font-semibold text-slate-800">候选与最终证据</summary>
      <div class="mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-700">Rerank 前候选</div>
          <div class="space-y-2">
            <template v-for="[key, channel] in channels" :key="key">
              <div
                v-for="(candidate, idx) in channel.top_candidates || []"
                :key="candidateKey(candidate, idx)"
                class="rounded-lg border p-3 text-xs"
                :class="candidate.selected ? 'border-blue-300 bg-blue-50' : 'border-slate-200 bg-white'"
              >
                <div class="flex items-start justify-between gap-2">
                  <div class="font-semibold text-slate-900">{{ candidate.title || candidate.id }}</div>
                  <div class="shrink-0 font-medium text-slate-700">{{ pct(candidate.score) }}</div>
                </div>
                <div class="mt-1 font-medium text-slate-700">
                  {{ sourceLabel(candidate.source_type) }} · {{ candidate.status || "approved" }} · {{ candidate.freshness || "current" }}
                </div>
                <div v-if="candidate.snippet" class="mt-2 leading-5 text-slate-700">{{ candidate.snippet }}</div>
              </div>
            </template>
          </div>
        </div>

        <div>
          <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-700">最终 Evidence Pack</div>
          <div v-if="selectedEvidence.length === 0" class="rounded-lg border border-slate-200 bg-white p-6 text-center text-sm font-medium text-slate-700">
            暂无最终证据。
          </div>
          <div v-else class="space-y-2">
            <div
              v-for="(item, idx) in selectedEvidence"
              :key="candidateKey(item, idx)"
              class="rounded-lg border border-slate-200 bg-white p-3 text-xs"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="font-semibold text-slate-900">{{ item.title || item.id }}</div>
                <div class="shrink-0 font-medium text-slate-700">{{ pct(item.score) }}</div>
              </div>
              <div class="mt-1 font-medium text-slate-700">
                {{ sourceLabel(item.source_type) }} · {{ item.status || "approved" }}
              </div>
              <div v-if="item.snippet" class="mt-2 leading-5 text-slate-700">{{ item.snippet }}</div>
            </div>
          </div>
        </div>
      </div>
    </details>
  </section>
</template>
