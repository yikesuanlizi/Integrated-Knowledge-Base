import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  { path: "/", redirect: "/query" },
  {
    path: "/query",
    name: "query",
    component: () => import("@/views/QueryView.vue"),
    meta: { title: "智能问答" },
  },
  {
    path: "/data-query",
    name: "data-query",
    component: () => import("@/views/DataQueryView.vue"),
    meta: { title: "结构化元数据调试台" },
  },
  {
    path: "/ingest",
    name: "ingest",
    component: () => import("@/views/IngestView.vue"),
    meta: { title: "文档摄入" },
  },
  {
    path: "/compile",
    name: "compile",
    component: () => import("@/views/CompileView.vue"),
    meta: { title: "知识编译" },
  },
  {
    path: "/wiki",
    name: "wiki",
    component: () => import("@/views/WikiBrowser.vue"),
    meta: { title: "知识库" },
  },
  {
    path: "/wiki/:card_id",
    name: "wiki-card",
    component: () => import("@/views/WikiCardPage.vue"),
    meta: { title: "Wiki 卡片" },
  },
  {
    path: "/governance",
    name: "governance",
    component: () => import("@/views/GovernanceView.vue"),
    meta: { title: "治理中心" },
  },
  {
    path: "/review",
    redirect: { path: "/governance", query: { tab: "review" } },
  },
  {
    path: "/eval",
    redirect: { path: "/governance", query: { tab: "quality" } },
  },
  {
    path: "/health",
    redirect: { path: "/governance", query: { tab: "runtime" } },
  },
  {
    path: "/export",
    name: "export",
    component: () => import("@/views/ExportView.vue"),
    meta: { title: "导出管理" },
  },
  {
    path: "/graph",
    name: "graph",
    component: () => import("@/views/WikiGraphView.vue"),
    meta: { title: "知识图谱" },
  },
  {
    path: "/monitor",
    name: "monitor",
    component: () => import("@/views/MonitorView.vue"),
    meta: { title: "运行监控" },
  },
  {
    path: "/config",
    name: "runtime-config",
    component: () => import("@/views/RuntimeConfigView.vue"),
    meta: { title: "运行配置" },
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});
