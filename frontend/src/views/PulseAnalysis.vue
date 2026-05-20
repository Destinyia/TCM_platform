<template>
  <div class="pulse-analysis">
    <el-card shadow="never" class="filter-card">
      <template #header>
        <div class="panel-header">
          <span>{{ ui.title }}</span>
          <el-tag type="success">{{ ui.dataDriven }}</el-tag>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :xs="24" :md="6">
          <el-select v-model="filters.userId" :placeholder="ui.selectUser" class="full-width" :loading="loading" filterable>
            <el-option
              v-for="user in users"
              :key="user.user_id"
              :label="`${user.display_id} ${user.name}`"
              :value="user.user_id"
            />
          </el-select>
        </el-col>
        <el-col :xs="24" :md="5">
          <el-select v-model="filters.slot" :placeholder="ui.slot" class="full-width">
            <el-option v-for="slot in slotOptions" :key="slot.value" :label="slot.label" :value="slot.value" />
          </el-select>
        </el-col>
        <el-col :xs="24" :md="5">
          <el-select v-model="filters.source" :placeholder="ui.source" class="full-width">
            <el-option :label="ui.allSources" value="all" />
            <el-option :label="ui.zhongke" value="zhongke" />
            <el-option :label="ui.yushengtang" value="yushengtang" />
          </el-select>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-checkbox v-model="filters.includeSuspicious">{{ ui.includeSuspicious }}</el-checkbox>
        </el-col>
      </el-row>
    </el-card>

    <el-row :gutter="16" class="stats-row">
      <el-col v-for="card in metricCards" :key="card.label" :xs="24" :sm="12" :lg="6">
        <el-card shadow="never" class="metric-card">
          <div class="metric-value">{{ card.value }}</div>
          <div class="metric-label">{{ card.label }}</div>
          <div class="metric-note">{{ card.note }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="14">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>{{ selectedUser?.name || '-' }} {{ ui.longitudinalTrend }}</span>
              <el-tag size="small">{{ ui.standardizedFeatures }}</el-tag>
            </div>
          </template>
          <div ref="trendChartRef" class="chart large-chart"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="10">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>{{ ui.slotChange }}</span>
              <el-tag size="small" type="warning">{{ ui.slotDrift }}</el-tag>
            </div>
          </template>
          <div ref="slotChartRef" class="chart large-chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="section-row">
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>{{ ui.sameSlotStability }}</span>
              <el-tag size="small">{{ slotName(filters.slot) }} | {{ selectedUser?.name || '-' }}</el-tag>
            </div>
          </template>
          <div ref="stabilityChartRef" class="chart"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>{{ ui.crossUserDifference }}</span>
              <el-tag size="small" type="success">{{ ui.crossUser }}</el-tag>
            </div>
          </template>
          <div ref="crossUserChartRef" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="panel-card section-row">
      <template #header>
        <div class="panel-header">
          <span>{{ ui.selectedRecordDetail }}</span>
          <span class="table-note">{{ selectedRecordTitle }}</span>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col :xs="24" :lg="10">
          <el-descriptions v-if="selectedRecord" :column="1" size="small" border>
            <el-descriptions-item :label="ui.user">{{ selectedRecord.user_name || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="ui.visitTime">{{ selectedRecord.visit_date || '-' }} {{ selectedRecord.visit_time || '' }}</el-descriptions-item>
            <el-descriptions-item :label="ui.source">{{ sourceName(selectedRecord.source_vendor) }}</el-descriptions-item>
            <el-descriptions-item :label="ui.side">{{ selectedRecord.side || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="ui.pulseType">{{ selectedRecord.pulse_type || '-' }}</el-descriptions-item>
            <el-descriptions-item :label="ui.stabilityScore">{{ formatNumber(selectedRecord.stability_score, 1) }}</el-descriptions-item>
          </el-descriptions>
          <el-empty v-else :description="ui.noSelectedRecord" :image-size="72" />
        </el-col>
        <el-col :xs="24" :lg="14">
          <div ref="waveformChartRef" class="chart"></div>
        </el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="panel-card section-row">
      <template #header>
        <div class="panel-header">
          <span>{{ ui.recordTable }}</span>
          <span class="table-note">{{ ui.currentFiltered }} {{ filteredRecords.length }} {{ ui.rowsUnit }} / {{ ui.analysisIncluded }} {{ analysisRecords.length }} {{ ui.rowsUnit }}</span>
        </div>
      </template>
      <el-table
        v-loading="loading"
        :data="filteredRecords"
        size="small"
        height="460"
        row-key="row_key"
        highlight-current-row
        @row-click="selectRecord"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expanded-record">
              <div class="expanded-title">{{ ui.parsedDetail }}</div>
              <div class="detail-grid">
                <div v-for="item in detailItems(row)" :key="item.key" class="detail-item">
                  <span class="detail-key">{{ item.key }}</span>
                  <span class="detail-value">{{ item.value }}</span>
                </div>
              </div>
              <el-table v-if="row.measurements?.length" :data="row.measurements" size="small" class="measurement-table">
                <el-table-column v-for="column in measurementColumns" :key="column.key" :prop="column.key" :label="column.label" min-width="92" />
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="visit_date" :label="ui.date" width="112" />
        <el-table-column prop="visit_time" :label="ui.time" width="78" />
        <el-table-column prop="user_name" :label="ui.user" width="90" />
        <el-table-column prop="slot" :label="ui.slot" width="64">
          <template #default="{ row }">{{ slotName(row.slot) }}</template>
        </el-table-column>
        <el-table-column prop="source_vendor" :label="ui.source" width="94">
          <template #default="{ row }">
            <el-tag size="small" :type="row.source_vendor === 'zhongke' ? 'primary' : 'success'">
              {{ sourceName(row.source_vendor) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="side" :label="ui.side" width="70" />
        <el-table-column prop="pulse_type" :label="ui.pulseType" min-width="110" show-overflow-tooltip />
        <el-table-column prop="pulse_rate" :label="ui.pulseRate" width="84" />
        <el-table-column prop="force" :label="ui.force" width="84" />
        <el-table-column prop="tension" :label="ui.tension" width="84" />
        <el-table-column prop="fluency" :label="ui.fluency" width="84" />
        <el-table-column prop="amplitude" :label="ui.amplitude" width="88" />
        <el-table-column prop="stability_score" :label="ui.stability" width="92" />
        <el-table-column prop="quality_status" :label="ui.quality" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="qualityType(row.quality_status)">
              {{ qualityName(row.quality_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="ui.actions" width="112" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click.stop="openVisit(row.visit_id)">
              {{ ui.visitDetail }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <VisitDetailDrawer v-model="visitDrawerVisible" :visit-id="activeVisitId" />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { api } from '../services/api'
import VisitDetailDrawer from '../components/VisitDetailDrawer.vue'

const ui = {
  title: '\u8109\u8bca\u5206\u6790\u5de5\u4f5c\u53f0',
  dataDriven: '\u7ed3\u6784\u5316\u6570\u636e\u9a71\u52a8',
  selectUser: '\u9009\u62e9\u7528\u6237',
  slot: '\u65f6\u6bb5',
  source: '\u6765\u6e90',
  allSources: '\u5168\u90e8\u6765\u6e90',
  zhongke: '\u4e2d\u79d1',
  yushengtang: '\u7389\u751f\u5802',
  includeSuspicious: '\u7eb3\u5165\u7591\u4f3c\u5f02\u5e38\u8bb0\u5f55\u505a\u654f\u611f\u6027\u89c2\u5bdf',
  longitudinalTrend: '\u7eb5\u5411\u8109\u8bca\u8d8b\u52bf',
  standardizedFeatures: '\u6807\u51c6\u5316\u7279\u5f81',
  slotChange: '\u4e0d\u540c\u65f6\u6bb5\u7279\u5f81\u53d8\u5316',
  slotDrift: 'slot drift',
  sameSlotStability: '\u540c\u4e00\u7528\u6237\u540c\u4e00\u65f6\u6bb5\u7a33\u5b9a\u6027',
  crossUserDifference: '\u4e0d\u540c\u7528\u6237\u7279\u5f81\u5dee\u5f02',
  crossUser: 'cross user',
  selectedRecordDetail: '\u5f53\u524d\u8109\u8bca\u8bb0\u5f55',
  noSelectedRecord: '\u5c1a\u672a\u9009\u62e9\u8109\u8bca\u8bb0\u5f55',
  recordTable: '\u8109\u8bca\u8bb0\u5f55\u660e\u7ec6',
  currentFiltered: '\u5f53\u524d\u7b5b\u9009',
  analysisIncluded: '\u7eb3\u5165\u5206\u6790',
  rowsUnit: '\u6761',
  parsedDetail: '\u89e3\u6790\u5b57\u6bb5',
  user: '\u7528\u6237',
  visitTime: '\u91c7\u96c6\u65f6\u95f4',
  side: '\u4fa7\u522b',
  pulseType: '\u8109\u8c61',
  stabilityScore: '\u7a33\u5b9a\u6027\u5f97\u5206',
  date: '\u65e5\u671f',
  time: '\u65f6\u95f4',
  pulseRate: '\u8109\u7387',
  force: '\u8109\u529b',
  tension: '\u7d27\u5f20\u5ea6',
  fluency: '\u6d41\u5229\u5ea6',
  amplitude: '\u5e45\u503c',
  stability: '\u7a33\u5b9a\u6027',
  quality: '\u8d28\u91cf',
  actions: '\u64cd\u4f5c',
  visitDetail: '\u67e5\u770b visit',
  waveform: '\u8109\u6ce2',
  measurements: '\u516d\u90e8\u6d4b\u91cf',
  averagePulseRate: '\u5e73\u5747\u8109\u7387',
  averageForce: '\u5e73\u5747\u8109\u529b',
  averageStability: '\u540c\u65f6\u6bb5\u7a33\u5b9a\u6027',
  excludedImpact: '\u7591\u4f3c\u5f02\u5e38\u5f71\u54cd',
  currentUserRecords: '\u5f53\u524d\u7528\u6237\u8bb0\u5f55',
  featureIndex: '\u7279\u5f81\u6307\u6570',
  defaultExcluded: '\u9ed8\u8ba4\u6392\u9664\u5206\u6790',
  includedNow: '\u5df2\u7eb3\u5165\u654f\u611f\u6027\u89c2\u5bdf',
  valid: '\u6709\u6548',
  incomplete: '\u4e0d\u5b8c\u6574',
  suspicious: '\u7591\u4f3c\u5f02\u5e38'
}

const slotOptions = [
  { label: '\u65e9', value: '\u65e9' },
  { label: '\u4e2d', value: '\u4e2d' },
  { label: '\u665a', value: '\u665a' }
]

const measurementColumns = [
  { key: 'type', label: '\u90e8\u4f4d' },
  { key: 'pulse_rate_value', label: '\u8109\u7387\u503c' },
  { key: 'force_value', label: '\u8109\u529b\u503c' },
  { key: 'tension_value', label: '\u7d27\u5f20\u503c' },
  { key: 'fluency_value', label: '\u6d41\u5229\u503c' },
  { key: 'h1', label: 'h1' },
  { key: 'w_t', label: 'W/t' }
]

const filters = ref({
  userId: '',
  slot: '\u65e9',
  source: 'all',
  includeSuspicious: false
})
const users = ref([])
const pulseRecords = ref([])
const loading = ref(false)
const selectedRecord = ref(null)
const visitDrawerVisible = ref(false)
const activeVisitId = ref('')

const trendChartRef = ref(null)
const slotChartRef = ref(null)
const stabilityChartRef = ref(null)
const crossUserChartRef = ref(null)
const waveformChartRef = ref(null)
let trendChart
let slotChart
let stabilityChart
let crossUserChart
let waveformChart

const selectedUser = computed(() => users.value.find((user) => user.user_id === filters.value.userId))

const normalizedRecords = computed(() => {
  return pulseRecords.value.map((record, index) => ({
    ...record,
    row_key: `${record.visit_id || 'visit'}-${record.source_asset_id || index}`,
    pulse_rate: toNumber(record.pulse_rate),
    force: toNumber(record.force),
    tension: toNumber(record.tension),
    fluency: toNumber(record.fluency),
    amplitude: toNumber(record.amplitude),
    stability_score: toNumber(record.stability_score)
  }))
})

const filteredRecords = computed(() => {
  return normalizedRecords.value.filter((record) => {
    const sourceMatched = filters.value.source === 'all' || record.source_vendor === filters.value.source
    const qualityMatched = filters.value.includeSuspicious || record.included
    return sourceMatched && qualityMatched
  })
})

const analysisRecords = computed(() => filteredRecords.value.filter((record) => record.included || filters.value.includeSuspicious))

const selectedUserRecords = computed(() => {
  return analysisRecords.value
    .filter((record) => record.user_id === filters.value.userId)
    .sort((a, b) => `${a.visit_date || ''} ${a.visit_time || ''}`.localeCompare(`${b.visit_date || ''} ${b.visit_time || ''}`))
})

const sameSlotRecords = computed(() => {
  return selectedUserRecords.value.filter((record) => record.slot === filters.value.slot)
})

const metricCards = computed(() => {
  const records = selectedUserRecords.value
  const slotRecords = sameSlotRecords.value
  const excludedCount = pulseRecords.value.filter((record) => !record.included).length
  return [
    {
      label: ui.averagePulseRate,
      value: `${formatNumber(average(records, 'pulse_rate'), 0)} bpm`,
      note: `${selectedUser.value?.name || ''} ${ui.currentUserRecords}`
    },
    {
      label: ui.averageForce,
      value: formatNumber(average(records, 'force'), 1),
      note: ui.featureIndex
    },
    {
      label: ui.averageStability,
      value: formatNumber(average(slotRecords, 'stability_score'), 1),
      note: `${slotName(filters.value.slot)} ${slotRecords.length} ${ui.rowsUnit}`
    },
    {
      label: ui.excludedImpact,
      value: `${excludedCount} ${ui.rowsUnit}`,
      note: filters.value.includeSuspicious ? ui.includedNow : ui.defaultExcluded
    }
  ]
})

const selectedRecordTitle = computed(() => {
  if (!selectedRecord.value) return '-'
  return `${selectedRecord.value.user_name || '-'} / ${selectedRecord.value.visit_date || '-'} ${selectedRecord.value.visit_time || ''} / ${sourceName(selectedRecord.value.source_vendor)}`
})

function toNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function average(records, key) {
  const values = records.map((record) => Number(record[key])).filter((value) => Number.isFinite(value))
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function formatNumber(value, digits = 1) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(digits) : '-'
}

function sourceName(value) {
  return { zhongke: ui.zhongke, yushengtang: ui.yushengtang }[value] || value || '-'
}

function slotName(value) {
  return slotOptions.find((item) => item.value === value)?.label || value || '-'
}

function qualityName(value) {
  return { valid: ui.valid, incomplete: ui.incomplete, suspicious: ui.suspicious }[value] || value || '-'
}

function qualityType(value) {
  return { valid: 'success', incomplete: 'warning', suspicious: 'danger' }[value] || 'info'
}

function detailItems(record) {
  const detail = record?.detail || {}
  return Object.entries(detail)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => ({ key, value: typeof value === 'object' ? JSON.stringify(value) : String(value) }))
}

function slotAverages() {
  return slotOptions.map((slot) => {
    const records = selectedUserRecords.value.filter((record) => record.slot === slot.value)
    return {
      slot: slot.label,
      pulse_rate: average(records, 'pulse_rate'),
      force: average(records, 'force'),
      tension: average(records, 'tension'),
      fluency: average(records, 'fluency')
    }
  })
}

function userAverages() {
  return users.value.map((user) => {
    const records = analysisRecords.value.filter((record) => record.user_id === user.user_id)
    return {
      name: user.name,
      pulse_rate: average(records, 'pulse_rate'),
      force: average(records, 'force'),
      tension: average(records, 'tension'),
      fluency: average(records, 'fluency')
    }
  })
}

function ensureChart(instance, refValue) {
  if (!refValue) return null
  return instance || echarts.init(refValue)
}

function renderTrendChart() {
  const records = selectedUserRecords.value
  trendChart = ensureChart(trendChart, trendChartRef.value)
  if (!trendChart) return
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 42, right: 18, top: 42, bottom: 36 },
    xAxis: { type: 'category', data: records.map((record) => `${record.visit_date || ''}\n${record.visit_time || ''}`) },
    yAxis: { type: 'value' },
    series: [
      { name: ui.pulseRate, type: 'line', smooth: true, data: records.map((record) => record.pulse_rate), symbolSize: 8 },
      { name: ui.force, type: 'line', smooth: true, data: records.map((record) => record.force), symbolSize: 8 },
      { name: ui.tension, type: 'line', smooth: true, data: records.map((record) => record.tension), symbolSize: 8 }
    ]
  }, true)
}

function renderSlotChart() {
  const data = slotAverages()
  slotChart = ensureChart(slotChart, slotChartRef.value)
  if (!slotChart) return
  slotChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 36, right: 12, top: 42, bottom: 30 },
    xAxis: { type: 'category', data: data.map((item) => item.slot) },
    yAxis: { type: 'value' },
    series: [
      { name: ui.pulseRate, type: 'bar', data: data.map((item) => item.pulse_rate), itemStyle: { borderRadius: [4, 4, 0, 0] } },
      { name: ui.force, type: 'bar', data: data.map((item) => item.force), itemStyle: { borderRadius: [4, 4, 0, 0] } },
      { name: ui.fluency, type: 'bar', data: data.map((item) => item.fluency), itemStyle: { borderRadius: [4, 4, 0, 0] } }
    ]
  }, true)
}

function renderStabilityChart() {
  const records = sameSlotRecords.value
  stabilityChart = ensureChart(stabilityChart, stabilityChartRef.value)
  if (!stabilityChart) return
  stabilityChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const record = params.data.record
        return `${record.user_name || '-'} ${slotName(record.slot)} ${record.side || '-'}<br/>${ui.pulseRate} ${formatNumber(record.pulse_rate, 1)}<br/>${ui.amplitude} ${formatNumber(record.amplitude, 2)}<br/>${ui.stability} ${formatNumber(record.stability_score, 1)}`
      }
    },
    grid: { left: 42, right: 18, top: 20, bottom: 36 },
    xAxis: { type: 'value', name: ui.pulseRate },
    yAxis: { type: 'value', name: ui.amplitude },
    series: [
      {
        name: ui.sameSlotStability,
        type: 'scatter',
        symbolSize: (data) => Math.max(10, Number(data[2] || 40) / 4),
        data: records.map((record) => ({
          value: [record.pulse_rate, record.amplitude, record.stability_score],
          record,
          itemStyle: { color: record.quality_status === 'suspicious' ? '#d94f45' : '#2f7d79' }
        }))
      }
    ]
  }, true)
}

