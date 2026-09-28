<template>
  <section class="page" data-module="dispatchcenter">
    <header class="page-head">
      <div>
        <h2>调度中心管理</h2>
        <p class="page-desc">
          通道按「正常 → 通道降级 → 设备故障 → 备用运行 → 正常」闭环流转；同管辖范围链路同时故障时按优先级处置，不可越级标回正常。
        </p>
      </div>
      <div class="page-actions">
        <label class="operator-box">
          <span>当前操作人</span>
          <input v-model="operator" class="operator-input" placeholder="交接后请填写当班人" />
        </label>
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
        <span>调度台编号/管辖范围</span>
        <input v-model="keyword" placeholder="按编号或管辖范围检索" />
      </label>
      <label class="filter-item">
        <span>通道状态</span>
        <select v-model="statusFilter">
          <option value="">全部</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
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
          <td>
            <RouterLink class="link" :to="`/dispatchcenter/${row.id}`">{{ row['调度台编号'] }}</RouterLink>
          </td>
          <td>{{ row['管辖范围'] ?? '—' }}</td>
          <td>{{ row['显示设备'] ?? '—' }}</td>
          <td>{{ row['操作终端'] || '—' }}</td>
          <td>{{ row['通信链路'] || '—' }}</td>
          <td>{{ row['优先级'] ?? '—' }}</td>
          <td><span class="status-tag" :class="statusClass(row.status)">{{ row['通道状态'] ?? row.status }}</span></td>
          <td>{{ row['备用方式'] || '—' }}</td>
          <td>
            <span class="status-tag" :class="row['调度台状态'] === '停用' ? 'tag-disabled' : 'tag-normal'">
              {{ row['调度台状态'] || '启用' }}
            </span>
          </td>
          <td>{{ row.lastOperator || '—' }}</td>
          <td>{{ row.lastSwitchedAt || '—' }}</td>
          <td class="row-actions">
            <template v-if="row.allowedActions && row.allowedActions.length">
              <button
                v-for="action in row.allowedActions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else-if="row['调度台状态'] === '停用'" class="muted-text">已停用</span>
            <span v-else class="muted-text">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无调度中心数据，可先登记调度台</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条调度中心记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="showCreate" class="modal-mask" @click.self="showCreate = false">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记调度台</h3>
        <label v-for="field in createFields" :key="field.key" class="filter-item modal-field">
          <span>{{ field.label }}{{ field.required ? ' *' : '' }}</span>
          <input
            v-if="field.key !== '优先级'"
            v-model="createForm[field.key]"
            :placeholder="`请输入${field.label}`"
          />
          <input v-else v-model.number="createForm[field.key]" type="number" min="1" placeholder="数字越小优先级越高" />
        </label>
        <p v-if="createError" class="error-text">{{ createError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" type="submit">确认登记</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null> & { allowedActions?: string[] }

const ENDPOINT = '/api/dispatchcenter'
const columns = [
  '调度台编号',
  '管辖范围',
  '显示设备',
  '操作终端',
  '通信链路',
  '优先级',
  '通道状态',
  '备用方式',
  '调度台状态',
  '最后切换人',
  '最后切换时间',
]
const statuses = ['正常', '通道降级', '设备故障', '备用运行']
const OPERATOR_KEY = 'dispatchcenter.operator'

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
// 交接后谁当班就填谁，保存在本机，重新进入页面仍是上一次的操作人。
const operator = ref(localStorage.getItem(OPERATOR_KEY) || '')

const stats = computed(() => [
  { label: '正常调度台', value: rows.value.filter((r) => r.status === '正常').length },
  { label: '通道降级', value: rows.value.filter((r) => r.status === '通道降级').length },
  { label: '设备故障', value: rows.value.filter((r) => r.status === '设备故障').length },
  { label: '备用运行', value: rows.value.filter((r) => r.status === '备用运行').length },
  { label: '已停用', value: rows.value.filter((r) => r['调度台状态'] === '停用').length },
])

function statusClass(status: string | number | null | undefined): string {
  switch (status) {
    case '正常':
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

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

// ---- 登记调度台 ----
const createFields: { key: string; label: string; required: boolean }[] = [
  { key: '调度台编号', label: '调度台编号', required: true },
  { key: '管辖范围', label: '管辖范围', required: true },
  { key: '显示设备', label: '显示设备', required: true },
  { key: '操作终端', label: '操作终端', required: false },
  { key: '通信链路', label: '通信链路', required: false },
  { key: '优先级', label: '链路优先级', required: false },
  { key: '备用方式', label: '备用方式', required: false },
]
const showCreate = ref(false)
const createError = ref('')
const createForm = reactive<Record<string, string | number>>({
  调度台编号: '',
  管辖范围: '',
  显示设备: '',
  操作终端: '',
  通信链路: '',
  优先级: 99,
  备用方式: '',
})

function openCreate() {
  createError.value = ''
  showCreate.value = true
}

async function submitCreate() {
  createError.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '调度台登记失败')
    }
    showCreate.value = false
    await reload()
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '调度台登记失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    if (operator.value.trim()) {
      localStorage.setItem(OPERATOR_KEY, operator.value.trim())
    }
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, operator: operator.value.trim() } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 越级、优先级拦截、缺操作终端/备用方式等原因由后端给出，直接展示。
      throw new Error(payload.message || '调度中心动作未生效')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度中心操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('调度台列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '调度台列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions {
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
  width: 150px;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.muted-text {
  color: var(--muted);
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal {
  width: 460px;
  background: #fff;
  border-radius: 8px;
  padding: 18px 20px;
}
.modal-field {
  margin-bottom: 10px;
  width: 100%;
}
.modal-field input {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}
</style>
