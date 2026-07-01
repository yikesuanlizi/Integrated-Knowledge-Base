<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getIngestStatus, ingestFile, ingestPath } from "@/api/client";
import type { IngestResult, IngestStatus } from "@/types";
import AppIcon from "@/components/AppIcon.vue";

type UploadMode = "files" | "local_folder" | "remote_folder";

const files = ref<File[]>([]);
const isDragging = ref(false);
const uploading = ref(false);
const uploadProgress = ref(0);
const error = ref<string | null>(null);
const lastResult = ref<IngestResult | null>(null);
const status = ref<IngestStatus | null>(null);
const mode = ref<UploadMode>("files");
const localFolderPath = ref("");
const remoteFolderPath = ref("");

const fileInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);

const selectedSummary = computed(() => {
  if (mode.value === "files") return `${files.value.length} 个文件`;
  if (mode.value === "local_folder") return localFolderPath.value || "未选择目录";
  return remoteFolderPath.value || "未填写路径";
});

function statusNumber(key: keyof IngestStatus) {
  return status.value?.[key]?.toLocaleString() ?? "--";
}

async function refreshStatus(force = false) {
  try {
    status.value = await getIngestStatus(force);
  } catch {
    status.value = null;
  }
}

function resetQueue() {
  files.value = [];
  localFolderPath.value = "";
  remoteFolderPath.value = "";
  uploadProgress.value = 0;
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files) {
    files.value = Array.from(input.files);
  }
}

function onFolderSelect(e: Event) {
  const input = e.target as HTMLInputElement;
  const picked = input.files ? Array.from(input.files) : [];
  files.value = picked;
  const first = picked[0] as File & { webkitRelativePath?: string };
  if (first?.webkitRelativePath) {
    const top = first.webkitRelativePath.split("/")[0];
    localFolderPath.value = top || "已选择目录";
  } else if (picked.length > 0) {
    localFolderPath.value = "已选择目录";
  }
}

function onDrop(e: DragEvent) {
  e.preventDefault();
  isDragging.value = false;
  if (mode.value !== "files") return;
  if (e.dataTransfer?.files) {
    files.value = Array.from(e.dataTransfer.files);
  }
}

async function uploadFilesIndividually() {
  const results: IngestResult[] = [];
  const total = Math.max(1, files.value.length);

  for (let index = 0; index < files.value.length; index += 1) {
    const file = files.value[index];
    const base = index / total;
    const portion = 1 / total;

    const result = await ingestFile(file, (p) => {
      const normalized = Math.max(0, Math.min(1, p || 0));
      uploadProgress.value = Math.round((base + normalized * portion) * 100);
    });
    results.push(result);
    uploadProgress.value = Math.round(((index + 1) / total) * 100);
  }

  return results;
}

async function ingestFolderPath(path: string) {
  uploadProgress.value = 10;
  const result = await ingestPath(path);
  uploadProgress.value = 100;
  return result;
}

async function doUpload() {
  if (uploading.value) return;
  error.value = null;
  uploading.value = true;
  uploadProgress.value = 0;

  try {
    if (mode.value === "files") {
      if (files.value.length === 0) return;
      const results = await uploadFilesIndividually();
      lastResult.value = results[results.length - 1] || null;
    } else if (mode.value === "local_folder") {
      if (!remoteFolderPath.value && !localFolderPath.value) {
        throw new Error("请先选择本地目录");
      }
      const path = remoteFolderPath.value || localFolderPath.value;
      lastResult.value = await ingestFolderPath(path);
    } else {
      if (!remoteFolderPath.value.trim()) {
        throw new Error("请填写远程目录路径");
      }
      lastResult.value = await ingestFolderPath(remoteFolderPath.value.trim());
    }
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    uploading.value = false;
    if (mode.value === "files") {
      files.value = [];
    }
    await refreshStatus(true);
  }
}

onMounted(refreshStatus);
</script>

