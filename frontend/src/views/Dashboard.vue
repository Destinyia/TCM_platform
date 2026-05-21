<template>
  <div class="dashboard">
    <el-alert
      title="标准化离线数据已入库，当前页面通过 Flask API 动态读取，用于验证多模态呈现、治理视图和下游分析接口形态。"
      type="info"
      show-icon
      :closable="false"
      class="phase-alert"
    />

    <el-row :gutter="16" class="stats-row">
      <el-col :xs="24" :sm="12" :lg="6" v-for="item in statCards" :key="item.label">
        <el-card shadow="never" class="stat-card">
          <div class="stat-value">{{ item.value }}</div>
          <div class="stat-label">{{ item.label }}</div>
          <div class="stat-note">{{ item.note }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>模态覆盖率</span>
              <el-tag type="success" size="small">standard view</el-tag>
            </div>
          </template>
          <div ref="coverageChartRef" class="chart"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>质量事件分布</span>
              <el-tag type="warning" size="small">governance</el-tag>
            </div>
          </template>
          <div ref="qualityChartRef" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="panel-card pulse-panel" v-loading="pulseLoading">
      <template #header>
        <div class="panel-header">
          <span>脉诊一阶段分析</span>
          <el-button type="primary" link @click="router.push('/pulse-analysis')">进入工作台</el-button>
        </div>
      </template>
      <div class="pulse-summary-grid">
        <div class="pulse-metric">
          <span class="pulse-metric-value">{{ pulseSummary.valid_count || 0 }}</span>
          <span class="pulse-metric-label">完整有效</span>
        </div>
        <div class="pulse-metric">
          <span class="pulse-metric-value">{{ pulseSummary.partial_valid_count || 0 }}</span>
          <span class="pulse-metric-label">初筛可用</span>
        </div>
        <div class="pulse-metric">
          <span class="pulse-metric-value">{{ pulseSummary.invalid_count || 0 }}</span>
          <span class="pulse-metric-label">质量不足</span>
        </div>
        <div class="pulse-metric">
          <span class="pulse-metric-value">{{ pulseSummary.duration_unavailable_count || 0 }}</span>
          <span class="pulse-metric-label">缺时长</span>
        </div>
      </div>
      <el-row :gutter="16" class="pulse-chart-row">
        <el-col :xs="24" :lg="12">
          <div ref="pulseValidityChartRef" class="chart pulse-chart"></div>
        </el-col>
        <el-col :xs="24" :lg="12">
          <div ref="pulseRiskChartRef" class="chart pulse-chart"></div>
        </el-col>
      </el-row>
    </el-card>

    <el-row :gutter="16" class="section-row">
      <el-col :xs="24" :lg="14">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>最近多模态 visit</span>
              <el-button type="primary" link @click="router.push('/examinations')">查看全部</el-button>
            </div>
          </template>
          <el-table v-loading="loading" :data="recentVisits" size="small" height="304">
            <el-table-column prop="visit_time" label="采集时间" width="150" />
            <el-table-column prop="user_name" label="用户" width="90" />
            <el-table-column prop="source_vendor" label="来源" width="105">
              <template #default="{ row }">
                <el-tag size="small" :type="row.source_vendor === 'zhongke' ? 'primary' : 'success'">
                  {{ sourceName(row.source_vendor) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="time_window_slot" label="时段" width="70" />
            <el-table-column label="模态">
              <template #default="{ row }">
                <el-space wrap>
                  <el-tag v-for="modality in row.modalities" :key="modality" size="small" effect="plain">
                    {{ modalityName(modality) }}
                  </el-tag>
                </el-space>
              </template>
            </el-table-column>
            <el-table-column prop="quality_status" label="质量" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="qualityType(row.quality_status)">
                  {{ qualityName(row.quality_status) }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="10">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>常用入口</span>
              <el-tag size="small">workflow</el-tag>
            </div>
          </template>
          <div class="quick-actions">
            <el-button type="primary" @click="router.push('/checkin-matrix')">查看打卡矩阵</el-button>
            <el-button @click="router.push('/patients')">患者管理</el-button>
            <el-button @click="router.push('/pulse-analysis')">脉诊分析</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { api } from '../services/api'

const router = useRouter()
const coverageChartRef = ref(null)
const qualityChartRef = ref(null)
const pulseValidityChartRef = ref(null)
const pulseRiskChartRef = ref(null)
const loading = ref(false)
const pulseLoading = ref(false)
const summary = ref({
  stats: {},
  modality_coverage: [],
  quality_distribution: [],
  recent_visits: []
})
const pulseSummary = ref({
  available: false,
  source_quality: [],
  feature_risks: []
})
let coverageChart
let qualityChart
let pulseValidityChart
let pulseRiskChart

const recentVisits = computed(() => summary.value.recent_visits || [])
const statCards = computed(() => [
  { label: '脱敏用户', value: summary.value.stats.user_count || 0, note: '按 canonical user 聚合' },
  { label: '标准 visit', value: summary.value.stats.visit_count || 0, note: '保留来源证据与时段口径' },
  { label: '文件资产', value: summary.value.stats.asset_count || 0, note: '图片、PDF、脉波、语音' },
  { label: '质量事件', value: summary.value.stats.quality_event_count || 0, note: '缺失、重复、兜底、聚合' }
])

const modalityLabels = {
  ask: '问诊',
  pulse: '脉诊',
  tongue: '舌诊',
  face: '面诊',
  voice: '声诊',
  report: '报告'
}

function modalityName(value) {
  return modalityLabels[value] || value
}

function sourceName(value) {
  return value === 'zhongke' ? '中科' : value === 'yushengtang' ? '玉生堂' : value
}

function qualityName(value) {
  return { valid: '有效', incomplete: '不完整', suspicious: '疑似异常', duplicate: '重复' }[value] || value
}

function qualityType(value) {
  return { valid: 'success', incomplete: 'warning', suspicious: 'danger', duplicate: 'info' }[value] || 'info'
}

function renderCoverageChart() {
  if (!coverageChartRef.value) return
  const keys = Object.keys(modalityLabels)
  const coverage = summary.value.modality_coverage || []
  const data = keys.map((key) => coverage.find((item) => item.modality === key)?.count || 0)
  coverageChart = coverageChart || echarts.init(coverageChartRef.value)
  coverageChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 36, right: 16, top: 24, bottom: 34 },
    xAxis: { type: 'category', data: keys.map(modalityName), axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [{ name: 'visit 数', type: 'bar', barWidth: 28, data, itemStyle: { color: '#2f7d79', borderRadius: [4, 4, 0, 0] } }]
  }, true)
}

function renderQualityChart() {
  if (!qualityChartRef.value) return
  const grouped = summary.value.quality_distribution || []
  qualityChart = qualityChart || echarts.init(qualityChartRef.value)
  qualityChart.setOption({
    tooltip: { trigger: 'item' },
    legend: { bottom: 0, type: 'scroll' },
    series: [{ type: 'pie', radius: ['42%', '68%'], center: ['50%', '43%'], data: grouped.map((item) => ({ name: item.flag, value: item.count })), label: { formatter: '{b}\n{c}' } }]
  }, true)
}

function renderPulseValidityChart() {
  if (!pulseValidityChartRef.value) return
  const rows = pulseSummary.value.source_quality || []
  const labels = rows.map((item) => sourceName(item.source_vendor))
  pulseValidityChart = pulseValidityChart || echarts.init(pulseValidityChartRef.value)
  pulseValidityChart.setOption({
    title: { text: '来源质量分布', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, right: 0 },
    grid: { left: 40, right: 16, top: 48, bottom: 34 },
    xAxis: { type: 'category', data: labels, axisTick: { show: false } },
    yAxis: { type: 'value', minInterval: 1 },
    series: [
      { name: '完整有效', type: 'bar', stack: 'quality', data: rows.map((item) => item.valid_count), itemStyle: { color: '#2f7d79' } },
      { name: '初筛可用', type: 'bar', stack: 'quality', data: rows.map((item) => item.partial_valid_count), itemStyle: { color: '#d6a13d' } },
      { name: '质量不足', type: 'bar', stack: 'quality', data: rows.map((item) => item.invalid_count), itemStyle: { color: '#b05a4a' } }
    ]
  }, true)
}

function renderPulseRiskChart() {
  if (!pulseRiskChartRef.value) return
  const rows = (pulseSummary.value.feature_risks || []).slice(0, 6).reverse()
  pulseRiskChart = pulseRiskChart || echarts.init(pulseRiskChartRef.value)
  pulseRiskChart.setOption({
    title: { text: '特征可靠性风险', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 72, right: 18, top: 44, bottom: 24 },
    xAxis: { type: 'value', max: 50 },
    yAxis: { type: 'category', data: rows.map((item) => item.feature_name), axisTick: { show: false } },
    series: [{
      name: 'risk score',
      type: 'bar',
      data: rows.map((item) => item.risk_score),
      label: { show: true, position: 'right', formatter: ({ value }) => Number(value).toFixed(1) },
      itemStyle: {
        color: ({ value }) => (value >= 40 ? '#b05a4a' : value >= 25 ? '#d6a13d' : '#2f7d79'),
        borderRadius: [0, 4, 4, 0]
      }
    }]
  }, true)
}

function resizeCharts() {
  coverageChart?.resize()
  qualityChart?.resize()
  pulseValidityChart?.resize()
  pulseRiskChart?.resize()
}

onMounted(async () => {
  loading.value = true
  pulseLoading.value = true
  try {
    const [summaryResult, pulseResult] = await Promise.allSettled([
      api.summary(),
      api.pulsePhase1Summary()
    ])
    if (summaryResult.status === 'fulfilled') {
      summary.value = summaryResult.value
    }
    if (pulseResult.status === 'fulfilled') {
      pulseSummary.value = pulseResult.value
    }
  } finally {
    loading.value = false
    pulseLoading.value = false
  }
  await nextTick()
  renderCoverageChart()
  renderQualityChart()
  renderPulseValidityChart()
  renderPulseRiskChart()
  window.addEventListener('resize', resizeCharts)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts)
  coverageChart?.dispose()
  qualityChart?.dispose()
  pulseValidityChart?.dispose()
  pulseRiskChart?.dispose()
})
</script>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.phase-alert {
  border-radius: 6px;
}
.stats-row,
.section-row {
  margin-bottom: 16px;
  row-gap: 16px;
}
.stat-card,
.panel-card {
  border-radius: 6px;
}
.stat-card {
  min-height: 118px;
}
.stat-value {
  color: #1f4f4c;
  font-size: 30px;
  font-weight: 700;
  line-height: 1.2;
}
.stat-label {
  color: #303133;
  font-size: 14px;
  margin-top: 8px;
}
.stat-note {
  color: #7a858f;
  font-size: 12px;
  margin-top: 6px;
}
.panel-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
}
.chart {
  height: 304px;
  width: 100%;
}
.pulse-panel {
  margin-bottom: 16px;
}
.pulse-summary-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 12px;
}
.pulse-metric {
  background: #f7faf9;
  border: 1px solid #e2ecea;
  border-radius: 6px;
  min-width: 0;
  padding: 10px 12px;
}
.pulse-metric-value {
  color: #1f4f4c;
  display: block;
  font-size: 24px;
  font-weight: 700;
  line-height: 1.1;
}
.pulse-metric-label {
  color: #69757f;
  display: block;
  font-size: 12px;
  margin-top: 6px;
}
.pulse-chart-row {
  row-gap: 12px;
}
.pulse-chart {
  height: 260px;
}
.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
@media (max-width: 768px) {
  .pulse-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
