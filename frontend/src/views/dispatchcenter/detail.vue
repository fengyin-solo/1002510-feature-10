<template>
  <section class="page" data-module="dispatchcenter-detail">
    <header class="page-head">
      <div>
        <h2>通道明细：{{ entry?.调度台编号 ?? `#${route.params.id}` }}</h2>
        <p class="page-desc">通道状态与清单页一致，切换记录完整保留，交接后可直接核对上一次切换。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/dispatchcenter">返回调度台清单</RouterLink>
      </div>
    </header>

    <template v-if="entry">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">通道状态</span>
          <strong class="stat-value">{{ entry['通道状态'] }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">调度台状态</span>
          <strong class="stat-value">{{ entry['调度台状态'] }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">最近操作人</span>
          <strong class="stat-value">{{ entry['最近操作人'] || '—' }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">最近切换时间</span>
          <strong class="stat-value stat-time">{{ entry['最近切换时间'] || '—' }}</strong>
        </article>
      </div>

      <table class="data-table detail-table">
        <tbody>
          <tr v-for="field in detailFields" :key="field">
            <th>{{ field }}</th>
            <td>{{ entry[field] || '—' }}</td>
          </tr>
        </tbody>
      </table>

      <div class="action-bar">
        <template v-if="entry['调度台状态'] === '已停用'">
          <span class="muted-text">该调度台已停用，不再参与通道状态变更</span>
        </template>
        <template v-else>
          <label class="filter-item">
            <span>操作人</span>
            <input v-model="operator" placeholder="执行切换的值班人员" />
          </label>
          <button
            v-for="action in availableActions"
            :key="action"
            class="btn primary"
            type="button"
            @click="runAction(action)"
          >
            {{ action }}
          </button>
          <span v-if="!availableActions.length" class="muted-text">当前状态无可执行动作</span>
        </template>
      </div>

      <h3 class="section-title">切换记录</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>动作</th>
            <th>原状态</th>
            <th>目标状态</th>
            <th>操作人</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(record, index) in switchHistory" :key="index">
            <td>{{ record['时间'] }}</td>
            <td>{{ record['动作'] }}</td>
            <td>{{ record['原状态'] }}</td>
            <td>{{ record['目标状态'] }}</td>
            <td>{{ record['操作人'] }}</td>
          </tr>
          <tr v-if="!switchHistory.length">
            <td colspan="5" class="empty-state">暂无切换记录</td>
          </tr>
        </tbody>
      </table>
    </template>

    <footer class="page-foot">
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type Entry = Record<string, any>

const ENDPOINT = '/api/dispatchcenter'
const detailFields = ["调度台编号", "管辖范围", "优先级", "显示设备", "操作终端", "通信链路", "备用方式"]
const NEXT_ACTIONS: Record<string, string[]> = {
  正常: ["登记降级"],
  通道降级: ["登记故障"],
  设备故障: ["切换备用"],
  备用运行: ["处理故障"],
}

const route = useRoute()
const entry = ref<Entry | null>(null)
const operator = ref('')
const errorMessage = ref('')
const infoMessage = ref('')

const availableActions = computed(() => NEXT_ACTIONS[String(entry.value?.['通道状态'] ?? '')] ?? [])
const switchHistory = computed<Entry[]>(() => entry.value?.['切换记录'] ?? [])

async function runAction(action: string) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action, operator: operator.value }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || payload.detail || '调度中心动作未生效')
    }
    infoMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度中心操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}`)
    const payload = await response.json()
    if (!response.ok) {
      throw new Error(payload.detail || '调度台明细读取失败')
    }
    entry.value = payload
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度台明细读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.detail-table {
  margin-bottom: 12px;
}
.detail-table th {
  width: 140px;
  background: #f8fafc;
}
.action-bar {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  margin-bottom: 16px;
}
.section-title {
  font-size: 14px;
  margin: 0 0 8px;
}
.stat-time {
  font-size: 15px;
}
.muted-text {
  color: var(--muted);
  font-size: 13px;
}
.info-text {
  color: #067647;
}
</style>
