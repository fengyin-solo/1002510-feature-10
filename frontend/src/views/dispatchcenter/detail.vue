<template>
  <section class="page" data-module="dispatchcenter-detail">
    <header class="page-head">
      <div>
        <h2>通道明细 · {{ entry?.['调度台编号'] ?? '调度台' }}</h2>
        <p class="page-desc">通道状态与调度台清单同源，结论保持一致；下方为完整流转链路与历史切换记录。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/dispatchcenter">返回调度台清单</RouterLink>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>
    <template v-if="entry">
      <div class="detail-grid">
        <article v-for="item in infoItems" :key="item.label" class="info-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="info-value">{{ item.value || '—' }}</strong>
        </article>
      </div>

      <h3 class="section-title">通道状态流转</h3>
      <ol class="flow-bar">
        <li
          v-for="(step, index) in flowSteps"
          :key="step.status"
          class="flow-step"
          :class="flowClass(step.status, index)"
        >
          <span class="flow-index">{{ index + 1 }}</span>
          <span class="flow-name">{{ step.status }}</span>
          <span v-if="step.action" class="flow-action">（{{ step.action }}）</span>
        </li>
      </ol>

      <div class="switch-panel">
        <div>
          <span class="stat-label">当前通道状态</span>
          <strong class="status-tag" :class="statusClass(entry.status)" style="margin-left: 8px">
            {{ entry['通道状态'] }}
          </strong>
          <span
            class="status-tag"
            :class="entry['调度台状态'] === '停用' ? 'tag-disabled' : 'tag-normal'"
            style="margin-left: 8px"
          >
            调度台{{ entry['调度台状态'] || '启用' }}
          </span>
        </div>
        <div class="switch-actions">
          <label class="operator-box">
            <span>当前操作人</span>
            <input v-model="operator" class="operator-input" placeholder="交接后请填写当班人" />
          </label>
          <button
            v-for="action in entry.allowedActions ?? []"
            :key="action"
            class="btn primary"
            type="button"
            :disabled="!!actionError"
            @click="runAction(action)"
          >
            {{ action }}
          </button>
          <span v-if="entry['调度台状态'] === '停用'" class="muted-text">该调度台已停用，不参与通道状态变更</span>
          <span v-else-if="!entry.allowedActions?.length" class="muted-text">当前无待执行动作</span>
        </div>
      </div>
      <p v-if="actionError" class="error-text">{{ actionError }}</p>
      <p v-if="actionMessage" class="ok-text">{{ actionMessage }}</p>

      <h3 class="section-title">切换记录（共 {{ history.length }} 条）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>序号</th>
            <th>动作</th>
            <th>变更前</th>
            <th>变更后</th>
            <th>操作人</th>
            <th>切换时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(record, index) in history" :key="`${record.switchedAt}-${index}`">
            <td>{{ index + 1 }}</td>
            <td>{{ record.action }}</td>
            <td>{{ record.from }}</td>
            <td><span class="status-tag" :class="statusClass(record.to)">{{ record.to }}</span></td>
            <td>{{ record.operator }}</td>
            <td>{{ record.switchedAt }}</td>
          </tr>
          <tr v-if="!history.length">
            <td colspan="6" class="empty-state">该调度台暂无通道切换记录</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'

type HistoryRecord = {
  action: string
  from: string
  to: string
  operator: string
  switchedAt: string
}
type Entry = Record<string, string | number | null> & {
  status: string
  allowedActions?: string[]
  history?: HistoryRecord[]
}

const route = useRoute()
const entryId = String(route.params.id)
const ENDPOINT = `/api/dispatchcenter/${entryId}`
const OPERATOR_KEY = 'dispatchcenter.operator'

// 流转闭环：正常 →（登记降级）通道降级 →（确认故障）设备故障
// →（切换备用）备用运行 →（处理故障）正常。
const flowSteps = [
  { status: '正常', action: '' },
  { status: '通道降级', action: '登记降级' },
  { status: '设备故障', action: '确认故障' },
  { status: '备用运行', action: '切换备用' },
  { status: '正常(恢复)', action: '处理故障' },
]
const FLOW_RANK: Record<string, number> = {
  正常: 0,
  通道降级: 1,
  设备故障: 2,
  备用运行: 3,
}

