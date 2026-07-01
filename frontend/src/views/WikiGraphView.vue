<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import * as d3 from "d3";
import { listWikiCards } from "@/api/client";
import type { WikiCardInfo } from "@/types";
import AppIcon from "@/components/AppIcon.vue";

type GraphNode = {
  id: string;
  title: string;
  card_type: string;
  content: string;
  source_ref: string;
  status: string;
  confidence: number;
  linked_chunks: string[];
  degree: number;
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
};

type GraphLink = {
  source: string | GraphNode;
  target: string | GraphNode;
  relation: "共享切片" | "同源文档" | "同类知识";
  strength: number;
};

const router = useRouter();
const container = ref<HTMLDivElement | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const cards = ref<WikiCardInfo[]>([]);
const selectedId = ref("");
const typeFilter = ref("all");
const statusFilter = ref("approved");
const keyword = ref("");

let simulation: d3.Simulation<GraphNode, GraphLink> | null = null;

const typeMeta: Record<string, { label: string; color: string }> = {
  definition: { label: "定义", color: "#2563eb" },
  concept: { label: "概念", color: "#0891b2" },
  procedure: { label: "流程", color: "#0f766e" },
  faq: { label: "问答", color: "#d97706" },
  fault: { label: "故障", color: "#dc2626" },
  default: { label: "其他", color: "#64748b" },
};

const filteredCards = computed(() => {
  const q = keyword.value.trim().toLowerCase();
  return cards.value.filter((card) => {
    const typeOk = typeFilter.value === "all" || card.card_type === typeFilter.value;
    const statusOk = statusFilter.value === "all" || card.status === statusFilter.value;
    const text = `${card.title} ${card.content} ${card.source_ref}`.toLowerCase();
    return typeOk && statusOk && (!q || text.includes(q));
  });
});

const graphData = computed(() => buildGraph(filteredCards.value));
const selectedNode = computed(() => graphData.value.nodes.find((node) => node.id === selectedId.value) || graphData.value.nodes[0] || null);
const neighborNodes = computed(() => {
  const selected = selectedNode.value;
  if (!selected) return [];
  const neighbors = new Map<string, { node: GraphNode; relation: string }>();
  for (const link of graphData.value.links) {
    const sourceId = typeof link.source === "string" ? link.source : link.source.id;
    const targetId = typeof link.target === "string" ? link.target : link.target.id;
    const otherId = sourceId === selected.id ? targetId : targetId === selected.id ? sourceId : "";
    if (!otherId) continue;
    const node = graphData.value.nodes.find((item) => item.id === otherId);
    if (node) neighbors.set(otherId, { node, relation: link.relation });
  }
  return Array.from(neighbors.values()).slice(0, 12);
});

const graphStats = computed(() => ({
  nodes: graphData.value.nodes.length,
  links: graphData.value.links.length,
  chunks: new Set(graphData.value.nodes.flatMap((node) => node.linked_chunks)).size,
}));

const visibleTypes = computed(() => {
  const types = new Set(graphData.value.nodes.map((node) => node.card_type || "default"));
  return Object.entries(typeMeta).filter(([key]) => key !== "default" ? types.has(key) : types.has("default"));
});

