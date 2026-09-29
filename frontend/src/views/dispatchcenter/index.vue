<template>
  <section class="page" data-module="dispatchcenter">
    <header class="page-head">
      <div>
        <h2>调度中心管理</h2>
        <p class="page-desc">维护调度台，通道状态按 正常 → 通道降级 → 设备故障 → 备用运行 → 正常 逐级流转，每次切换留痕。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记调度台</button>
        <button class="btn" type="button" @click="exportRows">导出调度中心清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>调度台编号</span>
        <input v-model="filters.keyword" placeholder="按调度台编号检索" />
      </label>
      <label class="filter-item">
        <span>通道状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>操作人</span>
        <input v-model="operator" placeholder="执行切换的值班人员" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <RouterLink v-if="column === '调度台编号'" :to="`/dispatchcenter/${row.id}`">
              {{ row[column] || '—' }}
            </RouterLink>
            <template v-else>{{ row[column] || '—' }}</template>
          </td>
          <td class="row-actions">
            <template v-if="row['调度台状态'] === '已停用'">
              <span class="muted-text">已停用</span>
            </template>
            <template v-else>
              <button
                v-for="action in availableActions(row)"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <RouterLink class="link" :to="`/dispatchcenter/${row.id}`">明细</RouterLink>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无调度中心数据，可先登记调度台</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条调度中心记录</span>
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/dispatchcenter'
const columns = ["调度台编号", "管辖范围", "优先级", "显示设备", "操作终端", "通信链路", "通道状态", "备用方式", "调度台状态", "最近操作人", "最近切换时间"]
const statuses = ["正常", "通道降级", "设备故障", "备用运行"]
// 每个状态只暴露下一步动作，与后端状态机保持一致，避免越级操作。
const NEXT_ACTIONS: Record<string, string[]> = {
  正常: ["登记降级"],
  通道降级: ["登记故障"],
  设备故障: ["切换备用"],
  备用运行: ["处理故障"],
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const infoMessage = ref('')
const operator = ref('')
const filters = ref<Record<string, string>>({ keyword: '', status: '' })

const stats = computed(() => [
  { label: '正常调度台', value: countByStatus('正常') },
  { label: '降级调度台', value: countByStatus('通道降级') },
  { label: '故障调度台', value: countByStatus('设备故障') },
  { label: '备用运行', value: countByStatus('备用运行') },
])

function countByStatus(status: string) {
  return rows.value.filter((row) => row['通道状态'] === status).length
}

function availableActions(row: Row) {
  return NEXT_ACTIONS[String(row['通道状态'] ?? '')] ?? []
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '调度台登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
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
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('调度台列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度中心列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.muted-text {
  color: var(--muted);
  font-size: 12px;
}
.info-text {
  color: #067647;
}
select {
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 6px;
}
</style>
