<script setup lang="ts">
import { ref, onMounted, computed, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Activity,
  Clock,
  Cpu,
  AlertCircle,
  FileText,
  Zap,
  ChevronDown,
  ChevronUp,
} from "lucide-vue-next";
import AppIcon from "@/components/AppIcon.vue";
import {
  listMonitorQueries,
  getMonitorQueryDetail,
  listMonitorLLMCalls,
  getMonitorLLMCallDetail,
  getMonitorStats,
} from "@/api/client";
import type {
  QueryTraceListItem,
  QueryTraceDetail,
  LLMCallListItem,
  LLMCallDetail,
  MonitorStats,
  NodeExecutionRecord,
  MonitorNodeStat,
  RetrievalTrace,
} from "@/types";
import RetrievalTracePanel from "@/components/RetrievalTracePanel.vue";

const router = useRouter();
const route = useRoute();

type TabKey = "queries" | "llm_calls" | "nodes" | "stats";

const currentTab = ref<TabKey>((route.query.tab as TabKey) || "queries");

const tabs = [
  { key: "queries" as TabKey, label: "查询历史", icon: FileText },
  { key: "llm_calls" as TabKey, label: "LLM 调用", icon: Cpu },
  { key: "nodes" as TabKey, label: "节点耗时", icon: Clock },
  { key: "stats" as TabKey, label: "统计概览", icon: Activity },
];

function switchTab(tab: TabKey) {
  currentTab.value = tab;
  router.replace({ path: "/monitor", query: { tab } });
}

watch(
  () => route.query.tab,
  (v) => {
    if (v && tabs.find((t) => t.key === v)) {
      currentTab.value = v as TabKey;
    }
  },
);

// ================ Tab 1: 查询历史 ================
const queries = ref<QueryTraceListItem[]>([]);
const queryTotal = ref(0);
const queryPage = ref(1);
const queryPageSize = 20;
const queryLoading = ref(false);
const queryError = ref<string | null>(null);
const expandedQueryId = ref<string | null>(null);
const queryDetail = ref<QueryTraceDetail | null>(null);
const queryDetailLoading = ref(false);

const queryTotalPages = computed(() => Math.max(1, Math.ceil(queryTotal.value / queryPageSize)));

async function loadQueries() {
  queryLoading.value = true;
  queryError.value = null;
  try {
    const r = await listMonitorQueries(queryPage.value, queryPageSize);
    queries.value = r.items;
    queryTotal.value = r.total;
  } catch (e) {
    queryError.value = (e as Error).message;
  } finally {
    queryLoading.value = false;
  }
}

function queryNextPage() {
  if (queryPage.value < queryTotalPages.value) {
    queryPage.value++;
    expandedQueryId.value = null;
    queryDetail.value = null;
    loadQueries();
  }
}
function queryPrevPage() {
  if (queryPage.value > 1) {
    queryPage.value--;
    expandedQueryId.value = null;
    queryDetail.value = null;
    loadQueries();
  }
}

async function toggleQueryDetail(traceId: string) {
  if (expandedQueryId.value === traceId) {
    expandedQueryId.value = null;
    queryDetail.value = null;
    return;
  }
  expandedQueryId.value = traceId;
  queryDetail.value = null;
  queryDetailLoading.value = true;
  try {
    queryDetail.value = await getMonitorQueryDetail(traceId);
  } catch (e) {
    queryError.value = (e as Error).message;
  } finally {
    queryDetailLoading.value = false;
  }
}

const queryRetrievalTrace = computed<RetrievalTrace | undefined>(() => {
  if (!queryDetail.value) return undefined;
  const d = queryDetail.value;
  return {
    strategy: "",
    stages: d.stages,
    channels: d.channels,
    selected_evidence: d.selected_evidence,
    evidence_sufficiency: d.evidence_sufficiency,
  } as RetrievalTrace;
});

// ================ Tab 2: LLM 调用 ================
const llmCalls = ref<LLMCallListItem[]>([]);
const llmTotal = ref(0);
const llmPage = ref(1);
const llmPageSize = 20;
const llmLoading = ref(false);
const llmError = ref<string | null>(null);
const sceneFilter = ref("");
const expandedCallId = ref<string | null>(null);
const callDetail = ref<LLMCallDetail | null>(null);
const callDetailLoading = ref(false);

