<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppSidebar from "@/components/AppSidebar.vue";

const route = useRoute();
const pageTitle = computed(() => (route.meta?.title as string) || "航空知识平台");
</script>

<template>
  <div class="ak-shell">
    <AppSidebar />
    <div class="ak-main">
      <header class="ak-topbar">
        <div class="ak-topbar-left">
          <h1 class="ak-topbar-title">{{ pageTitle }}</h1>
        </div>
        <div class="ak-health">
          <span class="ak-health-dot"></span>
          <span class="ak-health-text">服务正常</span>
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

.ak-topbar-subtitle {
  font-size: 0.7rem;
  color: #64748b;
  font-weight: 400;
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
}

.ak-health-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 2px rgba(34, 197, 94, 0.2);
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
  .ak-topbar-subtitle {
    display: none;
  }
  .ak-content {
    padding: 16px;
  }
}
</style>
