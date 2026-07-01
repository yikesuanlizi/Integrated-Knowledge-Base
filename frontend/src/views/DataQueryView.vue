<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getNL2SQLStatus, queryNL2SQL, seedNL2SQL } from "@/api/client";
import type { NL2SQLQueryResponse, NL2SQLStatus } from "@/types";

const question = ref("查找起落架轮迹相关的知识库字段和值域");
const loading = ref(false);
const seeding = ref(false);
const error = ref<string | null>(null);
const status = ref<NL2SQLStatus | null>(null);
const result = ref<NL2SQLQueryResponse | null>(null);

const sampleQuestions = [
  "查找起落架轮迹相关的知识库字段和值域",
  "哪些字段控制 Wiki 卡片审核状态",
  "引用覆盖率依赖哪些结构化元数据",
  "飞机等级号/道面等级号会命中哪些实体和值域",
  "严格审核模式下哪些状态可以参与问答",
];

const steps = computed(() => {
  const raw = result.value?.trace?.steps;
  return Array.isArray(raw) ? raw : [];
});

const tableCount = computed(() => status.value?.metadata?.nl2sql_table_info || 0);
const fieldCount = computed(() => status.value?.metadata?.nl2sql_column_info || 0);
const metricCount = computed(() => status.value?.metadata?.nl2sql_metric_info || 0);
const valueCount = computed(() => status.value?.metadata?.nl2sql_value_info || 0);
const statusNotice = computed(() => {
  if (!status.value?.warnings?.length) return "";
  const joined = status.value.warnings.join("；");
  if (joined.includes("Elasticsearch")) {
    return "枚举值全文索引待同步，当前元数据检索已自动使用本地协议兜底。";
  }
  if (joined.includes("Milvus") || joined.includes("connection")) {
    return "向量索引待同步，当前元数据检索已自动使用结构化协议兜底。";
  }
  return "部分索引待同步，当前元数据检索已使用本地协议兜底。";
});