async function loadGraph() {
  loading.value = true;
  error.value = null;
  try {
    const first = await listWikiCards(1, 100, undefined, statusFilter.value === "all" ? undefined : statusFilter.value);
    const pages = [first];
    const totalPages = Math.min(5, Math.ceil(first.total / first.page_size));
    for (let page = 2; page <= totalPages; page += 1) {
      pages.push(await listWikiCards(page, 100, undefined, statusFilter.value === "all" ? undefined : statusFilter.value));
    }
    cards.value = pages.flatMap((page) => page.cards);
    selectedId.value = "";
    await nextTick();
    renderGraph();
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

function buildGraph(sourceCards: WikiCardInfo[]) {
  const nodes: GraphNode[] = sourceCards.map((card) => ({
    id: card.card_id,
    title: card.title || card.card_id,
    card_type: card.card_type || "default",
    content: card.content || "",
    source_ref: card.source_ref || "",
    status: card.status || "",
    confidence: card.confidence ?? card.score ?? 0.5,
    linked_chunks: card.linked_chunks || [],
    degree: 0,
  }));

  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const links: GraphLink[] = [];
  const seen = new Set<string>();

  function addLink(a: GraphNode, b: GraphNode, relation: GraphLink["relation"], strength: number) {
    if (a.id === b.id) return;
    const key = [a.id, b.id].sort().join("::");
    if (seen.has(key)) return;
    seen.add(key);
    links.push({ source: a.id, target: b.id, relation, strength });
    a.degree += 1;
    b.degree += 1;
  }

  const byChunk = new Map<string, GraphNode[]>();
  for (const node of nodes) {
    for (const chunk of node.linked_chunks) {
      if (!byChunk.has(chunk)) byChunk.set(chunk, []);
      byChunk.get(chunk)?.push(node);
    }
  }
  for (const group of byChunk.values()) connectGroup(group, "共享切片", 1.1, addLink);

  const bySource = groupBy(nodes, (node) => node.source_ref || "unknown");
  for (const group of bySource.values()) connectGroup(group, "同源文档", 0.55, addLink, 18);

  const byType = groupBy(nodes, (node) => node.card_type || "default");
  for (const group of byType.values()) connectGroup(group, "同类知识", 0.25, addLink, 10);

  const stableLinks = links.filter((link) => nodeMap.has(String(link.source)) && nodeMap.has(String(link.target)));
  return { nodes, links: stableLinks };
}

function groupBy<T>(items: T[], getKey: (item: T) => string) {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const key = getKey(item);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)?.push(item);
  }
  return groups;
}

function connectGroup(
  group: GraphNode[],
  relation: GraphLink["relation"],
  strength: number,
  addLink: (a: GraphNode, b: GraphNode, relation: GraphLink["relation"], strength: number) => void,
  maxLinks = 32,
) {
  if (group.length < 2) return;
  const sorted = [...group].sort((a, b) => b.confidence - a.confidence);
  let count = 0;
  for (let i = 0; i < sorted.length; i += 1) {
    for (let j = i + 1; j < sorted.length; j += 1) {
      addLink(sorted[i], sorted[j], relation, strength);
      count += 1;
      if (count >= maxLinks) return;
    }
  }
}

function renderGraph() {
  if (!container.value || typeof window === "undefined") return;
  if (simulation) simulation.stop();
  container.value.innerHTML = "";

  const width = container.value.clientWidth || 900;
  const height = container.value.clientHeight || 620;
  const { nodes, links } = graphData.value;
  if (!selectedId.value && nodes[0]) selectedId.value = nodes[0].id;

  const svg = d3.select(container.value)
    .append("svg")
    .attr("width", width)
    .attr("height", height)
    .attr("viewBox", [0, 0, width, height]);

  const root = svg.append("g");
  svg.call(
    d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.45, 2.2])
      .on("zoom", (event) => root.attr("transform", event.transform.toString())),
  );

  const link = root.append("g")
    .selectAll("line")
    .data(links)
    .join("line")
    .attr("stroke", (d) => d.relation === "共享切片" ? "#38bdf8" : d.relation === "同源文档" ? "#94a3b8" : "#cbd5e1")
    .attr("stroke-opacity", (d) => d.relation === "共享切片" ? 0.65 : 0.32)
    .attr("stroke-width", (d) => d.relation === "共享切片" ? 1.5 : 1);

  const node = root.append("g")
    .selectAll("g")
    .data(nodes)
    .join("g")
    .attr("class", "graph-node")
    .style("cursor", "pointer")
    .on("click", (_event, d) => {
      selectedId.value = d.id;
      updateSelection();
    })
    .on("dblclick", (_event, d) => router.push({ path: `/wiki/${d.id}`, query: { from: "graph" } }))
    .call(drag() as any);

  node.append("circle")
    .attr("r", (d) => nodeRadius(d))
    .attr("fill", (d) => typeMeta[d.card_type]?.color || typeMeta.default.color)
    .attr("fill-opacity", 0.88)
    .attr("stroke", "#ffffff")
    .attr("stroke-width", 2);

  node.append("text")
    .attr("dy", (d) => nodeRadius(d) + 13)
    .attr("text-anchor", "middle")
    .attr("class", "graph-node-label")
    .text((d) => shortTitle(d.title));

  node.append("title").text((d) => `${d.title}\n${typeLabel(d.card_type)}\n双击打开卡片`);

  simulation = d3.forceSimulation<GraphNode>(nodes)
    .force("link", d3.forceLink<GraphNode, GraphLink>(links).id((d) => d.id).distance((d) => 110 - d.strength * 28).strength((d) => d.strength * 0.18))
    .force("charge", d3.forceManyBody().strength(-260))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("x", d3.forceX(width / 2).strength(0.035))
    .force("y", d3.forceY(height / 2).strength(0.04))
    .force("collision", d3.forceCollide<GraphNode>().radius((d) => nodeRadius(d) + 30));

  simulation.on("tick", () => {
    link
      .attr("x1", (d: any) => d.source.x)
      .attr("y1", (d: any) => d.source.y)
      .attr("x2", (d: any) => d.target.x)
      .attr("y2", (d: any) => d.target.y);

    node.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
  });

  updateSelection();

  function updateSelection() {
    node.select("circle")
      .attr("stroke", (d) => d.id === selectedId.value ? "#0f172a" : "#ffffff")
      .attr("stroke-width", (d) => d.id === selectedId.value ? 3 : 2);
  }

  function drag() {
    function dragstarted(event: any) {
      if (!event.active && simulation) simulation.alphaTarget(0.25).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    }
    function dragged(event: any) {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    }
    function dragended(event: any) {
      if (!event.active && simulation) simulation.alphaTarget(0);
      event.subject.fx = null;
      event.subject.fy = null;
    }
    return d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended);
  }
}