const sceneOptions = [
  { value: "", label: "全部场景" },
  { value: "compile", label: "compile" },
  { value: "generate_answer", label: "generate_answer" },
  { value: "unknown", label: "unknown" },
];

const llmTotalPages = computed(() => Math.max(1, Math.ceil(llmTotal.value / llmPageSize)));

async function loadLLMCalls() {
  llmLoading.value = true;
  llmError.value = null;
  try {
    const r = await listMonitorLLMCalls(llmPage.value, llmPageSize, sceneFilter.value || undefined);
    llmCalls.value = r.items;
    llmTotal.value = r.total;
  } catch (e) {
    llmError.value = (e as Error).message;
  } finally {
    llmLoading.value = false;
  }
}

function llmNextPage() {
  if (llmPage.value < llmTotalPages.value) {
    llmPage.value++;
    expandedCallId.value = null;
    callDetail.value = null;
    loadLLMCalls();
  }
}
function llmPrevPage() {
  if (llmPage.value > 1) {
    llmPage.value--;
    expandedCallId.value = null;
    callDetail.value = null;
    loadLLMCalls();
  }
}

async function toggleCallDetail(callId: string) {
  if (expandedCallId.value === callId) {
    expandedCallId.value = null;
    callDetail.value = null;
    return;
  }
  expandedCallId.value = callId;
  callDetail.value = null;
  callDetailLoading.value = true;
  try {
    callDetail.value = await getMonitorLLMCallDetail(callId);
  } catch (e) {
    llmError.value = (e as Error).message;
  } finally {
    callDetailLoading.value = false;
  }
}

// ================ Tab 3 & 4: 节点耗时 / 统计概览 ================
const monitorStats = ref<MonitorStats | null>(null);
const statsLoading = ref(false);
const statsError = ref<string | null>(null);
const recentNodeRecords = ref<Array<NodeExecutionRecord & { trace_id?: string; question?: string; created_at?: string | null }>>([]);
const nodesLoading = ref(false);
const nodesError = ref<string | null>(null);

const nodeStats = computed<MonitorNodeStat[]>(() => monitorStats.value?.node_stats || []);
const maxAvgMs = computed(() => Math.max(1, ...nodeStats.value.map((n) => n.avg_ms || 0)));

async function loadMonitorStats() {
  statsLoading.value = true;
  statsError.value = null;
  try {
    monitorStats.value = await getMonitorStats(24);
  } catch (e) {
    statsError.value = (e as Error).message;
  } finally {
    statsLoading.value = false;
  }
}

async function loadRecentNodeRecords() {
  nodesLoading.value = true;
  nodesError.value = null;
  try {
    const r = await listMonitorQueries(1, 8);
    const records: Array<NodeExecutionRecord & { trace_id?: string; question?: string; created_at?: string | null }> = [];
    const details = await Promise.all(
      r.items.slice(0, 8).map((q) => getMonitorQueryDetail(q.trace_id).catch(() => null)),
    );
    for (let i = 0; i < details.length && records.length < 20; i++) {
      const d = details[i];
      if (!d) continue;
      for (const node of d.node_executions || []) {
        records.push({
          ...node,
          trace_id: d.trace_id,
          question: d.question,
          created_at: d.created_at,
        });
        if (records.length >= 20) break;
      }
    }
    recentNodeRecords.value = records;
  } catch (e) {
    nodesError.value = (e as Error).message;
  } finally {
    nodesLoading.value = false;
  }
}

// ================ 通用工具 ================
function statusColor(status: string): string {
  if (status === "success") return "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (status === "error") return "bg-rose-50 text-rose-700 border-rose-200";
  if (status === "needs_clarification") return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-slate-50 text-slate-600 border-slate-200";
}

function statusLabel(status: string): string {
  if (status === "success") return "成功";
  if (status === "error") return "失败";
  if (status === "needs_clarification") return "需澄清";
  return status || "-";
}

function sceneLabel(scene: string): string {
  if (scene === "compile") return "编译";
  if (scene === "generate_answer") return "生成回答";
  if (scene === "unknown") return "未知";
  return scene || "-";
}

function formatTime(t: string | null | undefined): string {
  if (!t) return "-";
  try {
    const d = new Date(t);
    return d.toLocaleString("zh-CN", { hour12: false });
  } catch {
    return t;
  }
}