async function refreshStatus() {
  try {
    status.value = await getNL2SQLStatus();
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function seed() {
  seeding.value = true;
  error.value = null;
  try {
    await seedNL2SQL();
    await refreshStatus();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    seeding.value = false;
  }
}

async function ask() {
  const q = question.value.trim();
  if (!q || loading.value) return;
  loading.value = true;
  error.value = null;
  result.value = null;
  try {
    result.value = await queryNL2SQL(q, 100);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

function pick(q: string) {
  question.value = q;
}

function formatCell(value: unknown) {
  if (typeof value === "number") return Number.isInteger(value) ? value : value.toFixed(2);
  return value ?? "-";
}

onMounted(refreshStatus);
</script>

<template>
  <div class="mx-auto max-w-7xl">
    <!-- Header -->
    <div class="mb-4">
      <h2 class="text-lg font-semibold text-slate-800">结构化元数据查询</h2>
    </div>

    <!-- Status -->
    <div class="rounded-lg border border-slate-200 bg-white p-4 mb-6">
      <div class="flex items-center justify-between gap-3">
        <div>
          <div class="text-xs font-medium text-slate-600">元数据协议状态</div>
          <div class="mt-1 text-sm font-semibold text-slate-800">
            {{ status?.seeded ? "已初始化" : "等待初始化" }}
          </div>
        </div>
        <span
          class="rounded-full border px-2.5 py-1 text-xs font-medium"
          :class="status?.seeded ? 'border-blue-200 bg-blue-50 text-blue-800' : 'border-amber-200 bg-amber-50 text-amber-800'"
        >
          {{ status?.seeded ? "已就绪" : "待初始化" }}
        </span>
      </div>
      <button
        @click="seed"
        :disabled="seeding"
        class="mt-3 w-full rounded-md bg-slate-800 px-3 py-1 text-sm font-medium text-white transition hover:bg-slate-700 disabled:bg-slate-400"
      >
        {{ seeding ? "初始化中..." : "初始化结构化元数据索引" }}
      </button>
    </div>

    <!-- Stats -->
    <div class="grid gap-3 md:grid-cols-4 mb-6">
      <div v-for="(stat, i) in [
        { label: '协议表', value: tableCount },
        { label: '字段协议', value: fieldCount },
        { label: '指标口径', value: metricCount },
        { label: '值域索引', value: valueCount },
      ]" :key="i" class="rounded-lg border border-slate-200 bg-white p-3">
        <div class="text-xs font-medium text-slate-600">{{ stat.label }}</div>
        <div class="mt-1 text-lg font-semibold text-slate-800">{{ stat.value }}</div>
      </div>
    </div>

    <!-- Warning -->
    <div v-if="statusNotice" class="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
      {{ statusNotice }}
    </div>

    <!-- Query Section -->
    <div class="grid gap-4">
      <div class="rounded-lg border border-slate-200 bg-white">
        <div class="border-b border-slate-100 px-4 py-3">
          <div class="text-sm font-medium text-slate-700">自然语言元数据检索</div>
        </div>
        <div class="p-4">
          <textarea
            v-model="question"
            rows="3"
            class="w-full resize-none rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm text-slate-800 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
            placeholder="例如：哪些字段控制 Wiki 卡片审核状态"
            @keydown.enter.exact.prevent="ask"
          />
          <div class="mt-3 flex flex-wrap items-center gap-3">
            <button
              @click="ask"
              :disabled="loading || !question.trim()"
              class="rounded-md bg-blue-600 px-3 py-1 text-sm font-medium text-white transition hover:bg-blue-700 disabled:bg-slate-400"
            >
              {{ loading ? "生成中..." : "生成元数据 SQL" }}
            </button>
            <span class="text-xs text-slate-500">Enter 执行，Shift+Enter 换行</span>
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              v-for="q in sampleQuestions"
              :key="q"
              @click="pick(q)"
              class="rounded-md border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-700 transition hover:border-slate-300 hover:bg-white"
            >
              {{ q }}
            </button>
          </div>
          <div v-if="error" class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {{ error }}
          </div>
        </div>
      </div>

    </div>

    <!-- Results -->
    <div v-if="result" class="mt-4 space-y-3">
      <div class="rounded-lg border border-slate-200 bg-white">
        <div class="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
          <div class="text-sm font-medium text-slate-800">生成 SQL</div>
          <div class="text-xs text-slate-600">已校验的只读查询</div>
        </div>
        <pre class="overflow-x-auto bg-slate-900 p-4 text-sm text-slate-300">{{ result.sql }}</pre>
      </div>

      <div class="rounded-lg border border-slate-200 bg-white">
        <div class="flex items-center justify-between border-b border-slate-100 px-4 py-2.5">
          <div class="text-sm font-medium text-slate-800">结果表格</div>
          <div class="text-xs text-slate-600">{{ result.row_count }} 行</div>
        </div>
        <div class="overflow-x-auto">
          <table class="min-w-full border-collapse text-sm">
            <thead class="bg-slate-50">
              <tr>
                <th v-for="col in result.columns" :key="col" class="border-b border-slate-200 px-4 py-2.5 text-left font-medium text-slate-700">
                  {{ col }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, idx) in result.rows" :key="idx" class="odd:bg-white even:bg-slate-50">
                <td v-for="col in result.columns" :key="col" class="border-b border-slate-100 px-4 py-2.5 text-slate-700">
                  {{ formatCell(row[col]) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="rounded-lg border border-slate-200 bg-white p-4">
        <div class="text-sm font-medium text-slate-800">解释</div>
        <p class="mt-2 text-sm text-slate-700">{{ result.explanation }}</p>
      </div>

      <div class="rounded-lg border border-slate-200 bg-white">
        <div class="border-b border-slate-100 px-4 py-2.5 text-sm font-medium text-slate-800">执行轨迹</div>
        <ol class="divide-y divide-slate-100">
          <li v-for="(step, idx) in steps" :key="idx" class="px-4 py-3">
            <div class="flex items-center gap-2">
              <span class="flex h-5 w-5 items-center justify-center rounded-full bg-slate-100 text-xs font-medium text-slate-700">
                {{ idx + 1 }}
              </span>
              <div class="text-xs font-medium text-slate-800">{{ step.node || `step_${idx + 1}` }}</div>
            </div>
            <pre class="mt-2 whitespace-pre-wrap break-words rounded bg-slate-50 p-2 text-xs text-slate-700">{{ JSON.stringify(step, null, 2) }}</pre>
          </li>
        </ol>
      </div>
    </div>
  </div>
</template>
