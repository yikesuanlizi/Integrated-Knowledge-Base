<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import { computed } from "vue";
import AppIcon from "@/components/AppIcon.vue";

const router = useRouter();
const route = useRoute();

const navGroups = [
  {
    label: "使用",
    items: [
      { to: "/query", label: "智能问答", icon: "send" },
    ],
  },
  {
    label: "加工",
    items: [
      { to: "/ingest", label: "文档摄入", icon: "file-up" },
      { to: "/compile", label: "知识编译", icon: "layers" },
    ],
  },
  {
    label: "浏览",
    items: [
      { to: "/wiki", label: "知识库", icon: "database" },
      { to: "/graph", label: "知识图谱", icon: "network" },
    ],
  },
  {
    label: "运营",
    items: [
      { to: "/governance", label: "治理中心", icon: "shield-check" },
      { to: "/monitor", label: "运行监控", icon: "activity" },
      { to: "/export", label: "导出管理", icon: "download" },
    ],
  },
];

const activePath = computed(() => route.path);

function go(to: string) {
  if (activePath.value !== to) router.push(to);
}
</script>

<template>
  <aside class="ak-sidebar">
    <div class="ak-brand">
      <div class="ak-brand-mark">
        <AppIcon name="plane" class="h-5 w-5" />
      </div>
      <div class="ak-brand-text">
        <div class="ak-brand-title">航空知识平台</div>
        <div class="ak-brand-subtitle">知识整理与问答工作台</div>
      </div>
    </div>
    <nav class="ak-nav">
      <template v-for="group in navGroups" :key="group.label">
        <div class="ak-nav-group-label">{{ group.label }}</div>
        <button
          v-for="item in group.items"
          :key="item.to"
          @click="go(item.to)"
          class="ak-nav-item"
          :class="{ 'is-active': activePath.startsWith(item.to) || (item.to === '/governance' && ['/review', '/eval', '/health'].some((p) => activePath.startsWith(p))) }"
        >
          <span class="ak-nav-icon">
            <AppIcon :name="item.icon" class="w-4 h-4" />
          </span>
          <span class="ak-nav-label">{{ item.label }}</span>
        </button>
      </template>
    </nav>
    <div class="ak-sidebar-foot">
      <div class="ak-sidebar-foot-line">LangGraph · Milvus · Elasticsearch</div>
      <div class="ak-sidebar-foot-version">v0.1.0</div>
    </div>
  </aside>
</template>

<style scoped>
.ak-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: 220px;
  height: 100vh;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  z-index: 40;
  border-right: 1px solid #e2e8f0;
}

.ak-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}

.ak-brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #2563eb;
}

.ak-brand-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.ak-brand-title {
  font-size: 0.9375rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.01em;
  line-height: 1.25;
}

.ak-brand-subtitle {
  font-size: 0.6875rem;
  color: #64748b;
  font-weight: 500;
  line-height: 1.25;
}

.ak-nav {
  flex: 1;
  padding: 12px 10px 8px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ak-nav-group-label {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 14px 14px 6px;
  user-select: none;
}

.ak-nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 9px 14px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #475569;
  font-size: 0.8125rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease;
  text-align: left;
  line-height: 1.4;
}

.ak-nav-item:hover {
  background: #f8fafc;
  color: #0f172a;
}

.ak-nav-item.is-active {
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
  box-shadow: inset 3px 0 0 #2563eb;
}

.ak-nav-item.is-active .ak-nav-icon {
  filter: none;
}

.ak-nav-icon {
  font-size: 1rem;
  flex-shrink: 0;
  width: 20px;
  text-align: center;
  opacity: 0.85;
}

.ak-nav-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ak-sidebar-foot {
  padding: 14px 20px;
  border-top: 1px solid #e2e8f0;
  flex-shrink: 0;
}

.ak-sidebar-foot-line {
  font-size: 0.6875rem;
  color: #64748b;
  font-weight: 500;
  margin-bottom: 4px;
}

.ak-sidebar-foot-version {
  font-size: 0.6875rem;
  color: #94a3b8;
  font-weight: 500;
}

@media (max-width: 768px) {
  .ak-sidebar {
    width: 60px;
  }
  .ak-brand-text,
  .ak-nav-label,
  .ak-nav-group-label,
  .ak-sidebar-foot {
    display: none;
  }
  .ak-brand {
    justify-content: center;
    padding: 16px 0;
  }
  .ak-nav {
    align-items: center;
    padding: 12px 6px;
  }
  .ak-nav-item {
    justify-content: center;
    padding: 10px;
  }
}
</style>