function renderCrossUserChart() {
  const data = userAverages()
  crossUserChart = ensureChart(crossUserChart, crossUserChartRef.value)
  if (!crossUserChart) return
  crossUserChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 36, right: 14, top: 42, bottom: 34 },
    xAxis: { type: 'category', data: data.map((item) => item.name) },
    yAxis: { type: 'value' },
    series: [
      { name: ui.pulseRate, type: 'bar', data: data.map((item) => item.pulse_rate) },
      { name: ui.force, type: 'bar', data: data.map((item) => item.force) },
      { name: ui.tension, type: 'bar', data: data.map((item) => item.tension) }
    ]
  }, true)
}

function renderWaveformChart() {
  waveformChart = ensureChart(waveformChart, waveformChartRef.value)
  if (!waveformChart) return
  const record = selectedRecord.value
  const previews = record?.waveform_preview || []
  if (previews.length) {
    waveformChart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { top: 0 },
      grid: { left: 42, right: 18, top: 42, bottom: 34 },
      xAxis: { type: 'category', data: previews[0].points.map((_, index) => index + 1) },
      yAxis: { type: 'value' },
      series: previews.map((item) => ({ name: item.name, type: 'line', showSymbol: false, data: item.points }))
    }, true)
    return
  }
  const measurements = record?.measurements || []
  waveformChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 42, right: 18, top: 42, bottom: 34 },
    xAxis: { type: 'category', data: measurements.map((item) => item.type) },
    yAxis: { type: 'value' },
    series: [
      { name: ui.pulseRate, type: 'line', data: measurements.map((item) => item.pulse_rate_value) },
      { name: ui.force, type: 'line', data: measurements.map((item) => item.force_value) },
      { name: ui.tension, type: 'line', data: measurements.map((item) => item.tension_value) }
    ]
  }, true)
}

