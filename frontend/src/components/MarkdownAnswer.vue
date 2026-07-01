<script setup lang="ts">
import { computed } from "vue";
import type { Citation } from "@/types";

const props = defineProps<{
  text: string;
  citations: Citation[];
  isStreaming?: boolean;
}>();

const emit = defineEmits<{
  "citation-click": [id: number];
}>();

// Parse text: split at [n] patterns, render plain text + clickable citation badges.
const segments = computed(() => {
  const out: Array<{ type: "text" | "cite"; content: string; id?: number }> = [];
  if (!props.text) return out;
  const re = /\[(\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(props.text))) {
    if (m.index > last) {
      out.push({ type: "text", content: props.text.slice(last, m.index) });
    }
    const id = parseInt(m[1], 10);
    out.push({ type: "cite", content: m[0], id });
    last = re.lastIndex;
  }
  if (last < props.text.length) {
    out.push({ type: "text", content: props.text.slice(last) });
  }
  return out;
});

function hasCitation(id: number | undefined): boolean {
  if (!id) return false;
  return props.citations.some((c) => c.citation_id === id);
}
</script>

<template>
  <span class="whitespace-pre-wrap break-words leading-7 text-slate-800">
    <template v-for="(seg, idx) in segments" :key="idx">
      <span v-if="seg.type === 'text'">{{ seg.content }}</span>
      <span
        v-else
        class="citation-badge"
        :class="{
          'bg-brand-200 text-brand-800': hasCitation(seg.id),
          'bg-slate-100 text-slate-400 cursor-not-allowed': !hasCitation(seg.id),
        }"
        @click="seg.id && hasCitation(seg.id) && emit('citation-click', seg.id)"
        :title="hasCitation(seg.id) ? '点击查看证据 #' + seg.id : '无可用证据'"
      >
        {{ seg.id }}
      </span>
    </template>
    <span v-if="isStreaming" class="cursor-blink"></span>
  </span>
</template>
