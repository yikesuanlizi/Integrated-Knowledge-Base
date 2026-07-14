<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from "vue";
import { getEvalFixtures, streamQuery } from "@/api/client";
import type { Citation, QueryIntent, RetrievalTrace, SQLResult } from "@/types";
import CitationPanel from "@/components/CitationPanel.vue";
import IntentBadge from "@/components/IntentBadge.vue";
import MarkdownAnswer from "@/components/MarkdownAnswer.vue";
import RetrievalTracePanel from "@/components/RetrievalTracePanel.vue";
import AppIcon from "@/components/AppIcon.vue";

interface ChatTurn {
  id: number;
  role: "user" | "assistant";
  question?: string;
  text: string;
  citations: Citation[];
  sqlResult?: SQLResult;
  retrievalTrace?: RetrievalTrace;
  intent?: QueryIntent;
  isStreaming?: boolean;
  currentNode?: string;
  currentNodeLabel?: string;
  completedNodes?: string[];
  phase?: "recalling" | "generating" | "done";
  timestamp: string;
}

const question = ref("");
const loading = ref(false);
const error = ref<string | null>(null);
const conversation = ref<ChatTurn[]>([]);
const activeCitationId = ref<number | null>(null);
const turnCounter = ref(0);
const abortFn = ref<null | (() => void)>(null);

const sampleQuestions = ref<string[]>([
  "软、硬道面载荷等级值换算是什么？",
  "登机门是什么？",
  "起落架轮迹是什么意思？",
  "飞机等级号/道面等级号报告系统是什么？",
  "平尾后部离地高度是什么意思？",
]);

async function send() {
  const q = question.value.trim();
  if (!q || loading.value) return;

  error.value = null;
  loading.value = true;
  const turnId = ++turnCounter.value;

  conversation.value.push({
    id: turnId,
    role: "user",
    question: q,
    text: q,
    citations: [],
    timestamp: new Date().toLocaleTimeString(),
  });

  const assistantTurn: ChatTurn = {
    id: turnId + 10000,
    role: "assistant",
    text: "",
    citations: [],
    isStreaming: true,
    completedNodes: [],
    phase: "recalling",
    timestamp: new Date().toLocaleTimeString(),
  };
  conversation.value.push(assistantTurn);
  question.value = "";

  await nextTick();

  try {
    // 只调用一次 streamQuery：流式 token + done 时拿 citations / intent
    abortFn.value = streamQuery(
      { question: q, top_k: 8 },
      (_token, partial) => {
        assistantTurn.text = partial;
      },
      ({ citations, intent, trace, sql_result }) => {
        assistantTurn.citations = citations || [];
        assistantTurn.sqlResult = sql_result;
        assistantTurn.retrievalTrace = trace;
        if (intent) assistantTurn.intent = intent;
        assistantTurn.isStreaming = false;
        assistantTurn.phase = "done";
        assistantTurn.currentNode = undefined;
        assistantTurn.currentNodeLabel = undefined;
        loading.value = false;
      },
      (err) => {
        error.value = err.message;
        assistantTurn.isStreaming = false;
        assistantTurn.phase = "done";
        loading.value = false;
        if (!assistantTurn.text) {
          assistantTurn.text = "⚠️ 查询失败：" + err.message;
        }
      },
      (node, label) => {
        if (node === "generate_answer") {
          assistantTurn.phase = "generating";
        }
        assistantTurn.currentNode = node;
        assistantTurn.currentNodeLabel = label;
        if (!assistantTurn.completedNodes) assistantTurn.completedNodes = [];
        if (!assistantTurn.completedNodes.includes(node)) {
          assistantTurn.completedNodes.push(node);
        }
      },
      (trace, _mode) => {
        assistantTurn.retrievalTrace = trace;
      },
    );
  } catch (e) {
    error.value = (e as Error).message;
    loading.value = false;
    assistantTurn.isStreaming = false;
    if (!assistantTurn.text) {
      assistantTurn.text = "⚠️ 查询失败：" + (e as Error).message;
    }
  }
}

function stopStreaming() {
  abortFn.value?.();
  loading.value = false;
  const last = conversation.value[conversation.value.length - 1];
  if (last) last.isStreaming = false;
}