function renderAllCharts() {
  renderTrendChart()
  renderSlotChart()
  renderStabilityChart()
  renderCrossUserChart()
  renderWaveformChart()
}

function resizeCharts() {
  trendChart?.resize()
  slotChart?.resize()
  stabilityChart?.resize()
  crossUserChart?.resize()
  waveformChart?.resize()
}

function selectRecord(record) {
  selectedRecord.value = record
  nextTick(renderWaveformChart)
}

function openVisit(visitId) {
  activeVisitId.value = visitId
  visitDrawerVisible.value = true
}

function selectDefaultRecord() {
  const nextRecord = selectedUserRecords.value[0] || filteredRecords.value[0] || null
  if (!selectedRecord.value || !filteredRecords.value.some((record) => record.row_key === selectedRecord.value.row_key)) {
    selectedRecord.value = nextRecord
  }
}

onMounted(async () => {
  loading.value = true
  try {
    const [usersPayload, pulsePayload] = await Promise.all([
      api.users(),
      api.pulseRecords({ include_suspicious: true })
    ])
    users.value = Array.isArray(usersPayload) ? usersPayload : usersPayload.items || []
    pulseRecords.value = pulsePayload
    filters.value.userId = users.value[0]?.user_id || ''
    selectDefaultRecord()
  } finally {
    loading.value = false
  }
  await nextTick()
  renderAllCharts()
  window.addEventListener('resize', resizeCharts)
})

