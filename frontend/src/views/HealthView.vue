<script setup lang="ts">
import { ref, onMounted } from "vue";
import { getPing, getHealth } from "@/api/client";
import type { HealthStatus } from "@/types";

const loading = ref(false);
const health = ref<HealthStatus | null>(null);
const error = ref<string | null>(null);

async function checkHealth() {
  loading.value = true;
  error.value = null;
  try {
    health.value = await getHealth();
  } catch (e) {
    error.value = (e as Error).message;
    health.value = null;
  } finally {
    loading.value = false;
  }
}

async function checkPing() {
  try {
    const r = await getPing();
    health.value = { status: r.status || (r.pong ? "pong" : "unknown"), version: "v0.1", timestamp: new Date().toISOString(), services: {} };
  } catch {
    error.value = "Ping failed";
  }
}

onMounted(checkHealth);
</script>

<template>
  <div class="mx-auto max-w-4xl">
    <div class="mb-4">
      <h2 class="text-lg font-semibold text-slate-800 flex items-center gap-2">
        <span class="text-lg">🩺</span> 健康检查
      </h2>
    </div>

    <div class="flex flex-wrap gap-2 mb-6">
      <button @click="checkHealth" :disabled="loading" class="rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-3 py-1 disabled:opacity-60 transition-colors">
        {{ loading ? "检查中..." : "重新检查" }}
      </button>
      <button @click="checkPing" :disabled="loading" class="rounded-md bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-medium px-3 py-1 transition-colors">
        简单 Ping
      </button>
    </div>

    <div v-if="error" class="mb-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">{{ error }}</div>

    <div v-if="health" class="space-y-4">
      <div class="rounded-lg border border-slate-200 bg-white p-4">
        <div class="flex items-center gap-4">
          <div class="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
            <span class="text-lg">🟢</span>
          </div>
          <div>
            <div class="text-sm font-semibold text-slate-800">API 状态: {{ health.status }}</div>
            <div class="flex items-center gap-3 mt-1">
              <span class="text-xs font-medium bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">{{ health.version }}</span>
              <span class="text-xs text-slate-500">{{ health.timestamp }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="health.services" class="grid grid-cols-2 gap-3">
        <div
          v-for="(v, k) in health.services"
          :key="k"
          class="rounded-lg border border-slate-200 bg-white p-3 flex items-center justify-between"
        >
          <span class="text-xs font-medium text-slate-700">{{ k }}</span>
          <span class="text-sm font-semibold text-slate-800">{{ v }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
