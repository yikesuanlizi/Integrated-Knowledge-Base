<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute } from "vue-router";
import AppSidebar from "@/components/AppSidebar.vue";
import { getHealth } from "@/api/client";
import type { HealthStatus } from "@/types";

const route = useRoute();
const pageTitle = computed(() => (route.meta?.title as string) || "航空维修知识平台");

const health = ref<HealthStatus | null>(null);
const loading = ref(false);
const errorMsg = ref("");
const expanded = ref(false);
let timer: ReturnType<typeof setInterval> | null = null;

async function checkHealth() {
  loading.value = true;
  try {
    health.value = await getHealth();
    errorMsg.value = "";
  } catch (e) {
    errorMsg.value = "连接失败";
    health.value = null;
  } finally {
    loading.value = false;
  }
}

const isHealthy = computed(() => health.value?.status === "healthy");
const isDegraded = computed(() => health.value?.status === "degraded");
const isUnhealthy = computed(() => health.value?.status === "unhealthy");
const isError = computed(() => !!errorMsg.value || isUnhealthy.value);

const statusText = computed(() => {
  if (errorMsg.value) return "连接异常";
  if (isHealthy.value) return "服务正常";
  if (isUnhealthy.value) return "服务异常";
  if (isDegraded.value) return "服务降级";
  return "检测中...";
});

const dotColor = computed(() => {
  if (errorMsg.value || isUnhealthy.value) return "#ef4444";
  if (isDegraded.value) return "#f59e0b";
  if (isHealthy.value) return "#22c55e";
  return "#eab308";
});

const failedServices = computed(() => {
  if (!health.value?.services) return [];
  return Object.entries(health.value.services as Record<string, { ok: boolean; error?: string }>)
    .filter(([, v]) => !v.ok)
    .map(([k]) => SERVICE_NAMES[k] || k);
});

const SERVICE_NAMES: Record<string, string> = {
  milvus: "Milvus 向量库",
  wiki_pg: "PostgreSQL 知识库",
  elasticsearch: "Elasticsearch",
  minio: "MinIO 对象存储",
  llm: "LLM 大模型",
  embedding: "Embedding 嵌入",
  reranker: "Reranker 重排序",
};

onMounted(() => {
  checkHealth();
  timer = setInterval(checkHealth, 30000);
});

onUnmounted(() => {
  if (timer) clearInterval(timer);
});

function toggleExpanded() {
  expanded.value = !expanded.value;
}
</script>

<template>
  <div class="ak-shell">
    <AppSidebar />
    <div class="ak-main">
      <header class="ak-topbar">
        <div class="ak-topbar-left">
          <h1 class="ak-topbar-title">{{ pageTitle }}</h1>
        </div>
        <div class="ak-health-wrapper" @click="toggleExpanded">
          <div class="ak-health" :class="{ 'ak-health-degraded': isDegraded, 'ak-health-error': isError }">
            <span class="ak-health-dot" :style="{ background: dotColor, boxShadow: `0 0 0 2px ${dotColor}33` }"></span>
            <span class="ak-health-text">{{ statusText }}</span>
          </div>
          <div v-if="expanded && (failedServices.length > 0 || health)" class="ak-health-popover">
            <div v-if="health" class="ak-health-popover-title">服务状态详情</div>
            <div v-if="health?.services" class="ak-health-service-list">
              <div v-for="(svc, key) in health.services as Record<string, { ok: boolean; count?: number; chunks?: number; cards?: number; reviews?: number; entities?: number; model?: string; bucket?: string; bucket_exists?: boolean; error?: string }>"
                   :key="key"
                   class="ak-health-service-item">
                <span class="ak-health-dot-small" :class="svc.ok ? 'dot-ok' : 'dot-err'"></span>
                <span class="ak-health-svc-name">{{ SERVICE_NAMES[key] || key }}</span>
                <span class="ak-health-svc-meta" :class="{ 'ak-health-svc-err': !svc.ok }">
                  <template v-if="svc.ok">
                    <template v-if="svc.chunks !== undefined">{{ svc.chunks }} chunks</template>
                    <template v-else-if="svc.cards !== undefined">{{ svc.cards }} cards</template>
                    <template v-else-if="svc.bucket !== undefined">{{ svc.bucket }}</template>
                    <template v-else-if="svc.model">{{ svc.model }}</template>
                  </template>
                  <template v-else>{{ svc.error?.slice(0, 60) }}</template>
                </span>
              </div>
            </div>
            <div v-if="failedServices.length > 0" class="ak-health-warn">
              {{ failedServices.length }} 个服务异常
            </div>
            <button class="ak-health-refresh" @click.stop="checkHealth" :disabled="loading">
              {{ loading ? "检测中..." : "重新检测" }}
            </button>
          </div>
        </div>
      </header>
      <main class="ak-content">
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </main>
    </div>
  </div>
</template>

<style scoped>
.ak-shell {
  display: flex;
  min-height: 100vh;
  background: #ffffff;
}

.ak-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  margin-left: 220px;
}

.ak-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 52px;
  padding: 0 20px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  position: sticky;
  top: 0;
  z-index: 30;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.ak-topbar-left {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.ak-topbar-title {
  font-size: 1rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0;
  letter-spacing: -0.01em;
}

.ak-health-wrapper {
  position: relative;
  cursor: pointer;
}

.ak-health {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.75rem;
  color: #334155;
  font-weight: 500;
  background: #ffffff;
  padding: 3px 10px;
  border-radius: 9999px;
  border: 1px solid #cbd5e1;
  transition: all 0.15s ease;
}

.ak-health:hover {
  border-color: #94a3b8;
}

.ak-health-degraded {
  border-color: #f59e0b;
  color: #b45309;
  background: #fffbeb;
}

.ak-health-error {
  border-color: #fca5a5;
  color: #b91c1c;
  background: #fef2f2;
}

.ak-health-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  transition: all 0.3s ease;
}

.ak-health-popover {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  min-width: 280px;
  max-width: 360px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08);
  padding: 12px;
  z-index: 50;
}

.ak-health-popover-title {
  font-size: 0.8125rem;
  font-weight: 600;
  color: #0f172a;
  margin-bottom: 8px;
}

.ak-health-service-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ak-health-service-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.75rem;
}

.ak-health-dot-small {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-ok {
  background: #22c55e;
}

.dot-err {
  background: #ef4444;
}

.ak-health-svc-name {
  color: #334155;
  font-weight: 500;
  min-width: 90px;
}

.ak-health-svc-meta {
  color: #64748b;
  font-size: 0.6875rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ak-health-svc-err {
  color: #dc2626;
}

.ak-health-warn {
  margin-top: 10px;
  padding: 6px 10px;
  background: #fef2f2;
  border-radius: 6px;
  font-size: 0.75rem;
  color: #b91c1c;
  font-weight: 500;
}

.ak-health-refresh {
  margin-top: 10px;
  width: 100%;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  font-size: 0.75rem;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
}

.ak-health-refresh:hover {
  background: #f1f5f9;
}

.ak-health-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ak-content {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  min-height: 0;
}

@media (max-width: 768px) {
  .ak-main {
    margin-left: 0;
  }
  .ak-topbar {
    padding: 0 12px;
  }
  .ak-content {
    padding: 16px;
  }
  .ak-health-popover {
    right: -10px;
    min-width: 240px;
  }
}
</style>