function pickSample(q: string) {
  question.value = q;
}

function setActiveCitation(id: number | null) {
  activeCitationId.value = id;
}

function clearChat() {
  conversation.value = [];
}

const NODE_LABELS: Record<string, string> = {
  classify_intent: "意图分类",
  extract_query: "查询特征抽取",
  recall_dispatch: "多路召回",
  merge_results: "合并去重",
  expand_graph: "Wiki图扩展",
  rerank: "混合重排序",
  build_evidence: "证据包构建",
  generate_answer: "生成答案",
};

function getNodeLabel(node: string): string {
  return NODE_LABELS[node] || node;
}

const hasConversation = computed(() => conversation.value.length > 0);
const latestCitations = computed(() => conversation.value[conversation.value.length - 1]?.citations || []);

onMounted(async () => {
  try {
    const fixtures = await getEvalFixtures();
    if (fixtures.questions?.length) {
      sampleQuestions.value = fixtures.questions;
    }
  } catch {
    // Keep local fallback questions when fixture loading fails.
  }
});
</script>

<template>
  <div class="flex h-full bg-slate-50">
    <!-- 左侧：对话区 -->
    <div class="flex-1 flex flex-col border-r border-slate-200 bg-white">
      <!-- 消息区 -->
      <div class="flex-1 overflow-y-auto px-6 py-6 space-y-5" v-if="hasConversation">
        <div
          v-for="turn in conversation"
          :key="turn.id"
          class="max-w-4xl mx-auto"
          :class="turn.role === 'user' ? 'flex justify-end' : ''"
        >
          <!-- 用户消息 -->
          <div
            v-if="turn.role === 'user'"
            class="bg-slate-800 text-white rounded-xl rounded-tr-sm px-4 py-2.5 max-w-[80%]"
          >
            <p class="text-sm leading-relaxed">{{ turn.text }}</p>
            <div class="text-[10px] text-slate-400 mt-1">{{ turn.timestamp }}</div>
          </div>

          <!-- 助手消息 -->
          <div v-else class="w-full">
            <div class="flex gap-3 items-start">
              <div class="w-8 h-8 rounded-full bg-slate-200 flex items-center justify-center text-slate-600 text-sm font-medium shrink-0">
                AI
              </div>
              <div class="flex-1 bg-white rounded-xl rounded-tl-sm p-4 border border-slate-200">
                <!-- 意图 Badge -->
                <IntentBadge v-if="turn.intent" :intent="turn.intent" class="mb-3" />

                <!-- 召回阶段进度条 -->
                <div v-if="turn.isStreaming && turn.phase === 'recalling'" class="mb-3">
                  <div class="flex items-center gap-2 text-xs text-slate-500 mb-2">
                    <div class="w-4 h-4 border-2 border-sky-500 border-t-transparent rounded-full animate-spin"></div>
                    <span>正在{{ turn.currentNodeLabel || "处理" }}...</span>
                  </div>
                  <div class="flex flex-wrap gap-1.5">
                    <span
                      v-for="node in turn.completedNodes || []"
                      :key="node"
                      class="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200"
                    >
                      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>
                      {{ getNodeLabel(node) }}
                    </span>
                    <span
                      v-if="turn.currentNode && turn.currentNode !== 'generate_answer'"
                      class="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 animate-pulse"
                    >
                      {{ turn.currentNodeLabel }}
                    </span>
                  </div>
                </div>

                <!-- 生成阶段指示器 -->
                <div v-if="turn.isStreaming && turn.phase === 'generating' && !turn.text" class="mb-3">
                  <div class="flex items-center gap-2 text-xs text-slate-500">
                    <div class="w-4 h-4 border-2 border-sky-500 border-t-transparent rounded-full animate-spin"></div>
                    <span>AI 正在生成回答...</span>
                  </div>
                </div>

                <!-- 回答（带引用跳转） -->
                <div class="markdown">
                  <MarkdownAnswer
                    :text="turn.text"
                    :citations="turn.citations"
                    :is-streaming="!!turn.isStreaming"
                    @citation-click="setActiveCitation"
                  />
                </div>

                <div v-if="turn.sqlResult" class="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-white">
                  <div class="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-2.5">
                    <div class="text-sm font-medium text-slate-800">结构化元数据辅助</div>
                    <div class="text-xs text-slate-600">{{ turn.sqlResult.row_count }} 行</div>
                  </div>
                  <pre class="overflow-x-auto bg-slate-900 p-4 text-xs leading-6 text-slate-300">{{ turn.sqlResult.sql }}</pre>
                  <div class="overflow-x-auto">
                    <table class="min-w-full border-collapse text-sm">
                      <thead class="bg-slate-50">
                        <tr>
                          <th v-for="col in turn.sqlResult.columns" :key="col" class="border-b border-slate-200 px-4 py-2.5 text-left font-medium text-slate-700">
                            {{ col }}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="(row, idx) in turn.sqlResult.rows" :key="idx" class="odd:bg-white even:bg-slate-50">
                          <td v-for="col in turn.sqlResult.columns" :key="col" class="border-b border-slate-100 px-4 py-2.5 text-slate-700">
                            {{ row[col] ?? "-" }}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <RetrievalTracePanel v-if="turn.retrievalTrace" :trace="turn.retrievalTrace" />

                <!-- 引用列表（简短） -->
                <div v-if="turn.citations.length > 0" class="mt-4 pt-3 border-t border-slate-200">
                  <div class="text-xs font-semibold text-slate-600 mb-2">引用证据 ({{ turn.citations.length }})</div>
                  <div class="flex flex-wrap gap-2">
                    <button
                      v-for="c in turn.citations"
                      :key="c.citation_id"
                      @click="setActiveCitation(c.citation_id)"
                      class="text-xs px-2 py-1 bg-white border border-slate-200 rounded hover:bg-brand-50 hover:border-brand-300 transition-colors"
                      :class="activeCitationId === c.citation_id ? 'bg-blue-100 border-blue-400 text-blue-800' : 'text-slate-700'"
                    >
                      [{{ c.citation_id }}] {{ c.file_name }}
                      <span class="text-slate-500 ml-1">{{ (c.score * 100).toFixed(0) }}%</span>
                    </button>
                  </div>
                </div>

                <div class="text-[10px] text-slate-500 mt-2 text-right">{{ turn.timestamp }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else class="flex-1 flex items-center justify-center">
        <div class="text-center max-w-md px-8">
          <div class="w-12 h-12 mx-auto mb-3 bg-slate-100 rounded-xl flex items-center justify-center">
            <AppIcon name="sparkles" class="h-6 w-6 text-slate-500" />
          </div>
          <h2 class="text-base font-semibold text-slate-800 mb-4">智能问答</h2>
          <div class="text-left space-y-3">
            <div class="text-xs font-medium text-slate-600 mt-6 mb-2">试试这些问题：</div>
            <button
              v-for="q in sampleQuestions"
              :key="q"
              @click="pickSample(q)"
              class="block w-full text-left text-xs border border-slate-200 rounded-lg px-4 py-3 bg-white hover:bg-slate-50 cursor-pointer transition-colors"
            >
              {{ q }}
            </button>
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="border-t border-slate-200 py-6 bg-white shrink-0">
        <div class="max-w-4xl mx-auto">
          <div v-if="error" class="mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {{ error }}
          </div>
          <div class="flex gap-3 items-end">
            <textarea
              v-model="question"
              @keydown.enter.exact.prevent="send"
              :disabled="loading"
              rows="2"
              placeholder="输入当前知识库里的航空维修或飞机特性问题"
              class="flex-1 resize-none border border-slate-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:bg-slate-50"
            />
            <div class="flex flex-col gap-2">
              <button
              v-if="!loading"
              @click="send"
              :disabled="!question.trim()"
              class="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md text-sm disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
            >
              发送
            </button>
            <button v-else @click="stopStreaming" class="px-3 py-1 bg-red-500 hover:bg-red-600 text-white font-medium rounded-md text-sm">
              停止
            </button>
            <button
              v-if="hasConversation && !loading"
              @click="clearChat"
              class="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs rounded-md transition-colors"
            >
              清空对话
            </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：证据面板 -->
    <CitationPanel
      v-if="hasConversation"
      :citations="latestCitations"
      :active-id="activeCitationId"
      @select="setActiveCitation"
    />
  </div>
</template>
