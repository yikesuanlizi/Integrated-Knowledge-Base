<script setup lang="ts">
import { ref, onMounted } from "vue";
import { listReviews, approveReview, rejectReview, getReviewStats } from "@/api/client";
import type { ReviewInfo, ReviewStats } from "@/types";
import AppIcon from "@/components/AppIcon.vue";

const reviews = ref<ReviewInfo[]>([]);
const stats = ref<ReviewStats | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);
const statusFilter = ref("review");

async function refresh(force = false) {
  loading.value = true;
  error.value = null;
  try {
    const r = await listReviews(statusFilter.value);
    reviews.value = r.reviews;
    stats.value = await getReviewStats(force);
  } catch (e) {
    error.value = (e as Error).message;
  } finally {
    loading.value = false;
  }
}

async function doApprove(review: ReviewInfo) {
  try {
    await approveReview(review.review_id, "", "");
    reviews.value = reviews.value.filter((x) => x.review_id !== review.review_id);
    if (stats.value) stats.value.pending_review = Math.max(0, stats.value.pending_review - 1);
    await refresh(true);
  } catch (e) {
    error.value = (e as Error).message;
  }
}

async function doReject(review: ReviewInfo) {
  try {
    await rejectReview(review.review_id, "", "");
    reviews.value = reviews.value.filter((x) => x.review_id !== review.review_id);
    if (stats.value) stats.value.pending_review = Math.max(0, stats.value.pending_review - 1);
    await refresh(true);
  } catch (e) {
    error.value = (e as Error).message;
  }
}

function statLabel(key: keyof ReviewStats) {
  const value = stats.value?.[key];
  return value === undefined || value === null ? "--" : value;
}

onMounted(refresh);
</script>

<template>
  <div class="mx-auto max-w-5xl">
    <div class="mb-4 flex items-center justify-between gap-4 flex-wrap">
      <div>
        <h2 class="text-lg font-semibold text-slate-800 flex items-center gap-2">
          <span class="text-lg">审核队列</span>
        </h2>
      </div>
      <div class="flex gap-2 items-center flex-shrink-0">
        <select
          v-model="statusFilter"
          class="text-sm border border-slate-200 rounded-md px-3 py-1 bg-white focus:outline-none focus:border-blue-500"
          @change="refresh(true)"
        >
          <option value="review">待审核</option>
          <option value="approved">已通过</option>
          <option value="rejected">已驳回</option>
        </select>
        <button @click="refresh(true)" class="rounded-md bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-3 py-1 transition-colors">刷新</button>
      </div>
    </div>

    <!-- 统计 -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
      <div class="rounded-lg border border-slate-200 bg-white p-4">
            <div class="text-xs font-medium text-slate-600 mb-1">总记录</div>
            <div class="text-xl font-semibold text-slate-800">{{ statLabel("total") }}</div>
          </div>
          <div class="rounded-lg border border-amber-200 bg-amber-50 p-4">
            <div class="text-xs font-medium text-amber-700 mb-1">待审核</div>
            <div class="text-xl font-semibold text-amber-700">{{ statLabel("pending_review") }}</div>
          </div>
          <div class="rounded-lg border border-blue-200 bg-blue-50 p-4">
            <div class="text-xs font-medium text-blue-700 mb-1">已通过</div>
            <div class="text-xl font-semibold text-blue-700">{{ statLabel("approved") }}</div>
          </div>
          <div class="rounded-lg border border-red-200 bg-red-50 p-4">
            <div class="text-xs font-medium text-red-700 mb-1">已驳回</div>
            <div class="text-xl font-semibold text-red-700">{{ statLabel("rejected") }}</div>
          </div>
    </div>

    <div v-if="error" class="mb-5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm font-medium text-red-700">{{ error }}</div>
    <div v-if="loading" class="py-20 text-center text-slate-500">加载中...</div>

    <div v-if="!loading && reviews.length === 0" class="py-20 text-center rounded-lg border border-slate-200 bg-white">
      <AppIcon name="check" class="h-10 w-10 mx-auto text-slate-300" />
      <div class="text-sm font-semibold text-slate-800 mb-1">审核队列为空</div>
      <div class="text-xs text-slate-600">当前没有需要审核的卡片。</div>
    </div>

    <div v-if="!loading && reviews.length > 0" class="space-y-3">
      <div
        v-for="r in reviews"
        :key="r.review_id"
        class="rounded-lg border border-slate-200 bg-white p-4"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-3 mb-2 flex-wrap">
              <span class="text-sm font-semibold text-slate-800">{{ r.card_id }}</span>
              <span class="text-[11px] text-slate-700 bg-slate-100 px-2 py-0.5 rounded font-mono">{{ r.review_id }}</span>
              <span v-if="r.status === 'approved'" class="text-[11px] text-blue-800 bg-blue-100 px-2 py-0.5 rounded font-medium">已通过</span>
              <span v-if="r.status === 'rejected'" class="text-[11px] text-red-800 bg-red-100 px-2 py-0.5 rounded font-medium">已驳回</span>
              <span v-if="r.status === 'review'" class="text-[11px] text-amber-800 bg-amber-100 px-2 py-0.5 rounded font-medium">待审核</span>
            </div>
            <div v-if="r.notes" class="text-xs text-slate-600 mb-1">备注: {{ r.notes }}</div>
            <div class="text-[11px] text-slate-500 mt-1">{{ r.created_at }}</div>
          </div>
          <div class="flex gap-2 shrink-0">
            <button
              @click="doApprove(r)"
              class="rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium px-2.5 py-1 transition-colors"
            >
              通过
            </button>
            <button
              @click="doReject(r)"
              class="rounded-md bg-red-500 hover:bg-red-600 text-white text-xs font-medium px-2.5 py-1 transition-colors"
            >
              驳回
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
