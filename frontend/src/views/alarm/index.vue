<template>
  <section class="page" data-module="alarm">
    <header class="page-head">
      <div>
        <h2>告警监测管理</h2>
        <p class="page-desc">维护告警记录，围绕告警编号、告警来源、告警类型、触发阈值做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记告警记录</button>
        <button class="btn" type="button" :disabled="exporting" @click="exportRows">
          {{ exporting ? '正在导出…' : '导出告警监测清单' }}
        </button>
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
        <span>告警编号</span>
        <input v-model="filters.keyword" placeholder="按告警编号检索" />
      </label>
      <label class="filter-item">
        <span>告警状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
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
            <template v-if="column === '触发阈值'">
              <span v-if="isThresholdMissing(row)" class="tag tag-warning">未配置</span>
              <template v-else>{{ displayText(row[column]) }}</template>
            </template>
            <template v-else-if="column === '告警状态'">
              <span :class="['tag', statusTagClass(row.status)]">{{ displayText(row.status) }}</span>
            </template>
            <template v-else>{{ displayText(row[column]) }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!canRunAction(action, row) || busyId === Number(row.id)"
              :title="actionTip(action, row)"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
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
const columns = ["告警编号", "告警来源", "告警类型", "触发阈值", "触发时刻", "处置人员", "关闭时刻", "告警状态", "忽略理由"]
const actions = ["确认告警", "关闭告警", "忽略告警"]
const statuses = ["待确认", "处置中", "已关闭", "已忽略"]
// 与后端状态流转规则保持一致：终态记录不再展示可用动作，避免来回改状态。
const allowedActions: Record<string, string[]> = {
  "待确认": ["确认告警", "关闭告警", "忽略告警"],
  "处置中": ["关闭告警", "忽略告警"],
  "已关闭": [],
  "已忽略": [],
}
const stats = [{"label": "待确认告警", "value": 0}, {"label": "处置中告警", "value": 0}, {"label": "今日告警数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const exporting = ref(false)
const busyId = ref<number | null>(null)
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })

function displayText(value: unknown): string {
  if (value === null || value === undefined || String(value).trim() === '') {
    return '—'
  }
  return String(value)
}

function isThresholdMissing(row: Row): boolean {
  return displayText(row['触发阈值']) === '—'
}

function statusTagClass(status: unknown): string {
  if (status === '已忽略') return 'tag-muted'
  if (status === '已关闭') return 'tag-success'
  return 'tag-warning'
}

function canRunAction(action: string, row: Row): boolean {
  return allowedActions[String(row.status)]?.includes(action) ?? false
}

function actionTip(action: string, row: Row): string {
  return canRunAction(action, row) ? action : `当前为「${displayText(row.status)}」，不能${action}`
}

function buildQuery(): string {
  const params = new URLSearchParams()
  if (filters.value.keyword.trim()) params.set('keyword', filters.value.keyword.trim())
  if (filters.value.status) params.set('status', filters.value.status)
  return params.toString()
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

async function exportRows() {
  if (exporting.value) return
  exporting.value = true
  errorMessage.value = ''
  try {
    // 带上与列表完全一致的查询条件，导出条数与页脚总数保持一致。
    const response = await request(`${ENDPOINT}/export?${buildQuery()}`)
    if (!response.ok) {
      throw new Error('告警清单导出失败，请稍后重试')
    }
    const blob = await response.blob()
    const disposition = response.headers.get('Content-Disposition') ?? ''
    const match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
    const filename = match ? decodeURIComponent(match[1]) : '告警监测清单.csv'
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '告警清单导出失败'
  } finally {
    exporting.value = false
  }
}

function openCreate() {
  errorMessage.value = '告警记录登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  if (!canRunAction(action, row) || busyId.value !== null) return
  let remark: string | undefined
  if (action === '忽略告警') {
    // 忽略必须留痕：理由会随动作落库，并出现在列表与导出文件里。
    remark = window.prompt('请填写忽略理由（必填）')?.trim()
    if (!remark) {
      if (remark === undefined) return
      errorMessage.value = '忽略告警必须填写忽略理由'
      return
    }
  }
  busyId.value = Number(row.id)
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action }, remark }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '告警监测动作未生效，请稍后重试')
    }
    // 刷新沿用当前筛选条件，后端状态已落库，刷新后状态停住不会回跳。
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '告警监测操作失败'
  } finally {
    busyId.value = null
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}?${buildQuery()}`)
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
