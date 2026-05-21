<template>
  <div class="pulse-analysis">
    <template v-if="viewMode === 'patients'">
      <el-row :gutter="16" class="workspace-row detail-workspace">
        <el-col :xs="24" :lg="8" class="detail-side-col">
          <el-card shadow="never" class="panel-card list-panel detail-list-panel">
            <template #header>
              <div class="panel-header">
                <span>患者列表</span>
                <el-tag size="small">{{ filteredPatients.length }} 人</el-tag>
              </div>
            </template>
            <el-input
              v-model="patientKeyword"
              clearable
              placeholder="搜索患者或脱敏编号"
              class="search-input"
            />
            <div v-loading="loading" class="patient-list">
              <button
                v-for="patient in pagedPatients"
                :key="patient.user_id"
                type="button"
                class="patient-row"
                :class="{ active: patient.user_id === selectedUserId }"
                @click="selectPatient(patient.user_id)"
              >
                <span class="patient-main">
                  <span class="patient-name">{{ patient.name }}</span>
                  <span class="patient-id">{{ patient.display_id }}</span>
                </span>
                <span class="patient-meta">
                  <span>{{ patient.pulse_count }} 条脉诊</span>
                  <span>{{ patient.last_pulse_date || '-' }}</span>
                </span>
              </button>
            </div>
            <el-pagination
              v-model:current-page="patientPage"
              :page-size="patientPageSize"
              :total="filteredPatients.length"
              small
              layout="prev, pager, next"
              class="patient-pagination"
            />
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="16" class="detail-main-col">
          <el-card shadow="never" class="panel-card detail-analysis-panel">
            <template #header>
              <div class="panel-header">
                <span>{{ selectedPatient?.name || '患者统计' }}</span>
                <div class="header-actions">
                  <el-button :disabled="!selectedPatient" @click="openPlatformPatient">平台患者详情</el-button>
                  <el-button type="primary" :disabled="!selectedPatient" @click="openPulseDetail">查看详情</el-button>
                </div>
              </div>
            </template>

            <el-empty v-if="!selectedPatient" description="请选择左侧患者" :image-size="96" />
            <template v-else>
              <div class="metric-grid">
                <div v-for="card in patientMetricCards" :key="card.label" class="metric-card">
                  <span class="metric-value">{{ card.value }}</span>
                  <span class="metric-label">{{ card.label }}</span>
                  <span class="metric-note">{{ card.note }}</span>
                </div>
              </div>

              <el-row :gutter="16" class="chart-row">
                <el-col :xs="24" :lg="14">
                  <div ref="patientTrendChartRef" class="chart"></div>
                </el-col>
                <el-col :xs="24" :lg="10">
                  <div ref="patientSlotChartRef" class="chart"></div>
                </el-col>
              </el-row>

              <el-table :data="selectedPatientRecentRecords" size="small" height="220" class="record-preview-table">
                <el-table-column prop="visit_date" label="日期" width="110" />
                <el-table-column prop="visit_time" label="时间" width="80" />
                <el-table-column prop="slot" label="时段" width="70" />
                <el-table-column prop="source_vendor" label="来源" width="96">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.source_vendor === 'zhongke' ? 'primary' : 'success'">
                      {{ sourceName(row.source_vendor) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="pulse_type" label="脉象" min-width="120" show-overflow-tooltip />
                <el-table-column prop="pulse_rate" label="脉率" width="82" />
                <el-table-column prop="stability_score" label="稳定性" width="92" />
              </el-table>
            </template>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <template v-else>
      <div class="detail-toolbar">
        <el-button @click="backToPatients">返回患者列表</el-button>
        <div class="detail-title">
          <span>{{ selectedPatient?.name || '-' }}</span>
          <small>{{ selectedPatient?.display_id || '' }} · {{ selectedPatientRecords.length }} 条脉诊记录</small>
        </div>
        <el-button type="primary" plain @click="openPlatformPatient">平台患者详情</el-button>
      </div>

      <el-row :gutter="16" class="workspace-row">
        <el-col :xs="24" :lg="8">
          <el-card shadow="never" class="panel-card list-panel">
            <template #header>
              <div class="panel-header">
                <span>脉诊记录</span>
                <el-select v-model="recordFilter" size="small" class="record-filter">
                  <el-option label="全部记录" value="all" />
                  <el-option label="完整有效" value="valid" />
                  <el-option label="初筛可用" value="partial" />
                  <el-option label="质量不足" value="invalid" />
                </el-select>
              </div>
            </template>
            <div class="record-list">
              <button
                v-for="record in filteredPatientRecords"
                :key="record.row_key"
                type="button"
                class="record-row"
                :class="{ active: record.row_key === selectedRecord?.row_key }"
                @click="selectRecord(record)"
              >
                <span class="record-date">{{ record.visit_date || '-' }} {{ record.visit_time || '' }}</span>
                <span class="record-meta">
                  <el-tag size="small" :type="record.source_vendor === 'zhongke' ? 'primary' : 'success'">
                    {{ sourceName(record.source_vendor) }}
                  </el-tag>
                  <el-tag size="small" :type="recordValidityType(record)">{{ recordValidityName(record) }}</el-tag>
                </span>
                <span class="record-values">
                  脉率 {{ formatNumber(record.pulse_rate, 0) }} · 稳定 {{ formatNumber(record.stability_score, 1) }}
                </span>
              </button>
            </div>
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="16">
          <el-card shadow="never" class="panel-card">
            <template #header>
              <div class="panel-header">
                <span>记录波形与分析</span>
                <span class="table-note">{{ selectedRecordTitle }}</span>
              </div>
            </template>
            <el-empty v-if="!selectedRecord" description="请选择左侧脉诊记录" :image-size="96" />
            <template v-else>
              <div class="record-summary-grid">
                <div class="record-summary-item">
                  <span>脉率</span>
                  <strong>{{ formatNumber(selectedRecord.pulse_rate, 0) }}</strong>
                </div>
                <div class="record-summary-item">
                  <span>脉力</span>
                  <strong>{{ formatNumber(selectedRecord.force, 1) }}</strong>
                </div>
                <div class="record-summary-item">
                  <span>幅值</span>
                  <strong>{{ formatNumber(selectedRecord.amplitude, 2) }}</strong>
                </div>
                <div class="record-summary-item">
                  <span>稳定性</span>
                  <strong>{{ formatNumber(selectedRecord.stability_score, 1) }}</strong>
                </div>
              </div>

              <div ref="waveformChartRef" class="chart waveform-chart"></div>
              <div ref="signalQualityChartRef" class="chart signal-chart"></div>

              <el-row :gutter="16" class="chart-row">
                <el-col :xs="24" :lg="11">
                  <el-descriptions :column="1" size="small" border>
                    <el-descriptions-item label="采集时间">{{ selectedRecord.visit_date || '-' }} {{ selectedRecord.visit_time || '' }}</el-descriptions-item>
                    <el-descriptions-item label="来源">{{ sourceName(selectedRecord.source_vendor) }}</el-descriptions-item>
                    <el-descriptions-item label="侧别/部位">{{ selectedRecord.side || '-' }} / {{ selectedRecord.position || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="脉象">{{ selectedRecord.pulse_type || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="质量">{{ qualityName(selectedRecord.quality_status) }}</el-descriptions-item>
                  </el-descriptions>
                </el-col>
                <el-col :xs="24" :lg="13">
                  <div ref="recordFeatureChartRef" class="chart feature-chart"></div>
                </el-col>
              </el-row>

              <el-table v-if="selectedRecord.measurements?.length" :data="selectedRecord.measurements" size="small" class="measurement-table">
                <el-table-column v-for="column in measurementColumns" :key="column.key" :prop="column.key" :label="column.label" min-width="92" />
              </el-table>
            </template>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { api } from '../services/api'

const router = useRouter()
const viewMode = ref('patients')
const loading = ref(false)
const users = ref([])
const pulseRecords = ref([])
const selectedUserId = ref('')
const selectedRecord = ref(null)
const patientKeyword = ref('')
const patientPage = ref(1)
const patientPageSize = 12
const recordFilter = ref('all')

const patientTrendChartRef = ref(null)
const patientSlotChartRef = ref(null)
const waveformChartRef = ref(null)
const recordFeatureChartRef = ref(null)
const signalQualityChartRef = ref(null)
let patientTrendChart
let patientSlotChart
let waveformChart
let recordFeatureChart
let signalQualityChart

const measurementColumns = [
  { key: 'type', label: '部位' },
  { key: 'pulse_rate_value', label: '脉率值' },
  { key: 'force_value', label: '脉力值' },
  { key: 'tension_value', label: '紧张值' },
  { key: 'fluency_value', label: '流利值' },
  { key: 'h1', label: 'h1' },
  { key: 'w_t', label: 'W/t' }
]

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

const patientSummaries = computed(() => {
  return users.value.map((user) => {
    const records = normalizedRecords.value.filter((record) => record.user_id === user.user_id)
    const validRecords = records.filter((record) => record.included)
    const last = [...records].sort(recordTimeCompare).at(-1)
    return {
      ...user,
      pulse_count: records.length,
      valid_pulse_count: validRecords.length,
      last_pulse_date: last?.visit_date || null,
      avg_pulse_rate: average(records, 'pulse_rate'),
      avg_force: average(records, 'force'),
      avg_stability: average(records, 'stability_score')
    }
  }).sort((left, right) => right.pulse_count - left.pulse_count || String(left.name).localeCompare(String(right.name)))
})

const filteredPatients = computed(() => {
  const keyword = patientKeyword.value.trim().toLowerCase()
  if (!keyword) return patientSummaries.value
  return patientSummaries.value.filter((patient) => {
    return String(patient.name || '').toLowerCase().includes(keyword)
      || String(patient.display_id || '').toLowerCase().includes(keyword)
  })
})

const pagedPatients = computed(() => {
  const start = (patientPage.value - 1) * patientPageSize
  return filteredPatients.value.slice(start, start + patientPageSize)
})

const selectedPatient = computed(() => patientSummaries.value.find((patient) => patient.user_id === selectedUserId.value))

const selectedPatientRecords = computed(() => {
  return normalizedRecords.value
    .filter((record) => record.user_id === selectedUserId.value)
    .sort(recordTimeCompare)
})

const selectedPatientRecentRecords = computed(() => [...selectedPatientRecords.value].reverse().slice(0, 8))

const filteredPatientRecords = computed(() => {
  return selectedPatientRecords.value.filter((record) => {
    if (recordFilter.value === 'valid') return record.included && record.stability_score >= 50
    if (recordFilter.value === 'partial') return record.included && record.stability_score < 50
    if (recordFilter.value === 'invalid') return !record.included
    return true
  }).reverse()
})

const patientMetricCards = computed(() => {
  const records = selectedPatientRecords.value
  const validCount = records.filter((record) => record.included).length
  return [
    { label: '脉诊记录', value: records.length, note: `${validCount} 条纳入分析` },
    { label: '平均脉率', value: `${formatNumber(average(records, 'pulse_rate'), 0)} bpm`, note: '当前患者全部脉诊' },
    { label: '平均脉力', value: formatNumber(average(records, 'force'), 1), note: '玉生堂/中科标准字段' },
    { label: '平均稳定性', value: formatNumber(average(records, 'stability_score'), 1), note: '解析记录质量信号' }
  ]
})

const selectedRecordTitle = computed(() => {
  if (!selectedRecord.value) return '-'
  return `${selectedRecord.value.visit_date || '-'} ${selectedRecord.value.visit_time || ''} · ${sourceName(selectedRecord.value.source_vendor)}`
})

const longitudinalSignalRows = computed(() => {
  const rows = []
  for (const record of selectedPatientRecords.value) {
    if (record.source_vendor !== 'yushengtang' || !Array.isArray(record.waveform_preview)) continue
    for (const channel of record.waveform_preview) {
      if (!['Cun', 'GuanMai', 'Chi'].includes(channel.name) || !Array.isArray(channel.points)) continue
      const metrics = waveformSignalMetrics(channel.points)
      rows.push({
        record,
        channel: channel.name,
        date: `${record.visit_date || ''} ${record.visit_time || ''}`.trim(),
        ...metrics
      })
    }
  }
  return rows
})

function toNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function average(records, key) {
  const values = records.map((record) => Number(record[key])).filter((value) => Number.isFinite(value))
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
}

function formatNumber(value, digits = 1) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(digits) : '-'
}

function sourceName(value) {
  return { zhongke: '中科', yushengtang: '玉生堂' }[value] || value || '-'
}

function qualityName(value) {
  return { valid: '有效', incomplete: '不完整', suspicious: '疑似异常', duplicate: '重复' }[value] || value || '-'
}

function recordValidityName(record) {
  if (!record.included) return '质量不足'
  return Number(record.stability_score) >= 50 ? '可分析' : '初筛'
}

function recordValidityType(record) {
  if (!record.included) return 'danger'
  return Number(record.stability_score) >= 50 ? 'success' : 'warning'
}

function recordTimeCompare(left, right) {
  return `${left.visit_date || ''} ${left.visit_time || ''}`.localeCompare(`${right.visit_date || ''} ${right.visit_time || ''}`)
}

function ensureChart(instance, refValue) {
  if (!refValue) return null
  if (instance && instance.getDom?.() !== refValue) {
    instance.dispose()
    return echarts.init(refValue)
  }
  return instance || echarts.init(refValue)
}

function disposePatientCharts() {
  patientTrendChart?.dispose()
  patientSlotChart?.dispose()
  patientTrendChart = null
  patientSlotChart = null
}

function disposeDetailCharts() {
  waveformChart?.dispose()
  recordFeatureChart?.dispose()
  signalQualityChart?.dispose()
  waveformChart = null
  recordFeatureChart = null
  signalQualityChart = null
}

function selectPatient(userId) {
  selectedUserId.value = userId
  selectedRecord.value = selectedPatientRecords.value.at(-1) || null
  nextTick(() => {
    renderPatientCharts()
    renderDetailCharts()
  })
}

function openPulseDetail() {
  disposeDetailCharts()
  viewMode.value = 'detail'
  selectedRecord.value = filteredPatientRecords.value[0] || selectedPatientRecords.value.at(-1) || null
  nextTick(renderDetailCharts)
}

function backToPatients() {
  disposePatientCharts()
  viewMode.value = 'patients'
  nextTick(renderPatientCharts)
}

function openPlatformPatient() {
  if (selectedUserId.value) {
    router.push(`/patients/${selectedUserId.value}`)
  }
}

function selectRecord(record) {
  selectedRecord.value = record
  nextTick(renderDetailCharts)
}

function slotGroups(records) {
  return ['早', '中', '晚', '重复'].map((slot) => {
    const items = records.filter((record) => record.slot === slot)
    return {
      slot,
      count: items.length,
      pulse_rate: average(items, 'pulse_rate'),
      stability_score: average(items, 'stability_score')
    }
  })
}

function renderPatientCharts() {
  if (viewMode.value !== 'patients') return
  renderPatientTrendChart()
  renderPatientSlotChart()
}

function renderPatientTrendChart() {
  patientTrendChart = ensureChart(patientTrendChart, patientTrendChartRef.value)
  if (!patientTrendChart) return
  const records = selectedPatientRecords.value
  patientTrendChart.setOption({
    title: { text: '脉率与稳定性趋势', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, right: 0 },
    grid: { left: 42, right: 18, top: 48, bottom: 36 },
    xAxis: { type: 'category', data: records.map((record) => `${record.visit_date || ''}\n${record.visit_time || ''}`) },
    yAxis: { type: 'value' },
    series: [
      { name: '脉率', type: 'line', smooth: true, data: records.map((record) => record.pulse_rate), symbolSize: 7 },
      { name: '稳定性', type: 'line', smooth: true, data: records.map((record) => record.stability_score), symbolSize: 7 }
    ]
  }, true)
}

function renderPatientSlotChart() {
  patientSlotChart = ensureChart(patientSlotChart, patientSlotChartRef.value)
  if (!patientSlotChart) return
  const rows = slotGroups(selectedPatientRecords.value)
  patientSlotChart.setOption({
    title: { text: '分时段均值', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, right: 0 },
    grid: { left: 38, right: 12, top: 48, bottom: 32 },
    xAxis: { type: 'category', data: rows.map((row) => row.slot), axisTick: { show: false } },
    yAxis: { type: 'value' },
    series: [
      { name: '脉率', type: 'bar', data: rows.map((row) => row.pulse_rate), itemStyle: { color: '#2f7d79', borderRadius: [4, 4, 0, 0] } },
      { name: '稳定性', type: 'bar', data: rows.map((row) => row.stability_score), itemStyle: { color: '#d6a13d', borderRadius: [4, 4, 0, 0] } }
    ]
  }, true)
}

function renderDetailCharts() {
  if (viewMode.value !== 'detail') return
  renderWaveformChart()
  renderRecordFeatureChart()
  renderSignalQualityChart()
}

function renderWaveformChart() {
  waveformChart = ensureChart(waveformChart, waveformChartRef.value)
  if (!waveformChart) return
  const previews = selectedRecord.value?.waveform_preview || []
  if (previews.length) {
    waveformChart.setOption({
      title: { text: '波形预览', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
      tooltip: { trigger: 'axis' },
      legend: { top: 0, right: 0 },
      grid: { left: 42, right: 18, top: 48, bottom: 34 },
      xAxis: { type: 'category', data: previews[0].points.map((_, index) => index + 1) },
      yAxis: { type: 'value' },
      series: previews.map((item) => ({ name: item.name, type: 'line', showSymbol: false, data: item.points }))
    }, true)
    return
  }
  const measurements = selectedRecord.value?.measurements || []
  waveformChart.setOption({
    title: { text: '部位特征曲线', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, right: 0 },
    grid: { left: 42, right: 18, top: 48, bottom: 34 },
    xAxis: { type: 'category', data: measurements.map((item) => item.type) },
    yAxis: { type: 'value' },
    series: [
      { name: '脉率', type: 'line', data: measurements.map((item) => item.pulse_rate_value) },
      { name: '脉力', type: 'line', data: measurements.map((item) => item.force_value) },
      { name: '紧张度', type: 'line', data: measurements.map((item) => item.tension_value) }
    ]
  }, true)
}

function renderRecordFeatureChart() {
  recordFeatureChart = ensureChart(recordFeatureChart, recordFeatureChartRef.value)
  if (!recordFeatureChart) return
  const record = selectedRecord.value || {}
  const rows = [
    ['脉率', record.pulse_rate],
    ['脉力', record.force],
    ['紧张度', record.tension],
    ['流利度', record.fluency],
    ['稳定性', record.stability_score]
  ]
  recordFeatureChart.setOption({
    title: { text: '核心特征', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 16, top: 44, bottom: 22 },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: rows.map((row) => row[0]), axisTick: { show: false } },
    series: [{
      type: 'bar',
      data: rows.map((row) => row[1]),
      label: { show: true, position: 'right', formatter: ({ value }) => formatNumber(value, 1) },
      itemStyle: { color: '#2f7d79', borderRadius: [0, 4, 4, 0] }
    }]
  }, true)
}

function percentile(values, ratio) {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const index = Math.min(sorted.length - 1, Math.max(0, Math.floor((sorted.length - 1) * ratio)))
  return sorted[index]
}

function mean(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
}

function std(values) {
  if (values.length < 2) return 0
  const avg = mean(values)
  return Math.sqrt(mean(values.map((value) => (value - avg) ** 2)))
}

function detrend(values) {
  const numeric = values.map(Number).filter((value) => Number.isFinite(value))
  if (numeric.length < 3) return numeric
  const n = numeric.length
  const xMean = (n - 1) / 2
  const yMean = mean(numeric)
  let numerator = 0
  let denominator = 0
  for (let index = 0; index < n; index += 1) {
    numerator += (index - xMean) * (numeric[index] - yMean)
    denominator += (index - xMean) ** 2
  }
  const slope = denominator ? numerator / denominator : 0
  const intercept = yMean - slope * xMean
  return numeric.map((value, index) => value - (intercept + slope * index))
}

function autocorrelationPeak(values) {
  if (values.length < 8) return 0
  const base = values.map((value) => value - mean(values))
  const energy = base.reduce((sum, value) => sum + value * value, 0)
  if (!energy) return 0
  let best = 0
  const maxLag = Math.min(28, Math.floor(values.length / 2))
  for (let lag = 3; lag <= maxLag; lag += 1) {
    let numerator = 0
    for (let index = lag; index < base.length; index += 1) {
      numerator += base[index] * base[index - lag]
    }
    best = Math.max(best, numerator / energy)
  }
  return Math.max(0, best)
}

function waveformSignalMetrics(points) {
  const residual = detrend(points)
  if (residual.length < 8) {
    return { amplitudeRange: 0, fluctuation: 0, noise: 0, periodicity: 0, periodicSnr: 0 }
  }
  const amplitudeRange = percentile(residual, 0.95) - percentile(residual, 0.05)
  const fluctuation = std(residual)
  const diffs = residual.slice(1).map((value, index) => value - residual[index])
  const noise = std(diffs)
  const periodicity = autocorrelationPeak(residual)
  const periodicSnr = amplitudeRange <= 0 ? 0 : (fluctuation / (noise + 1e-6)) * periodicity * Math.log1p(amplitudeRange * 10)
  return {
    amplitudeRange: Number(amplitudeRange.toFixed(4)),
    fluctuation: Number(fluctuation.toFixed(4)),
    noise: Number(noise.toFixed(4)),
    periodicity: Number(periodicity.toFixed(4)),
    periodicSnr: Number(periodicSnr.toFixed(4))
  }
}

function renderSignalQualityChart() {
  signalQualityChart = ensureChart(signalQualityChart, signalQualityChartRef.value)
  if (!signalQualityChart) return
  const rows = longitudinalSignalRows.value
  const dates = [...new Set(rows.map((row) => row.date))]
  signalQualityChart.setOption({
    title: { text: '同一患者寸关尺周期信噪比', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const lines = [params[0]?.axisValue || '']
        for (const item of params) {
          const row = item.data?.row
          lines.push(`${item.marker}${item.seriesName}: ${formatNumber(item.value, 3)} 周期=${formatNumber(row?.periodicity, 2)} 波动=${formatNumber(row?.amplitudeRange, 3)}`)
        }
        return lines.join('<br/>')
      }
    },
    legend: { top: 0, right: 0 },
    grid: { left: 42, right: 18, top: 48, bottom: 44 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', name: 'SNR' },
    series: ['Cun', 'GuanMai', 'Chi'].map((channel) => ({
      name: channel,
      type: 'line',
      smooth: true,
      symbolSize: 7,
      data: dates.map((date) => {
        const row = rows.find((item) => item.date === date && item.channel === channel)
        return row ? { value: row.periodicSnr, row } : null
      })
    }))
  }, true)
}

function resizeCharts() {
  patientTrendChart?.resize()
  patientSlotChart?.resize()
  waveformChart?.resize()
  recordFeatureChart?.resize()
  signalQualityChart?.resize()
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
    selectedUserId.value = patientSummaries.value[0]?.user_id || users.value[0]?.user_id || ''
    selectedRecord.value = selectedPatientRecords.value.at(-1) || null
  } finally {
    loading.value = false
  }
  await nextTick()
  renderPatientCharts()
  window.addEventListener('resize', resizeCharts)
})

watch([selectedUserId, pulseRecords], async () => {
  selectedRecord.value = selectedPatientRecords.value.at(-1) || null
  await nextTick()
  renderPatientCharts()
  renderDetailCharts()
})

watch([recordFilter, viewMode], async () => {
  if (viewMode.value === 'detail' && !filteredPatientRecords.value.some((record) => record.row_key === selectedRecord.value?.row_key)) {
    selectedRecord.value = filteredPatientRecords.value[0] || null
  }
  await nextTick()
  renderPatientCharts()
  renderDetailCharts()
})

watch(patientKeyword, () => {
  patientPage.value = 1
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts)
  disposePatientCharts()
  disposeDetailCharts()
})
</script>

<style scoped>
.pulse-analysis {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.workspace-row,
.chart-row {
  row-gap: 16px;
}

.detail-workspace {
  align-items: stretch;
  height: calc(100vh - 178px);
  min-height: 620px;
}

.detail-side-col,
.detail-main-col {
  min-height: 0;
}

.panel-card {
  border-radius: 6px;
}

.panel-header,
.detail-toolbar,
.header-actions {
  align-items: center;
  display: flex;
  gap: 10px;
}

.panel-header {
  justify-content: space-between;
}

.detail-toolbar {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  justify-content: space-between;
  padding: 12px;
}

.detail-title {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.detail-title span {
  color: #1f2d3d;
  font-size: 16px;
  font-weight: 600;
}

.detail-title small,
.table-note {
  color: #7a858f;
  font-size: 12px;
}

.list-panel {
  min-height: 640px;
}

.detail-list-panel,
.detail-analysis-panel {
  height: 100%;
  min-height: 0;
}

.detail-list-panel :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  height: calc(100% - 57px);
  min-height: 0;
  overflow: hidden;
}

.detail-analysis-panel :deep(.el-card__body) {
  height: calc(100% - 57px);
  min-height: 0;
  overflow-y: auto;
}

.search-input {
  margin-bottom: 10px;
}

.patient-list,
.record-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.record-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
}

.patient-row,
.record-row {
  background: #fff;
  border: 1px solid #e7eceb;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 10px;
  text-align: left;
}

.patient-row:hover,
.record-row:hover,
.patient-row.active,
.record-row.active {
  background: #f1f8f7;
  border-color: #2f7d79;
}

.patient-main,
.patient-meta,
.record-meta,
.record-values {
  align-items: center;
  display: flex;
  gap: 8px;
  justify-content: space-between;
  min-width: 0;
}

.patient-name,
.record-date {
  color: #1f2d3d;
  font-size: 14px;
  font-weight: 600;
}

.patient-id,
.patient-meta,
.record-values {
  color: #7a858f;
  font-size: 12px;
}

.patient-pagination {
  justify-content: center;
  margin-top: 12px;
}

.metric-grid,
.record-summary-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 16px;
}

.metric-card,
.record-summary-item {
  background: #f7faf9;
  border: 1px solid #e2ecea;
  border-radius: 6px;
  min-width: 0;
  padding: 10px 12px;
}

.metric-value,
.record-summary-item strong {
  color: #1f4f4c;
  display: block;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}

.metric-label,
.record-summary-item span {
  color: #303133;
  display: block;
  font-size: 13px;
  margin-top: 8px;
}

.metric-note {
  color: #7a858f;
  display: block;
  font-size: 12px;
  margin-top: 6px;
}

.chart {
  height: 304px;
  width: 100%;
}

.waveform-chart {
  height: 300px;
  margin-bottom: 16px;
}

.signal-chart {
  height: 260px;
  margin-bottom: 16px;
}

.feature-chart {
  height: 220px;
}

.record-filter {
  width: 116px;
}

.record-preview-table,
.measurement-table {
  margin-top: 14px;
}

@media (max-width: 768px) {
  .metric-grid,
  .record-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .detail-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .detail-workspace {
    height: auto;
    min-height: 0;
  }

  .detail-list-panel,
  .detail-analysis-panel {
    height: auto;
  }

  .detail-list-panel :deep(.el-card__body),
  .detail-analysis-panel :deep(.el-card__body) {
    height: auto;
    max-height: none;
    overflow: visible;
  }

  .record-list {
    max-height: 420px;
  }
}
</style>
