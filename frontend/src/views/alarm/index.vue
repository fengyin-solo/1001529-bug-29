<template>
  <section class="page" data-module="alarm">
    <header class="page-head">
      <div>
        <h2>告警监测管理</h2>
        <p class="page-desc">维护告警记录，围绕告警编号、告警来源、告警类型、触发阈值做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记告警记录</button>
        <button class="btn" type="button" @click="exportRows">导出告警监测清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>告警状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
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
          <td v-for="column in columns" :key="column">
            <span v-if="column === '触发阈值' && row['阈值缺失']" class="tag-warn">未填阈值</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <template v-if="!isTerminal(row)">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="muted-text">已收尾</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无告警监测数据，可先登记告警记录</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条告警监测记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/alarm'
const columns = ["告警编号", "告警来源", "告警类型", "触发阈值", "触发时刻", "处置人员", "关闭时刻", "告警状态"]
const actions = ["确认告警", "关闭告警", "忽略告警"]
const statuses = ["待确认", "处置中", "已关闭", "已忽略"]
const terminalStatuses = ["已关闭", "已忽略"]
const stats = [{"label": "待确认告警", "value": 0}, {"label": "处置中告警", "value": 0}, {"label": "今日告警数", "value": 0}]
// 筛选输入框与后端查询参数的对应关系，列表与导出共用同一套口径
const filterParamMap: Record<string, string> = { "告警编号": "keyword", "告警来源": "source", "告警类型": "alarm_type" }

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const filterFields = columns.slice(0, 3)

function isTerminal(row: Row) {
  return terminalStatuses.includes(String(row['告警状态'] ?? ''))
}

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const [field, param] of Object.entries(filterParamMap)) {
    const value = (filters.value[field] ?? '').trim()
    if (value) {
      params.set(param, value)
    }
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  return params.toString()
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  const query = buildQuery()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '告警记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  const values: Record<string, string> = { action }
  if (action === '忽略告警') {
    const reason = window.prompt('请填写忽略理由，会随告警清单一并导出')?.trim()
    if (!reason) {
      errorMessage.value = '忽略告警必须填写忽略理由'
      return
    }
    values['忽略理由'] = reason
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? payload?.detail ?? '告警监测动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '告警监测操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = buildQuery()
  try {
    const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error('告警记录列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '告警监测列表读取失败'
  }
}

onMounted(reload)
</script>
