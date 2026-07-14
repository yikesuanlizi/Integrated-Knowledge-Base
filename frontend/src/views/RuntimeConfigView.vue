<script setup lang="ts">
import { ref, onMounted } from "vue";
import { Server, HardDrive, Cpu, Key, CheckCircle, XCircle, RefreshCw } from "lucide-vue-next";
import AppIcon from "@/components/AppIcon.vue";
import { getRuntimeConfig } from "@/api/client";
import type { RuntimeConfig, ModelRuntimeConfig } from "@/types";

const config = ref<RuntimeConfig | null>(null);
const loading = ref(false);
const errorMsg = ref("");

async function loadConfig() {
  loading.value = true;
  errorMsg.value = "";
  try {
    config.value = await getRuntimeConfig();
  } catch (e) {
    errorMsg.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

function formatModelName(name: string): string {
  const labels: Record<string, string> = {
    llm: "大语言模型 (LLM)",
    embedding: "向量嵌入 (Embedding)",
    reranker: "重排序 (Reranker)",
    ocr: "OCR 识别",
    vl: "视觉语言 (VL)",
  };
  return labels[name] || name;
}

onMounted(() => {
  loadConfig();
});
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-4 px-6 py-3">
    <div class="flex justify-end">
      <button
        class="flex items-center space-x-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:bg-slate-50 hover:text-slate-900 active:scale-95 disabled:opacity-60"
        @click="loadConfig"
        :disabled="loading"
      >
        <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loading }" />
        <span>{{ loading ? "加载中..." : "刷新" }}</span>
      </button>
    </div>

    <div v-if="errorMsg" class="bg-rose-50 border border-rose-200 rounded-lg p-4 text-sm text-rose-700 flex items-start gap-2">
      <XCircle class="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div>
        <div class="font-medium">加载配置失败</div>
        <div class="mt-1">{{ errorMsg }}</div>
      </div>
    </div>

    <div v-if="config" class="space-y-5">
      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex items-center gap-2">
          <HardDrive class="w-4 h-4 text-sky-600" />
          <h3 class="text-sm font-semibold text-slate-800">存储服务配置</h3>
        </div>
        <div class="p-5 space-y-5">
          <div>
            <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">PostgreSQL 知识库</h4>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">主机</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.postgres_host }}</div>
              </div>
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">端口</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.postgres_port }}</div>
              </div>
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">数据库</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.postgres_db }}</div>
              </div>
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">用户</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.postgres_user }}</div>
              </div>
            </div>
          </div>

          <div>
            <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Milvus 向量库</h4>
            <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">主机</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.milvus_host }}</div>
              </div>
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">端口</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.milvus_port }}</div>
              </div>
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">集合</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.milvus_collection }}</div>
              </div>
            </div>
          </div>

          <div>
            <h4 class="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">Elasticsearch</h4>
            <div class="grid grid-cols-2 gap-4">
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">主机</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.es_host }}</div>
              </div>
              <div class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">端口</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.es_port }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex items-center gap-2">
          <Server class="w-4 h-4 text-sky-600" />
          <h3 class="text-sm font-semibold text-slate-800">MinIO 对象存储</h3>
        </div>
        <div class="p-5">
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-slate-50 rounded-lg p-3">
              <div class="text-xs text-slate-500 mb-1">端点</div>
              <div class="text-sm font-medium text-slate-800 font-mono break-all">{{ config.storage.minio.endpoint }}</div>
            </div>
            <div class="bg-slate-50 rounded-lg p-3">
              <div class="text-xs text-slate-500 mb-1">Access Key</div>
              <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.minio.access_key }}</div>
            </div>
            <div class="bg-slate-50 rounded-lg p-3">
              <div class="text-xs text-slate-500 mb-1">Secret Key</div>
              <div class="text-sm font-medium flex items-center gap-1.5">
                <CheckCircle v-if="config.storage.minio.secret_key_configured" class="w-4 h-4 text-emerald-500" />
                <XCircle v-else class="w-4 h-4 text-rose-500" />
                <span :class="config.storage.minio.secret_key_configured ? 'text-emerald-700' : 'text-rose-700'">
                  {{ config.storage.minio.secret_key_configured ? "已配置" : "未配置" }}
                </span>
              </div>
            </div>
            <div class="bg-slate-50 rounded-lg p-3">
              <div class="text-xs text-slate-500 mb-1">Bucket</div>
              <div class="text-sm font-medium text-slate-800 font-mono">{{ config.storage.minio.bucket }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="p-4 bg-slate-50/70 border-b border-slate-200 flex items-center gap-2">
          <Cpu class="w-4 h-4 text-sky-600" />
          <h3 class="text-sm font-semibold text-slate-800">模型配置</h3>
        </div>
        <div class="p-5 space-y-4">
          <div
            v-for="(model, key) in { llm: config.llm, embedding: config.embedding, reranker: config.reranker, ocr: config.ocr, vl: config.vl } as Record<string, ModelRuntimeConfig & { dimensions?: number; instruction?: string }>"
            :key="key"
            class="border border-slate-200 rounded-lg overflow-hidden"
          >
            <div class="px-4 py-3 bg-slate-50/50 flex items-center justify-between">
              <h4 class="text-sm font-semibold text-slate-700">{{ formatModelName(key) }}</h4>
              <span class="flex items-center gap-1 text-xs font-medium" :class="model.api_key_configured ? 'text-emerald-700' : 'text-amber-700'">
                <Key class="w-3.5 h-3.5" />
                {{ model.api_key_configured ? "密钥已配置" : "密钥未配置" }}
              </span>
            </div>
            <div class="px-4 py-3 space-y-3">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div class="bg-slate-50 rounded-lg p-3">
                  <div class="text-xs text-slate-500 mb-1">模型名称</div>
                  <div class="text-sm font-medium text-slate-800 font-mono">{{ model.name }}</div>
                </div>
                <div class="bg-slate-50 rounded-lg p-3">
                  <div class="text-xs text-slate-500 mb-1">API 地址</div>
                  <div class="text-sm font-medium text-slate-800 font-mono break-all">{{ model.api_base }}</div>
                </div>
              </div>
              <div v-if="model.dimensions" class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">向量维度</div>
                <div class="text-sm font-medium text-slate-800 font-mono">{{ model.dimensions }}</div>
              </div>
              <div v-if="model.instruction" class="bg-slate-50 rounded-lg p-3">
                <div class="text-xs text-slate-500 mb-1">指令</div>
                <div class="text-sm text-slate-700">{{ model.instruction }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="bg-sky-50 border border-sky-200 rounded-lg p-4 flex items-start gap-3">
        <div class="w-8 h-8 bg-sky-100 rounded-full flex items-center justify-center flex-shrink-0">
          <span class="text-sky-600 text-sm font-bold">i</span>
        </div>
        <div class="text-sm text-sky-800">
          <div class="font-medium mb-1">配置说明</div>
          <ul class="text-sky-700 space-y-1 list-disc list-inside text-xs mt-1">
            <li>当前运行环境：<span class="font-mono font-medium">{{ config.app_env }}</span></li>
            <li>模型配置和服务地址通过代码配置或环境变量注入，密钥通过环境变量设置（不返回明文）</li>
            <li>修改配置需要重启服务后生效（已启用 --reload 热加载，修改 Python 代码会自动重启）</li>
          </ul>
        </div>
      </div>
    </div>

    <div v-if="loading && !config" class="py-20 text-center text-slate-400 text-sm">
      <RefreshCw class="w-8 h-8 mx-auto mb-3 animate-spin" />
      加载配置中...
    </div>
  </div>
</template>
