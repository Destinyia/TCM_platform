<template>
  <div class="pulse-analysis">
    <el-card shadow="never" class="filter-card">
      <template #header>
        <div class="panel-header">
          <span>脉诊分析工作台</span>
          <el-tag type="success">静态数据接口验证</el-tag>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :xs="24" :md="6">
          <el-select v-model="filters.userId" placeholder="选择用户" class="full-width" :loading="loading">
            <el-option v-for="user in users" :key="user.user_id" :label="`${user.display_id} ${user.name}`" :value="user.user_id" />
          </el-select>
        </el-col>
        <el-col :xs="24" :md="5">
          <el-select v-model="filters.slot" placeholder="时段" class="full-width">
            <el-option label="早" value="早" />
            <el-option label="中" value="中" />
            <el-option label="晚" value="晚" />
          </el-select>
        </el-col>
        <el-col :xs="24" :md="5">
          <el-select v-model="filters.source" placeholder="来源" class="full-width">
            <el-option label="全部来源" value="all" />
            <el-option label="中科" value="zhongke" />
            <el-option label="玉生堂" value="yushengtang" />
          </el-select>
        </el-col>
        <el-col :xs="24" :md="8">
          <el-checkbox v-model="filters.includeSuspicious">纳入疑似异常记录做敏感性观察</el-checkbox>
        </el-col>
      </el-row>
    </el-card>

    <el-row :gutter="16" class="stats-row">
      <el-col :xs="24" :sm="12" :lg="6" v-for="card in metricCards" :key="card.label">
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
              <span>{{ selectedUser?.name }} 纵向脉诊趋势</span>
              <el-tag size="small">pulse_rate / force / tension</el-tag>
            </div>
          </template>
          <div ref="trendChartRef" class="chart large-chart"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="10">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>早中晚特征变化</span>
              <el-tag size="small" type="warning">slot drift</el-tag>
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
              <span>同一用户同一时段稳定性</span>
              <el-tag size="small">{{ filters.slot }} | {{ selectedUser?.name }}</el-tag>
            </div>
          </template>
          <div ref="stabilityChartRef" class="chart"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>不同用户特征差异</span>
              <el-tag size="small" type="success">cross user</el-tag>
            </div>
          </template>
          <div ref="crossUserChartRef" class="chart"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="panel-card section-row">
      <template #header>
        <div class="panel-header">
          <span>脉诊记录明细</span>
          <span class="table-note">当前筛选 {{ filteredRecords.length }} 条，纳入分析 {{ analysisRecords.length }} 条</span>
        </div>
      </template>
      <el-table v-loading="loading" :data="filteredRecords" size="small" height="340">
        <el-table-column prop="visit_date" label="日期" width="112" />
        <el-table-column prop="visit_time" label="时间" width="78" />
        <el-table-column prop="user_name" label="用户" width="90" />
        <el-table-column prop="slot" label="时段" width="64" />
        <el-table-column prop="source_vendor" label="来源" width="94">
          <template #default="{ row }">
            <el-tag size="small" :type="row.source_vendor === 'zhongke' ? 'primary' : 'success'">
              {{ sourceName(row.source_vendor) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="side" label="侧别" width="70" />
        <el-table-column prop="pulse_type" label="脉象" width="86" />
        <el-table-column prop="pulse_rate" label="脉率" width="76" />
        <el-table-column prop="force" label="脉力" width="76" />
        <el-table-column prop="tension" label="紧张度" width="86" />
        <el-table-column prop="fluency" label="流利度" width="86" />
        <el-table-column prop="amplitude" label="幅值" width="80" />
        <el-table-column prop="stability_score" label="稳定性" width="86" />
        <el-table-column prop="quality_status" label="质量" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="qualityType(row.quality_status)">
              {{ qualityName(row.quality_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="纳入" width="76">
          <template #default="{ row }">
            <el-tag size="small" :type="row.included ? 'success' : 'info'">
              {{ row.included ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts'
import { api } from '../services/api'

const filters = ref({
  userId: '',
  slot: '早',
  source: 'all',
  includeSuspicious: false
})
const users = ref([])
const pulseRecords = ref([])
const loading = ref(false)

const trendChartRef = ref(null)
const slotChartRef = ref(null)
const stabilityChartRef = ref(null)
const crossUserChartRef = ref(null)
let trendChart
let slotChart
let stabilityChart
let crossUserChart

const selectedUser = computed(() => users.value.find((user) => user.user_id === filters.value.userId))

const filteredRecords = computed(() => {
  return pulseRecords.value.filter((record) => {
    const sourceMatched = filters.value.source === 'all' || record.source_vendor === filters.value.source
    const qualityMatched = filters.value.includeSuspicious || record.included
    return sourceMatched && qualityMatched
  })
})

const analysisRecords = computed(() => filteredRecords.value.filter((record) => record.included || filters.value.includeSuspicious))

const selectedUserRecords = computed(() => {
  return analysisRecords.value
    .filter((record) => record.user_id === filters.value.userId)
    .sort((a, b) => `${a.visit_date} ${a.visit_time}`.localeCompare(`${b.visit_date} ${b.visit_time}`))
})

const sameSlotRecords = computed(() => {
  return selectedUserRecords.value.filter((record) => record.slot === filters.value.slot)
})

const metricCards = computed(() => {
  const records = selectedUserRecords.value
  const slotRecords = sameSlotRecords.value
  return [
    {
      label: '平均脉率',
      value: `${round(average(records, 'pulse_rate'), 0)} 次/分`,
      note: `${selectedUser.value?.name || ''} 当前筛选记录`
    },
    {
      label: '平均脉力',
      value: round(average(records, 'force'), 1),
      note: '0-100 标准化特征'
    },
    {
      label: '同槽位稳定性',
      value: round(average(slotRecords, 'stability_score'), 0),
      note: `${filters.value.slot}时段 ${slotRecords.length} 条记录`
    },
    {
      label: '疑似异常影响',
      value: `${pulseRecords.value.filter((record) => !record.included).length} 条`,
      note: filters.value.includeSuspicious ? '已纳入敏感性观察' : '默认排除分析'
    }
  ]
})

function average(records, key) {
  const values = records.map((record) => Number(record[key])).filter((value) => Number.isFinite(value))
  if (!values.length) return 0
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function round(value, digits = 1) {
  return Number(value || 0).toFixed(digits)
}

function sourceName(value) {
  return value === 'zhongke' ? '中科' : value === 'yushengtang' ? '玉生堂' : value
}

function qualityName(value) {
  return { valid: '有效', incomplete: '不完整', suspicious: '疑似异常' }[value] || value
}

function qualityType(value) {
  return { valid: 'success', incomplete: 'warning', suspicious: 'danger' }[value] || 'info'
}

function slotAverages() {
  return ['早', '中', '晚'].map((slot) => {
    const records = selectedUserRecords.value.filter((record) => record.slot === slot)
    return {
      slot,
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
      fluency: average(records, 'fluency'),
      amplitude: average(records, 'amplitude') * 100
    }
  })
}

function renderTrendChart() {
  const records = selectedUserRecords.value
  trendChart = trendChart || echarts.init(trendChartRef.value)
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 42, right: 18, top: 42, bottom: 36 },
    xAxis: {
      type: 'category',
      data: records.map((record) => `${record.visit_date}\n${record.visit_time}`)
    },
    yAxis: { type: 'value' },
    series: [
      { name: '脉率', type: 'line', smooth: true, data: records.map((record) => record.pulse_rate), symbolSize: 8 },
      { name: '脉力', type: 'line', smooth: true, data: records.map((record) => record.force), symbolSize: 8 },
      { name: '紧张度', type: 'line', smooth: true, data: records.map((record) => record.tension), symbolSize: 8 }
    ]
  }, true)
}

function renderSlotChart() {
  const data = slotAverages()
  slotChart = slotChart || echarts.init(slotChartRef.value)
  slotChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 36, right: 12, top: 42, bottom: 30 },
    xAxis: { type: 'category', data: data.map((item) => item.slot) },
    yAxis: { type: 'value' },
    series: [
      { name: '脉率', type: 'bar', data: data.map((item) => round(item.pulse_rate, 1)), itemStyle: { borderRadius: [4, 4, 0, 0] } },
      { name: '脉力', type: 'bar', data: data.map((item) => round(item.force, 1)), itemStyle: { borderRadius: [4, 4, 0, 0] } },
      { name: '流利度', type: 'bar', data: data.map((item) => round(item.fluency, 1)), itemStyle: { borderRadius: [4, 4, 0, 0] } }
    ]
  }, true)
}

function renderStabilityChart() {
  const records = sameSlotRecords.value
  stabilityChart = stabilityChart || echarts.init(stabilityChartRef.value)
  stabilityChart.setOption({
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        const record = params.data.record
        return `${record.user_name} ${record.slot} ${record.side}<br/>脉率 ${record.pulse_rate}<br/>幅值 ${record.amplitude}<br/>稳定性 ${record.stability_score}`
      }
    },
    grid: { left: 42, right: 18, top: 20, bottom: 36 },
    xAxis: { type: 'value', name: '脉率', min: 55, max: 95 },
    yAxis: { type: 'value', name: '幅值', min: 0.6, max: 1.1 },
    series: [
      {
        name: '同槽位记录',
        type: 'scatter',
        symbolSize: (data) => Math.max(10, data[2] / 4),
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
  crossUserChart = crossUserChart || echarts.init(crossUserChartRef.value)
  crossUserChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 36, right: 14, top: 42, bottom: 34 },
    xAxis: { type: 'category', data: data.map((item) => item.name) },
    yAxis: { type: 'value' },
    series: [
      { name: '脉率', type: 'bar', data: data.map((item) => round(item.pulse_rate, 1)) },
      { name: '脉力', type: 'bar', data: data.map((item) => round(item.force, 1)) },
      { name: '紧张度', type: 'bar', data: data.map((item) => round(item.tension, 1)) }
    ]
  }, true)
}

function renderAllCharts() {
  if (!trendChartRef.value) return
  renderTrendChart()
  renderSlotChart()
  renderStabilityChart()
  renderCrossUserChart()
}

function resizeCharts() {
  trendChart?.resize()
  slotChart?.resize()
  stabilityChart?.resize()
  crossUserChart?.resize()
}

onMounted(async () => {
  loading.value = true
  try {
    const [usersPayload, pulsePayload] = await Promise.all([
      api.users(),
      api.pulseRecords({ include_suspicious: true })
    ])
    users.value = usersPayload
    pulseRecords.value = pulsePayload
    filters.value.userId = usersPayload[0]?.user_id || ''
  } finally {
    loading.value = false
  }
  await nextTick()
  renderAllCharts()
  window.addEventListener('resize', resizeCharts)
})

watch(filters, async () => {
  await nextTick()
  renderAllCharts()
}, { deep: true })

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts)
  trendChart?.dispose()
  slotChart?.dispose()
  stabilityChart?.dispose()
  crossUserChart?.dispose()
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
</style>