const entry = ref<Entry | null>(null)
const history = ref<HistoryRecord[]>([])
const errorMessage = ref('')
const actionError = ref('')
const actionMessage = ref('')
const operator = ref(localStorage.getItem(OPERATOR_KEY) || '')

const infoItems = computed(() => {
  const e = entry.value
  if (!e) return []
  return [
    { label: '调度台编号', value: e['调度台编号'] },
    { label: '管辖范围', value: e['管辖范围'] },
    { label: '显示设备', value: e['显示设备'] },
    { label: '操作终端', value: e['操作终端'] },
    { label: '通信链路', value: e['通信链路'] },
    { label: '链路优先级', value: String(e['优先级'] ?? '') },
    { label: '备用方式', value: e['备用方式'] },
    { label: '调度台状态', value: e['调度台状态'] },
    { label: '最后切换人', value: e.lastOperator },
    { label: '最后切换时间', value: e.lastSwitchedAt },
  ]
})

function statusClass(status: string | number | null | undefined): string {
  switch (status) {
    case '正常':
    case '正常(恢复)':
      return 'tag-normal'
    case '通道降级':
      return 'tag-warn'
    case '设备故障':
      return 'tag-danger'
    case '备用运行':
      return 'tag-info'
    default:
      return 'tag-normal'
  }
}

function flowClass(stepStatus: string, index: number): string {
  if (!entry.value) return ''
  // 末位的「正常(恢复)」与起始「正常」共用状态值，借助历史记录判断是否走过完整闭环。
  if (index === 4) {
    const recovered = history.value.some(
      (record) => record.action === '处理故障' && record.to === '正常',
    )
    return recovered ? 'flow-done' : ''
  }
  if (index === 0) {
    // 起点「正常」：从未流转过时高亮；处理完故障回到正常后由末位节点体现恢复。
    return entry.value.status === '正常' && !history.value.some((r) => r.action === '处理故障')
      ? 'flow-current'
      : 'flow-done'
  }
  const currentRank = FLOW_RANK[entry.value.status] ?? 0
  if (currentRank === index) return 'flow-current'
  return currentRank > index ? 'flow-done' : ''
}

async function runAction(action: string) {
  actionError.value = ''
  actionMessage.value = ''
  try {
    if (operator.value.trim()) {
      localStorage.setItem(OPERATOR_KEY, operator.value.trim())
    }
    const response = await request(`${ENDPOINT}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, operator: operator.value.trim() } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '通道状态未变更')
    }
    actionMessage.value = payload.message
    await reload()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '通道状态变更失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(ENDPOINT)
    if (!response.ok) {
      throw new Error(`通道明细读取失败（${response.status}）`)
    }
    const payload = (await response.json()) as Entry
    entry.value = payload
    history.value = payload.history ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '通道明细读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}
.info-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.info-value {
  display: block;
  margin-top: 4px;
  font-size: 14px;
}
.section-title {
  font-size: 15px;
  margin: 18px 0 8px;
}
.flow-bar {
  display: flex;
  gap: 0;
  padding: 0;
  margin: 0 0 14px;
  list-style: none;
}
.flow-step {
  flex: 1;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 8px;
  text-align: center;
  font-size: 13px;
  position: relative;
  margin-right: 18px;
}
.flow-step:last-child {
  margin-right: 0;
}
.flow-index {
  display: inline-block;
  width: 20px;
  height: 20px;
  line-height: 20px;
  border-radius: 50%;
  background: #e2e8f0;
  color: #475569;
  font-size: 12px;
  margin-right: 6px;
}
.flow-action {
  color: var(--muted);
  font-size: 12px;
}
.flow-done {
  border-color: #93c5fd;
  background: #eff6ff;
}
.flow-done .flow-index {
  background: #1f6feb;
  color: #fff;
}
.flow-current {
  border-color: #1f6feb;
  border-width: 2px;
  background: #dbeafe;
}
.flow-current .flow-index {
  background: #1f6feb;
  color: #fff;
}
.switch-panel {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 8px;
}
.switch-actions {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.operator-box span {
  display: block;
  font-size: 12px;
  color: var(--muted);
}
.operator-input {
  width: 140px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.muted-text {
  color: var(--muted);
  font-size: 13px;
}
.ok-text {
  color: #027a48;
}
</style>