function nodeRadius(node: GraphNode) {
  return 13 + Math.min(12, node.degree * 1.3) + Math.max(0, node.confidence - 0.5) * 8;
}

function shortTitle(title: string) {
  const clean = title.replace(/\s+/g, "");
  return clean.length > 12 ? `${clean.slice(0, 12)}...` : clean;
}

function typeLabel(type: string | undefined) {
  return typeMeta[type || "default"]?.label || typeMeta.default.label;
}

function statusLabel(status: string) {
  if (status === "approved") return "已通过";
  if (status === "review") return "待审核";
  if (status === "rejected") return "已驳回";
  return status || "未知";
}

function openSelectedCard() {
  if (selectedNode.value) router.push({ path: `/wiki/${selectedNode.value.id}`, query: { from: "graph" } });
}

watch(filteredCards, () => {
  void nextTick(renderGraph);
});

watch(statusFilter, () => {
  void loadGraph();
});

onMounted(loadGraph);

onUnmounted(() => {
  if (simulation) simulation.stop();
});
</script>

<template>
  <div class="graph-page">
    <div class="graph-toolbar">
      <div class="graph-filters">
        <input
          v-model="keyword"
          type="search"
          placeholder="搜索知识点"
          class="graph-search"
        />
        <select v-model="typeFilter" class="graph-select">
          <option value="all">全部类型</option>
          <option value="definition">定义</option>
          <option value="concept">概念</option>
          <option value="procedure">流程</option>
          <option value="faq">问答</option>
          <option value="fault">故障</option>
        </select>
        <select v-model="statusFilter" class="graph-select">
          <option value="approved">已通过</option>
          <option value="review">待审核</option>
          <option value="rejected">已驳回</option>
          <option value="all">全部状态</option>
        </select>
      </div>
      <button class="graph-refresh" :disabled="loading" @click="loadGraph">
        <AppIcon name="refresh-cw" class="h-4 w-4" />
        <span>{{ loading ? "加载中" : "刷新" }}</span>
      </button>
    </div>

    <div v-if="error" class="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{{ error }}</div>

    <div class="graph-layout">
      <section class="graph-canvas-card">
        <div class="graph-stat-row">
          <span>{{ graphStats.nodes }} 个知识点</span>
          <span>{{ graphStats.links }} 条关系</span>
          <span>{{ graphStats.chunks }} 个来源切片</span>
        </div>
        <div v-if="!loading && graphStats.nodes === 0" class="graph-empty">没有符合筛选条件的 Wiki 卡片</div>
        <div ref="container" class="graph-canvas"></div>
        <div class="graph-legend">
          <div v-for="[type, meta] in visibleTypes" :key="type" class="graph-legend-item">
            <span class="graph-dot" :style="{ backgroundColor: meta.color }"></span>
            <span>{{ meta.label }}</span>
          </div>
        </div>
      </section>

      <aside class="graph-side">
        <template v-if="selectedNode">
          <div class="graph-detail-card">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="graph-type-pill" :style="{ borderColor: typeMeta[selectedNode.card_type]?.color || typeMeta.default.color }">
                  {{ typeLabel(selectedNode.card_type) }}
                </div>
                <h2 class="mt-3 text-base font-semibold leading-6 text-slate-900">{{ selectedNode.title }}</h2>
              </div>
              <button class="graph-open" @click="openSelectedCard">打开</button>
            </div>
            <div class="mt-4 grid grid-cols-2 gap-3 text-xs">
              <div class="graph-metric">
                <div class="text-slate-500">状态</div>
                <div class="mt-1 font-semibold text-slate-900">{{ statusLabel(selectedNode.status) }}</div>
              </div>
              <div class="graph-metric">
                <div class="text-slate-500">置信度</div>
                <div class="mt-1 font-semibold text-slate-900">{{ Math.round(selectedNode.confidence * 100) }}%</div>
              </div>
              <div class="graph-metric">
                <div class="text-slate-500">关系数</div>
                <div class="mt-1 font-semibold text-slate-900">{{ selectedNode.degree }}</div>
              </div>
              <div class="graph-metric">
                <div class="text-slate-500">来源切片</div>
                <div class="mt-1 font-semibold text-slate-900">{{ selectedNode.linked_chunks.length }}</div>
              </div>
            </div>
            <div class="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div class="text-xs font-medium text-slate-500">来源</div>
              <div class="mt-1 break-all text-xs leading-5 text-slate-700">{{ selectedNode.source_ref || "暂无" }}</div>
            </div>
            <div class="mt-4 text-xs leading-6 text-slate-700">
              {{ selectedNode.content.slice(0, 260) }}{{ selectedNode.content.length > 260 ? "..." : "" }}
            </div>
          </div>

          <div class="graph-detail-card">
            <div class="text-sm font-semibold text-slate-900">相邻知识点</div>
            <div v-if="neighborNodes.length === 0" class="mt-3 rounded-lg border border-dashed border-slate-200 p-4 text-center text-xs text-slate-500">
              暂无可解释关系
            </div>
            <button
              v-for="item in neighborNodes"
              :key="item.node.id"
              class="graph-neighbor"
              @click="selectedId = item.node.id"
            >
              <span class="min-w-0 truncate text-left">{{ item.node.title }}</span>
              <span class="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-600">{{ item.relation }}</span>
            </button>
          </div>
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.graph-page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 12px 24px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.graph-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.graph-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.graph-search,
.graph-select {
  height: 36px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #ffffff;
  padding: 0 11px;
  font-size: 13px;
  color: #334155;
  outline: none;
}