<template>
  <div class="ingest-page max-w-7xl mx-auto space-y-6 px-6 pb-8">
    <div class="ingest-summary-stack">
      <div class="ingest-summary-grid">
        <div class="ingest-summary-card bg-white rounded-xl border shadow-sm">
          <div class="flex justify-between items-center">
            <span class="text-sm text-slate-600">文档</span>
            <span class="text-xs px-2 py-1 rounded bg-slate-100 text-slate-600">PG</span>
          </div>
          <div class="mt-3 text-3xl font-semibold text-slate-800">{{ statusNumber("documents") }}</div>
          <div class="text-xs text-slate-400 mt-1">已入库文档数</div>
        </div>
        <div class="ingest-summary-card bg-white rounded-xl border shadow-sm">
          <div class="flex justify-between items-center">
            <span class="text-sm text-slate-600">切块真相源</span>
            <span class="text-xs px-2 py-1 rounded bg-blue-50 text-blue-600">PG</span>
          </div>
          <div class="mt-3 text-3xl font-semibold text-slate-800">{{ statusNumber("pg_chunks") }}</div>
          <div class="text-xs text-slate-400 mt-1">总切片数</div>
        </div>
        <div class="ingest-summary-card bg-white rounded-xl border shadow-sm">
          <div class="flex justify-between items-center">
            <span class="text-sm text-slate-600">向量索引</span>
            <span class="text-xs px-2 py-1 rounded bg-indigo-50 text-indigo-600">Milvus</span>
          </div>
          <div class="mt-3 text-3xl font-semibold text-slate-800">{{ statusNumber("milvus_chunks") }}</div>
          <div class="text-xs text-slate-400 mt-1">已通过切片向量数</div>
        </div>
        <div class="ingest-summary-card bg-white rounded-xl border shadow-sm">
          <div class="flex justify-between items-center">
            <span class="text-sm text-slate-600">全文索引</span>
            <span class="text-xs px-2 py-1 rounded bg-orange-50 text-orange-600">Elasticsearch</span>
          </div>
          <div class="mt-3 text-3xl font-semibold text-slate-800">{{ statusNumber("elasticsearch_chunks") }}</div>
          <div class="text-xs text-slate-400 mt-1">已通过切片索引数</div>
        </div>
      </div>

      <div class="ingest-review-strip">
        <div class="ingest-review-card border-amber-200 bg-amber-50 text-amber-800">
          <div class="ingest-review-label text-amber-700">待审核切片</div>
          <div class="ingest-review-value">{{ statusNumber("review_chunks") }}</div>
        </div>
        <div class="ingest-review-card border-blue-200 bg-blue-50 text-blue-800">
          <div class="ingest-review-label text-blue-700">已通过切片</div>
          <div class="ingest-review-value">{{ statusNumber("approved_chunks") }}</div>
        </div>
        <div class="ingest-review-card border-rose-200 bg-rose-50 text-rose-800">
          <div class="ingest-review-label text-rose-700">已驳回切片</div>
          <div class="ingest-review-value">{{ statusNumber("rejected_chunks") }}</div>
        </div>
      </div>
    </div>

    <div class="bg-white border rounded-xl shadow-sm">
      <div class="px-6 py-4 border-b flex items-center justify-between">
        <h2 class="font-medium text-slate-800 text-sm">文档摄入</h2>
        <button
          type="button"
          class="text-xs text-slate-500 hover:text-slate-700"
          @click="refreshStatus(true)"
        >
          刷新状态
        </button>
      </div>
      <div class="p-6 space-y-5">
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
            :class="mode === 'files' ? 'border-indigo-600 bg-indigo-50 text-indigo-700' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'"
            @click="mode = 'files'; resetQueue()"
          >
            单文件
          </button>
          <button
            type="button"
            class="rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
            :class="mode === 'local_folder' ? 'border-indigo-600 bg-indigo-50 text-indigo-700' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'"
            @click="mode = 'local_folder'; resetQueue()"
          >
            本地目录
          </button>
          <button
            type="button"
            class="rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
            :class="mode === 'remote_folder' ? 'border-indigo-600 bg-indigo-50 text-indigo-700' : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'"
            @click="mode = 'remote_folder'; resetQueue()"
          >
            远程目录
          </button>
        </div>

        <div
          v-if="mode === 'files'"
          class="border-2 border-dashed border-gray-200 rounded-xl p-10 text-center bg-gray-50 transition"
          :class="isDragging ? 'border-indigo-400 bg-indigo-50' : ''"
          @dragenter.prevent="isDragging = true"
          @dragover.prevent="isDragging = true"
          @dragleave="isDragging = false"
          @drop="onDrop"
        >
          <div class="flex flex-col items-center gap-3">
            <div class="w-12 h-12 rounded-full bg-indigo-50 flex items-center justify-center text-indigo-600">
              <AppIcon name="file-up" class="h-6 w-6" />
            </div>
            <p class="text-sm text-slate-600">
              将文件拖拽到此处，或
              <span class="text-indigo-600 font-medium cursor-pointer" @click.stop="fileInput?.click()">点击选择文件</span>
            </p>
            <button type="button" class="mt-3 px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700" @click="fileInput?.click()">
              选择文件
            </button>
          </div>
          <input ref="fileInput" type="file" multiple accept=".pdf,.docx,.doc,.txt,.md,.markdown" class="hidden" @change="onFileSelect" />
        </div>

        <div v-else-if="mode === 'local_folder'" class="rounded-xl border border-slate-200 bg-slate-50 p-5 space-y-4">
          <div class="flex flex-wrap items-center gap-3">
            <button
              type="button"
              class="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700"
              @click="folderInput?.click()"
            >
              选择目录
            </button>
            <div class="text-sm text-slate-600 truncate">{{ localFolderPath || "尚未选择目录" }}</div>
          </div>
          <input
            ref="folderInput"
            type="file"
            webkitdirectory
            directory
            multiple
            class="hidden"
            @change="onFolderSelect"
          />
          <input
            v-model="remoteFolderPath"
            type="text"
            placeholder="例如 E:\\langchain\\RAG\\测试文档"
            class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
          />
        </div>

        <div v-else class="rounded-xl border border-slate-200 bg-slate-50 p-5 space-y-4">
          <input
            v-model="remoteFolderPath"
            type="text"
            placeholder="例如 E:\\langchain\\RAG\\测试文档"
            class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700"
          />
        </div>

        <div class="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
          当前选择: {{ selectedSummary }}
        </div>

        <div v-if="mode === 'files' && files.length > 0" class="space-y-3">
          <div v-for="f in files" :key="`${f.name}-${f.size}`" class="flex items-center justify-between p-3 border rounded-lg bg-gray-50">
            <div class="flex items-center gap-3 min-w-0">
              <span class="font-medium text-slate-800 truncate">{{ f.name }}</span>
              <span class="text-xs text-slate-500">{{ uploading ? "上传中" : "等待上传" }}</span>
            </div>
            <span class="text-xs text-slate-500 shrink-0">{{ (f.size / 1024 / 1024).toFixed(2) }} MB</span>
          </div>
        </div>

        <div class="flex gap-3">
          <button
            @click="doUpload"
            :disabled="uploading"
            class="px-4 py-2 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-60"
          >
            {{ uploading ? "处理中..." : "开始摄入" }}
          </button>
          <button
            @click="resetQueue"
            :disabled="uploading"
            class="px-4 py-2 bg-gray-100 text-slate-600 text-sm rounded-lg hover:bg-gray-200"
          >
            清空
          </button>
        </div>

        <div v-if="uploading" class="space-y-2">
          <div class="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div class="h-full bg-indigo-600 rounded-full transition-all duration-300" :style="{ width: `${uploadProgress}%` }"></div>
          </div>
          <div class="text-xs text-slate-500 text-right">{{ uploadProgress }}%</div>
        </div>
      </div>
    </div>

    <div v-if="error" class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
      {{ error }}
    </div>

    <div v-if="lastResult" class="bg-white border rounded-xl shadow-sm p-5 space-y-4">
      <div class="flex items-center gap-2">
        <AppIcon name="box" class="h-4 w-4 text-slate-500" />
        <span class="text-sm font-medium text-slate-800">最近摄入结果</span>
      </div>
        <div class="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div class="rounded-lg bg-indigo-50 border border-indigo-100 p-3 text-center">
          <div class="text-xs font-medium text-indigo-600 mb-1">成功</div>
          <div class="text-xl font-semibold text-indigo-700">{{ lastResult.ingested }}</div>
        </div>
        <div class="rounded-lg bg-gray-50 border border-gray-100 p-3 text-center">
          <div class="text-xs font-medium text-gray-600 mb-1">跳过</div>
          <div class="text-xl font-semibold text-gray-700">{{ lastResult.skipped }}</div>
        </div>
        <div class="rounded-lg bg-red-50 border border-red-100 p-3 text-center">
          <div class="text-xs font-medium text-red-600 mb-1">失败</div>
          <div class="text-xl font-semibold text-red-700">{{ lastResult.failed }}</div>
        </div>
        <div class="rounded-lg bg-gray-50 border border-gray-100 p-3 text-center">
          <div class="text-xs font-medium text-gray-600 mb-1">批次 ID</div>
          <div class="text-sm font-mono text-gray-700 truncate">{{ lastResult.build_id || "-" }}</div>
        </div>
        <div class="rounded-lg bg-slate-50 border border-slate-100 p-3 text-center">
          <div class="text-xs font-medium text-slate-600 mb-1">Wiki</div>
          <div class="text-sm font-semibold text-slate-700">{{ lastResult.wiki?.status || "-" }}</div>
        </div>
      </div>

      <ul class="space-y-2">
        <li v-for="doc in lastResult.documents" :key="doc.filename" class="flex items-center gap-2 text-sm text-slate-700">
          <AppIcon v-if="doc.status !== 'failed'" name="check" class="h-4 w-4 text-indigo-600" />
          <AppIcon v-else name="x-circle" class="h-4 w-4 text-red-600" />
          <span class="font-medium">{{ doc.filename }}</span>
          <span v-if="doc.chunks" class="text-xs text-slate-500 bg-gray-100 px-2 py-0.5 rounded">{{ doc.chunks }} 个切片</span>
          <span v-if="doc.status === 'failed'" class="text-xs text-red-600">{{ doc.error }}</span>
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.ingest-page {
  padding-top: 1.5rem;
}

.ingest-summary-stack {
  display: grid;
  gap: 0.75rem;
}

.ingest-summary-grid {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: 0.75rem;
}

.ingest-summary-card {
  min-height: 104px;
  padding: 1rem 1.125rem;
}

.ingest-review-strip {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: 0.75rem;
}

.ingest-review-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  border-width: 1px;
  border-style: solid;
  border-radius: 0.75rem;
  padding: 0.875rem 1rem;
}

.ingest-review-label {
  font-size: 12px;
  font-weight: 600;
}

.ingest-review-value {
  font-size: 1.5rem;
  line-height: 1;
  font-weight: 700;
}

@media (min-width: 768px) {
  .ingest-summary-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .ingest-review-strip {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
