<script setup lang="ts">
import type { QueryIntent } from "@/types";
import { computed } from "vue";

const props = defineProps<{
  intent: QueryIntent;
}>();

const intentLabels: Record<string, { label: string; color: string; icon: string }> = {
  procedure: { label: "操作步骤", color: "bg-blue-100 text-blue-800 border-blue-300", icon: "🛠️" },
  tools: { label: "工具耗材", color: "bg-amber-100 text-amber-800 border-amber-300", icon: "🔧" },
  safety: { label: "安全警告", color: "bg-red-100 text-red-800 border-red-300", icon: "⚠️" },
  numerical: { label: "数值规格", color: "bg-purple-100 text-purple-800 border-purple-300", icon: "📐" },
  component: { label: "部件功能", color: "bg-cyan-100 text-cyan-800 border-cyan-300", icon: "⚙️" },
  troubleshooting: { label: "故障处置", color: "bg-orange-100 text-orange-800 border-orange-300", icon: "🔬" },
  general_lookup: { label: "一般查询", color: "bg-slate-100 text-slate-800 border-slate-300", icon: "📖" },
  general: { label: "一般查询", color: "bg-slate-100 text-slate-800 border-slate-300", icon: "📖" },
};

const primary = computed(() => intentLabels[props.intent.primary] || intentLabels.general);
const confidencePct = computed(() => Math.round((props.intent.confidence || 0) * 100));
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <span class="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full border" :class="primary.color">
      <span>{{ primary.icon }}</span>
      <span>{{ primary.label }}</span>
    </span>

    <span
      v-if="intent.expects_procedure"
      class="inline-flex items-center text-xs px-2.5 py-1 rounded-full bg-blue-50 text-blue-800 border border-blue-200"
    >
      期待步骤式回答
    </span>

    <span
      v-if="intent.safety_sensitive"
      class="inline-flex items-center text-xs px-2.5 py-1 rounded-full bg-red-50 text-red-800 border border-red-200"
    >
      ⚠️ 涉及安全内容
    </span>

    <span class="text-[11px] text-slate-600 ml-1">置信度 {{ confidencePct }}%</span>

    <div v-if="intent.keywords?.length > 0" class="flex flex-wrap gap-1 ml-2">
      <span
        v-for="k in intent.keywords.slice(0, 5)"
        :key="k"
        class="text-[11px] px-2 py-0.5 rounded bg-slate-100 text-slate-800 border border-slate-200"
      >
        #{{ k }}
      </span>
    </div>
  </div>
</template>
