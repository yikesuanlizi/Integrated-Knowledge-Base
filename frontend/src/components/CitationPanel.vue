<script setup lang="ts">
import type { Citation } from "@/types";

const props = defineProps<{
  citations: Citation[];
  activeId: number | null;
}>();

const emit = defineEmits<{
  select: [id: number];
}>();

function scoreColor(score: number): string {
  if (score >= 0.8) return "text-blue-800";
  if (score >= 0.6) return "text-amber-800";
  return "text-slate-700";
}
</script>

<template>
  <aside class="w-[420px] shrink-0 bg-white border-l border-slate-200 flex flex-col">
    <div class="h-12 border-b border-slate-200 px-4 flex items-center shrink-0">
      <span class="text-sm font-semibold text-slate-700">📎 证据面板</span>
      <span class="ml-2 text-xs text-slate-400">共 {{ citations.length }} 条</span>
    </div>

    <div class="flex-1 overflow-y-auto p-3 space-y-3">
      <div
        v-for="c in citations"
        :key="c.citation_id"
        @click="emit('select', c.citation_id)"
        class="p-3 rounded-lg border cursor-pointer transition-all hover:border-brand-300 hover:shadow-sm"
        :class="activeId === c.citation_id ? 'bg-brand-50 border-brand-400 shadow-sm' : 'bg-white border-slate-200'"
      >
        <div class="flex items-center gap-2 mb-2">
          <span class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-800 text-xs font-bold shrink-0">
            {{ c.citation_id }}
          </span>
          <span class="text-xs font-medium text-slate-700 truncate flex-1">{{ c.file_name }}</span>
          <span class="text-xs font-semibold" :class="scoreColor(c.score)">{{ (c.score * 100).toFixed(0) }}%</span>
        </div>

        <div v-if="c.section_path" class="text-[11px] text-slate-600 mb-2">
          📁 {{ c.section_path }}
          <span v-if="c.page_start" class="ml-2">p.{{ c.page_start }}{{ c.page_end && c.page_end !== c.page_start ? "-" + c.page_end : "" }}</span>
        </div>

        <p class="text-xs text-slate-700 leading-relaxed bg-slate-50 rounded p-2 border border-slate-100">
          {{ c.snippet || c.source_ref }}
        </p>

        <div class="mt-2 text-[10px] text-slate-500">
          chunk: {{ c.chunk_id.slice(0, 16) }}...
        </div>
      </div>

      <div v-if="citations.length === 0" class="text-center text-sm text-slate-400 py-10">
        <div class="text-3xl mb-2">🔍</div>
        暂无证据。提问后将在此显示检索到的文档证据。
      </div>
    </div>
  </aside>
</template>