watch(filters, async () => {
  selectDefaultRecord()
  await nextTick()
  renderAllCharts()
}, { deep: true })

watch(pulseRecords, async () => {
  selectDefaultRecord()
  await nextTick()
  renderAllCharts()
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts)
  trendChart?.dispose()
  slotChart?.dispose()
  stabilityChart?.dispose()
  crossUserChart?.dispose()
  waveformChart?.dispose()
})
</script>

<style scoped>
.pulse-analysis {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-card,
.metric-card,
.panel-card {
  border-radius: 6px;
}

.full-width {
  width: 100%;
}

.panel-header {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
}

.stats-row,
.section-row {
  row-gap: 16px;
}

.metric-card {
  min-height: 112px;
}

.metric-value {
  color: #1f4f4c;
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
}

.metric-label {
  color: #303133;
  font-size: 14px;
  margin-top: 8px;
}

.metric-note,
.table-note {
  color: #7a858f;
  font-size: 12px;
}

.chart {
  height: 320px;
  width: 100%;
}

.large-chart {
  height: 360px;
}

.expanded-record {
  background: #f8fafc;
  padding: 12px 16px;
}

.expanded-title {
  color: #303133;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 10px;
}

.detail-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}

.detail-item {
  background: #fff;
  border: 1px solid #edf0f5;
  border-radius: 4px;
  min-width: 0;
  padding: 8px;
}

.detail-key {
  color: #7a858f;
  display: block;
  font-size: 12px;
}

.detail-value {
  color: #1f2d3d;
  display: block;
  font-size: 13px;
  margin-top: 4px;
  overflow-wrap: anywhere;
}

.measurement-table {
  margin-top: 12px;
}
</style>