function formatNumber(n: number | undefined): string {
  if (n === undefined || n === null) return "0";
  return n.toLocaleString("zh-CN");
}

function formatRate(rate: number | undefined): string {
  if (rate === undefined || rate === null) return "0.0%";
  const r = rate <= 1 ? rate * 100 : rate;
  return `${r.toFixed(1)}%`;
}

function barWidth(avgMs: number): string {
  return `${Math.max(2, Math.round((avgMs / maxAvgMs.value) * 100))}%`;
}

function refreshAll() {
  loadQueries();
  loadLLMCalls();
  loadMonitorStats();
  loadRecentNodeRecords();
}

watch(currentTab, (tab) => {
  if (tab === "queries" && queries.value.length === 0 && !queryLoading.value) loadQueries();
  if (tab === "llm_calls" && llmCalls.value.length === 0 && !llmLoading.value) loadLLMCalls();
  if (tab === "nodes") {
    if (!monitorStats.value && !statsLoading.value) loadMonitorStats();
    if (recentNodeRecords.value.length === 0 && !nodesLoading.value) loadRecentNodeRecords();
  }
  if (tab === "stats" && !monitorStats.value && !statsLoading.value) loadMonitorStats();
});

onMounted(() => {
  if (currentTab.value === "queries") loadQueries();
  else if (currentTab.value === "llm_calls") loadLLMCalls();
  else if (currentTab.value === "nodes") {
    loadMonitorStats();
    loadRecentNodeRecords();
  } else if (currentTab.value === "stats") loadMonitorStats();
});
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-4 px-6 py-3">
    <div class="flex justify-end">
      <button
        class="flex items-center space-x-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-900 active:scale-95 disabled:opacity-60"
        @click="refreshAll"
      >
        <AppIcon name="refresh-cw" class="h-4 w-4" />
        <span>刷新数据</span>
      </button>
    </div>

    <div>
      <div class="governance-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="governance-tab"
          :class="currentTab === tab.key ? 'is-active' : ''"
          @click="switchTab(tab.key)"
        >
          <component :is="tab.icon" class="h-4 w-4" />
          <span>{{ tab.label }}</span>
        </button>
      </div>
    </div>

    <!-- ============ Tab 1: 查询历史 ============ -->
    <div v-if="currentTab === 'queries'">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex items-center justify-between">
          <h3 class="text-sm font-semibold text-slate-800">查询历史</h3>
          <span class="text-xs text-slate-500">共 {{ queryTotal }} 条查询</span>
        </div>

        <div v-if="queryError" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ queryError }}</div>
        <div v-if="queryLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>

        <div v-if="!queryLoading && queries.length === 0 && !queryError" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300">
            <FileText class="w-8 h-8" />
          </div>
          <h3 class="text-base font-semibold text-slate-800">暂无查询记录</h3>
          <p class="text-sm text-slate-400 mt-1 max-w-md">当前还没有任何查询追踪记录。</p>
        </div>

        <div v-if="!queryLoading && queries.length > 0" class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50/70 border-b border-slate-200">
              <tr class="text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                <th class="px-4 py-3 w-8"></th>
                <th class="px-4 py-3">问题</th>
                <th class="px-4 py-3 text-right whitespace-nowrap">耗时(ms)</th>
                <th class="px-4 py-3 text-right whitespace-nowrap">节点数</th>
                <th class="px-4 py-3 text-right whitespace-nowrap">LLM调用数</th>
                <th class="px-4 py-3 whitespace-nowrap">状态</th>
                <th class="px-4 py-3 whitespace-nowrap">时间</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <template v-for="q in queries" :key="q.trace_id">
                <tr
                  class="hover:bg-slate-50 cursor-pointer transition-colors"
                  @click="toggleQueryDetail(q.trace_id)"
                >
                  <td class="px-4 py-3 text-slate-400">
                    <component
                      :is="expandedQueryId === q.trace_id ? ChevronUp : ChevronDown"
                      class="w-4 h-4"
                    />
                  </td>
                  <td class="px-4 py-3">
                    <div class="text-slate-800 font-medium line-clamp-1 max-w-md">{{ q.question || '-' }}</div>
                    <div v-if="q.answer_summary" class="text-xs text-slate-500 line-clamp-1 mt-0.5 max-w-md">{{ q.answer_summary }}</div>
                  </td>
                  <td class="px-4 py-3 text-right text-slate-700 tabular-nums">{{ q.duration_ms ?? 0 }}</td>
                  <td class="px-4 py-3 text-right text-slate-700 tabular-nums">{{ q.node_count ?? 0 }}</td>
                  <td class="px-4 py-3 text-right text-slate-700 tabular-nums">{{ q.llm_call_count ?? 0 }}</td>
                  <td class="px-4 py-3">
                    <span class="text-[10px] font-medium px-2 py-0.5 rounded border whitespace-nowrap" :class="statusColor(q.status)">{{ statusLabel(q.status) }}</span>
                  </td>
                  <td class="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{{ formatTime(q.created_at) }}</td>
                </tr>
                <tr v-if="expandedQueryId === q.trace_id">
                  <td colspan="7" class="px-4 py-4 bg-slate-50/40">
                    <div v-if="queryDetailLoading" class="py-8 text-center text-slate-400 text-sm">加载详情中...</div>
                    <div v-else-if="queryDetail" class="space-y-5">
                      <!-- 检索 trace -->
                      <div v-if="queryRetrievalTrace" class="bg-white rounded-lg border border-slate-200 p-4">
                        <h4 class="text-xs font-semibold text-slate-700 mb-3 flex items-center space-x-2">
                          <FileText class="w-3.5 h-3.5" />
                          <span>检索 Trace</span>
                        </h4>
                        <RetrievalTracePanel :trace="queryRetrievalTrace" />
                      </div>

                      <!-- 节点执行列表 -->
                      <div class="bg-white rounded-lg border border-slate-200 overflow-hidden">
                        <div class="px-4 py-2.5 border-b border-slate-200 bg-slate-50/70">
                          <h4 class="text-xs font-semibold text-slate-700">节点执行列表（{{ queryDetail.node_executions?.length || 0 }}）</h4>
                        </div>
                        <div v-if="queryDetail.node_executions && queryDetail.node_executions.length > 0" class="overflow-x-auto">
                          <table class="w-full text-xs">
                            <thead class="bg-white border-b border-slate-200">
                              <tr class="text-left text-[10px] font-medium text-slate-500 uppercase tracking-wider">
                                <th class="px-4 py-2">节点名</th>
                                <th class="px-4 py-2 text-right whitespace-nowrap">耗时(ms)</th>
                                <th class="px-4 py-2 whitespace-nowrap">状态</th>
                                <th class="px-4 py-2">输入摘要</th>
                                <th class="px-4 py-2">输出摘要</th>
                                <th class="px-4 py-2">错误</th>
                              </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                              <tr v-for="(node, idx) in queryDetail.node_executions" :key="idx" class="hover:bg-slate-50">
                                <td class="px-4 py-2 text-slate-800 font-medium whitespace-nowrap">{{ node.node_name }}</td>
                                <td class="px-4 py-2 text-right text-slate-700 tabular-nums">{{ node.duration_ms ?? 0 }}</td>
                                <td class="px-4 py-2">
                                  <span class="text-[10px] font-medium px-2 py-0.5 rounded border whitespace-nowrap" :class="statusColor(node.status)">{{ statusLabel(node.status) }}</span>
                                </td>
                                <td class="px-4 py-2 text-slate-600 max-w-xs truncate">{{ node.input_summary || '-' }}</td>
                                <td class="px-4 py-2 text-slate-600 max-w-xs truncate">{{ node.output_summary || '-' }}</td>
                                <td class="px-4 py-2 text-rose-600 max-w-xs truncate">{{ node.error || '-' }}</td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                        <div v-else class="p-4 text-xs text-slate-400 text-center">无节点执行记录</div>
                      </div>

                      <!-- LLM 调用列表 -->
                      <div class="bg-white rounded-lg border border-slate-200 overflow-hidden">
                        <div class="px-4 py-2.5 border-b border-slate-200 bg-slate-50/70">
                          <h4 class="text-xs font-semibold text-slate-700">LLM 调用列表（{{ queryDetail.llm_calls?.length || 0 }}）</h4>
                        </div>
                        <div v-if="queryDetail.llm_calls && queryDetail.llm_calls.length > 0" class="overflow-x-auto">
                          <table class="w-full text-xs">
                            <thead class="bg-white border-b border-slate-200">
                              <tr class="text-left text-[10px] font-medium text-slate-500 uppercase tracking-wider">
                                <th class="px-4 py-2">场景</th>
                                <th class="px-4 py-2">模型</th>
                                <th class="px-4 py-2 text-right whitespace-nowrap">耗时(ms)</th>
                                <th class="px-4 py-2 text-right whitespace-nowrap">输入tokens</th>
                                <th class="px-4 py-2 text-right whitespace-nowrap">输出tokens</th>
                                <th class="px-4 py-2 whitespace-nowrap">状态</th>
                              </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                              <tr v-for="call in queryDetail.llm_calls" :key="call.call_id" class="hover:bg-slate-50">
                                <td class="px-4 py-2 text-slate-800 whitespace-nowrap">{{ sceneLabel(call.scene) }}</td>
                                <td class="px-4 py-2 text-slate-600 whitespace-nowrap">{{ call.model_name || '-' }}</td>
                                <td class="px-4 py-2 text-right text-slate-700 tabular-nums">{{ call.duration_ms ?? 0 }}</td>
                                <td class="px-4 py-2 text-right text-slate-700 tabular-nums">{{ call.input_tokens ?? 0 }}</td>
                                <td class="px-4 py-2 text-right text-slate-700 tabular-nums">{{ call.output_tokens ?? 0 }}</td>
                                <td class="px-4 py-2">
                                  <span class="text-[10px] font-medium px-2 py-0.5 rounded border whitespace-nowrap" :class="statusColor(call.status)">{{ statusLabel(call.status) }}</span>
                                </td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                        <div v-else class="p-4 text-xs text-slate-400 text-center">无 LLM 调用记录</div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <div v-if="queryTotalPages > 1" class="p-4 border-t border-slate-200 flex items-center justify-center gap-2">
          <button @click="queryPrevPage" :disabled="queryPage === 1" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">上一页</button>
          <span class="text-sm text-slate-600">第 {{ queryPage }} / {{ queryTotalPages }} 页</span>
          <button @click="queryNextPage" :disabled="queryPage >= queryTotalPages" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">下一页</button>
        </div>
      </div>
    </div>

    <!-- ============ Tab 2: LLM 调用 ============ -->
    <div v-else-if="currentTab === 'llm_calls'">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div class="flex items-center gap-3">
            <label class="text-sm font-medium text-slate-600 shrink-0">场景:</label>
            <select
              v-model="sceneFilter"
              @change="llmPage = 1; expandedCallId = null; callDetail = null; loadLLMCalls()"
              class="bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm text-slate-700 shadow-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            >
              <option v-for="opt in sceneOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
            </select>
            <button @click="llmPage = 1; expandedCallId = null; callDetail = null; loadLLMCalls()" class="bg-slate-800 hover:bg-slate-900 text-white rounded-lg px-4 py-1.5 text-sm font-medium ml-2">刷新</button>
          </div>
          <span class="text-xs text-slate-500">共 {{ llmTotal }} 条调用</span>
        </div>

        <div v-if="llmError" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ llmError }}</div>
        <div v-if="llmLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>

        <div v-if="!llmLoading && llmCalls.length === 0 && !llmError" class="flex flex-col items-center justify-center py-20 px-4 text-center">
          <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300">
            <Cpu class="w-8 h-8" />
          </div>
          <h3 class="text-base font-semibold text-slate-800">暂无 LLM 调用记录</h3>
          <p class="text-sm text-slate-400 mt-1 max-w-md">当前还没有任何 LLM 调用记录。</p>
        </div>

        <div v-if="!llmLoading && llmCalls.length > 0" class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-slate-50/70 border-b border-slate-200">
              <tr class="text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                <th class="px-4 py-3 w-8"></th>
                <th class="px-4 py-3 whitespace-nowrap">场景</th>
                <th class="px-4 py-3 whitespace-nowrap">模型</th>
                <th class="px-4 py-3 text-right whitespace-nowrap">耗时(ms)</th>
                <th class="px-4 py-3 text-right whitespace-nowrap">输入tokens</th>
                <th class="px-4 py-3 text-right whitespace-nowrap">输出tokens</th>
                <th class="px-4 py-3 whitespace-nowrap">状态</th>
                <th class="px-4 py-3 whitespace-nowrap">时间</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              <template v-for="call in llmCalls" :key="call.call_id">
                <tr
                  class="hover:bg-slate-50 cursor-pointer transition-colors"
                  @click="toggleCallDetail(call.call_id)"
                >
                  <td class="px-4 py-3 text-slate-400">
                    <component
                      :is="expandedCallId === call.call_id ? ChevronUp : ChevronDown"
                      class="w-4 h-4"
                    />
                  </td>
                  <td class="px-4 py-3">
                    <span class="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200 whitespace-nowrap">{{ sceneLabel(call.scene) }}</span>
                  </td>
                  <td class="px-4 py-3 text-slate-700 whitespace-nowrap">{{ call.model_name || '-' }}</td>
                  <td class="px-4 py-3 text-right text-slate-700 tabular-nums">{{ call.duration_ms ?? 0 }}</td>
                  <td class="px-4 py-3 text-right text-slate-700 tabular-nums">{{ call.input_tokens ?? 0 }}</td>
                  <td class="px-4 py-3 text-right text-slate-700 tabular-nums">{{ call.output_tokens ?? 0 }}</td>
                  <td class="px-4 py-3">
                    <span class="text-[10px] font-medium px-2 py-0.5 rounded border whitespace-nowrap" :class="statusColor(call.status)">{{ statusLabel(call.status) }}</span>
                  </td>
                  <td class="px-4 py-3 text-xs text-slate-500 whitespace-nowrap">{{ formatTime(call.created_at) }}</td>
                </tr>
                <tr v-if="expandedCallId === call.call_id">
                  <td colspan="8" class="px-4 py-4 bg-slate-50/40">
                    <div v-if="callDetailLoading" class="py-8 text-center text-slate-400 text-sm">加载详情中...</div>
                    <div v-else-if="callDetail" class="space-y-4">
                      <div class="flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-500">
                        <span>调用ID: <span class="text-slate-700 font-mono">{{ callDetail.call_id }}</span></span>
                        <span>追踪ID: <span class="text-slate-700 font-mono">{{ callDetail.trace_id || '-' }}</span></span>
                        <span>模型: <span class="text-slate-700">{{ callDetail.model_name || '-' }}</span></span>
                        <span>耗时: <span class="text-slate-700">{{ callDetail.duration_ms ?? 0 }}ms</span></span>
                        <span>Tokens: <span class="text-slate-700">{{ callDetail.input_tokens ?? 0 }} / {{ callDetail.output_tokens ?? 0 }}</span></span>
                      </div>

                      <div v-if="callDetail.error" class="bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ callDetail.error }}</div>

                      <div>
                        <div class="text-xs font-semibold text-slate-700 mb-1.5 flex items-center space-x-1.5">
                          <span class="w-1 h-3 bg-indigo-500 rounded"></span>
                          <span>System Prompt</span>
                        </div>
                        <pre class="bg-slate-900 text-slate-100 rounded-lg p-4 overflow-x-auto text-sm font-mono whitespace-pre-wrap break-words">{{ callDetail.system_prompt || '(空)' }}</pre>
                      </div>

                      <div>
                        <div class="text-xs font-semibold text-slate-700 mb-1.5 flex items-center space-x-1.5">
                          <span class="w-1 h-3 bg-blue-500 rounded"></span>
                          <span>User Prompt</span>
                        </div>
                        <pre class="bg-slate-900 text-slate-100 rounded-lg p-4 overflow-x-auto text-sm font-mono whitespace-pre-wrap break-words">{{ callDetail.user_prompt || '(空)' }}</pre>
                      </div>

                      <div>
                        <div class="text-xs font-semibold text-slate-700 mb-1.5 flex items-center space-x-1.5">
                          <span class="w-1 h-3 bg-emerald-500 rounded"></span>
                          <span>Completion</span>
                        </div>
                        <pre class="bg-slate-900 text-slate-100 rounded-lg p-4 overflow-x-auto text-sm font-mono whitespace-pre-wrap break-words">{{ callDetail.completion || '(空)' }}</pre>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <div v-if="llmTotalPages > 1" class="p-4 border-t border-slate-200 flex items-center justify-center gap-2">
          <button @click="llmPrevPage" :disabled="llmPage === 1" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">上一页</button>
          <span class="text-sm text-slate-600">第 {{ llmPage }} / {{ llmTotalPages }} 页</span>
          <button @click="llmNextPage" :disabled="llmPage >= llmTotalPages" class="px-3 py-1 text-sm bg-white border border-slate-200 rounded-md hover:bg-slate-50 disabled:opacity-50">下一页</button>
        </div>
      </div>
    </div>

    <!-- ============ Tab 3: 节点耗时 ============ -->
    <div v-else-if="currentTab === 'nodes'">
      <div class="space-y-6">
        <!-- 上半部分：节点平均耗时柱状图 -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-slate-800">节点平均耗时聚合（24h）</h3>
            <span class="text-xs text-slate-500">按节点名聚合</span>
          </div>

          <div v-if="statsError" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ statsError }}</div>
          <div v-if="statsLoading" class="py-16 text-center text-slate-400 text-sm">加载中...</div>

          <div v-if="!statsLoading && nodeStats.length === 0 && !statsError" class="py-16 text-center text-sm text-slate-400">暂无节点统计数据</div>

          <div v-if="!statsLoading && nodeStats.length > 0" class="p-5 space-y-3">
            <div v-for="stat in nodeStats" :key="stat.node_name" class="space-y-1">
              <div class="flex items-center justify-between text-xs">
                <span class="text-slate-700 font-medium">{{ stat.node_name }}</span>
                <span class="text-slate-500">
                  avg <span class="text-slate-800 font-semibold tabular-nums">{{ stat.avg_ms ?? 0 }}ms</span>
                  <span class="mx-1 text-slate-300">·</span>
                  <span class="tabular-nums">{{ stat.count ?? 0 }} 次</span>
                </span>
              </div>
              <div class="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                <div
                  class="h-full bg-gradient-to-r from-indigo-500 to-blue-500 rounded-full transition-all"
                  :style="{ width: barWidth(stat.avg_ms || 0) }"
                ></div>
              </div>
            </div>
          </div>
        </div>

        <!-- 下半部分：最近 20 条节点执行记录 -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-slate-800">最近节点执行记录</h3>
            <span class="text-xs text-slate-500">最多 20 条</span>
          </div>

          <div v-if="nodesError" class="m-4 bg-rose-50 border border-rose-200 rounded-lg p-3 text-sm text-rose-700">{{ nodesError }}</div>
          <div v-if="nodesLoading" class="py-16 text-center text-slate-400 text-sm">加载中...</div>

          <div v-if="!nodesLoading && recentNodeRecords.length === 0 && !nodesError" class="py-16 text-center text-sm text-slate-400">暂无节点执行记录</div>

          <div v-if="!nodesLoading && recentNodeRecords.length > 0" class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead class="bg-slate-50/70 border-b border-slate-200">
                <tr class="text-left text-xs font-medium text-slate-500 uppercase tracking-wider">
                  <th class="px-4 py-3 whitespace-nowrap">节点名</th>
                  <th class="px-4 py-3 text-right whitespace-nowrap">耗时(ms)</th>
                  <th class="px-4 py-3 whitespace-nowrap">状态</th>
                  <th class="px-4 py-3">关联问题</th>
                  <th class="px-4 py-3 whitespace-nowrap">时间</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                <tr v-for="(node, idx) in recentNodeRecords" :key="idx" class="hover:bg-slate-50 transition-colors">
                  <td class="px-4 py-2.5 text-slate-800 font-medium whitespace-nowrap">{{ node.node_name }}</td>
                  <td class="px-4 py-2.5 text-right text-slate-700 tabular-nums">{{ node.duration_ms ?? 0 }}</td>
                  <td class="px-4 py-2.5">
                    <span class="text-[10px] font-medium px-2 py-0.5 rounded border whitespace-nowrap" :class="statusColor(node.status)">{{ statusLabel(node.status) }}</span>
                  </td>
                  <td class="px-4 py-2.5 text-slate-600 max-w-sm truncate">{{ node.question || node.trace_id || '-' }}</td>
                  <td class="px-4 py-2.5 text-xs text-slate-500 whitespace-nowrap">{{ formatTime(node.created_at) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- ============ Tab 4: 统计概览 ============ -->
    <div v-else-if="currentTab === 'stats'">
      <div v-if="statsLoading" class="py-20 text-center text-slate-400 text-sm">加载中...</div>
      <div v-else-if="statsError" class="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700">{{ statsError }}</div>
      <div v-else-if="monitorStats" class="space-y-6">
        <!-- 5 个统计卡片 -->
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
          <div class="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-slate-500">总查询数（24h）</p>
              <p class="text-2xl font-bold text-slate-900 tabular-nums">{{ formatNumber(monitorStats.total_queries) }}</p>
            </div>
            <div class="p-2 text-indigo-600 bg-indigo-50 rounded-lg">
              <Activity class="w-5 h-5" />
            </div>
          </div>

          <div class="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-slate-500">平均查询耗时</p>
              <p class="text-2xl font-bold text-slate-900 tabular-nums">{{ monitorStats.avg_query_ms ?? 0 }}<span class="text-sm font-medium text-slate-400 ml-1">ms</span></p>
            </div>
            <div class="p-2 text-blue-600 bg-blue-50 rounded-lg">
              <Clock class="w-5 h-5" />
            </div>
          </div>

          <div class="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-slate-500">错误率</p>
              <p class="text-2xl font-bold tabular-nums" :class="monitorStats.error_rate > 0 ? 'text-rose-600' : 'text-emerald-600'">{{ formatRate(monitorStats.error_rate) }}</p>
              <p class="text-[10px] text-slate-400">{{ monitorStats.error_queries ?? 0 }} / {{ monitorStats.total_queries ?? 0 }} 次错误</p>
            </div>
            <div class="p-2 text-rose-600 bg-rose-50 rounded-lg">
              <AlertCircle class="w-5 h-5" />
            </div>
          </div>

          <div class="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-slate-500">LLM 调用次数</p>
              <p class="text-2xl font-bold text-slate-900 tabular-nums">{{ formatNumber(monitorStats.total_llm_calls) }}</p>
            </div>
            <div class="p-2 text-purple-600 bg-purple-50 rounded-lg">
              <Cpu class="w-5 h-5" />
            </div>
          </div>

          <div class="bg-white p-4 rounded-lg border border-slate-200 shadow-sm flex items-center justify-between">
            <div class="space-y-0.5">
              <p class="text-xs font-medium text-slate-500">总 Token 用量</p>
              <p class="text-2xl font-bold text-slate-900 tabular-nums">{{ formatNumber(monitorStats.total_tokens) }}</p>
              <p class="text-[10px] text-slate-400">入 {{ formatNumber(monitorStats.total_input_tokens) }} / 出 {{ formatNumber(monitorStats.total_output_tokens) }}</p>
            </div>
            <div class="p-2 text-amber-600 bg-amber-50 rounded-lg">
              <Zap class="w-5 h-5" />
            </div>
          </div>
        </div>

        <!-- 统计窗口说明 -->
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-4 flex items-center justify-between">
          <div class="flex items-center space-x-2">
            <Clock class="w-4 h-4 text-slate-400" />
            <span class="text-xs text-slate-500">统计窗口</span>
          </div>
          <span class="text-sm font-semibold text-slate-800">最近 {{ monitorStats.hours ?? 24 }} 小时</span>
        </div>
      </div>

      <div v-else class="flex flex-col items-center justify-center py-20 px-4 text-center">
        <div class="w-16 h-16 bg-slate-100 text-slate-400 rounded-full flex items-center justify-center mb-4 border border-dashed border-slate-300">
          <Activity class="w-8 h-8" />
        </div>
        <h3 class="text-base font-semibold text-slate-800">暂无统计数据</h3>
        <p class="text-sm text-slate-400 mt-1 max-w-md">当前还没有任何监控统计数据。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.governance-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
  border-bottom: 1px solid #e2e8f0;
  padding-bottom: 0.75rem;
}

.governance-tab {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.75rem;
  background: #ffffff;
  color: #64748b;
  padding: 0.625rem 0.875rem;
  font-size: 0.875rem;
  font-weight: 500;
  transition: color 0.16s ease, border-color 0.16s ease, background-color 0.16s ease;
}

.governance-tab:hover {
  border-color: #cbd5e1;
  color: #0f172a;
  background: #f8fafc;
}

.governance-tab.is-active {
  border-color: #818cf8;
  background: #eef2ff;
  color: #4338ca;
  font-weight: 600;
}
</style>