.graph-search {
  width: 220px;
}

.graph-refresh,
.graph-open {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #ffffff;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.graph-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 16px;
  align-items: start;
}

.graph-canvas-card,
.graph-detail-card {
  border: 1px solid #dbe3ea;
  border-radius: 10px;
  background: #ffffff;
}

.graph-canvas-card {
  overflow: hidden;
}

.graph-stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  border-bottom: 1px solid #e2e8f0;
  padding: 10px 12px;
  font-size: 12px;
  color: #475569;
}

.graph-stat-row span {
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #f8fafc;
  padding: 4px 10px;
}

.graph-canvas {
  width: 100%;
  height: 620px;
  background: #ffffff;
}

.graph-empty {
  position: absolute;
  padding: 24px;
  font-size: 13px;
  color: #64748b;
}

.graph-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 14px;
  border-top: 1px solid #e2e8f0;
  padding: 10px;
  font-size: 12px;
  color: #334155;
}

.graph-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.graph-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
}

.graph-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.graph-detail-card {
  padding: 14px;
}

.graph-type-pill {
  display: inline-flex;
  border: 1px solid;
  border-radius: 999px;
  background: #f8fafc;
  padding: 3px 9px;
  font-size: 11px;
  font-weight: 700;
  color: #334155;
}

.graph-open {
  padding: 6px 10px;
}

.graph-metric {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
  padding: 8px;
}

.graph-neighbor {
  margin-top: 8px;
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  padding: 9px 10px;
  font-size: 12px;
  color: #334155;
}

.graph-neighbor:hover {
  border-color: #93c5fd;
  background: #eff6ff;
}

:deep(.graph-node-label) {
  paint-order: stroke;
  stroke: #ffffff;
  stroke-width: 4px;
  stroke-linejoin: round;
  fill: #0f172a;
  font-size: 11px;
  font-weight: 700;
  pointer-events: none;
}

@media (max-width: 1100px) {
  .graph-layout {
    grid-template-columns: 1fr;
  }
}
</style>
