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

    <el-card shadow="never" class="panel-card pulse-quality-panel" v-loading="pulseQualityLoading">
      <template #header>
        <div class="panel-header">
          <span>脉诊质量概览</span>
          <el-button type="primary" link @click="router.push('/pulse-analysis')">进入脉诊分析</el-button>
        </div>
      </template>
      <div class="pulse-quality-grid">
        <div v-for="item in pulseQualityCards" :key="item.label" class="pulse-quality-card">
          <span class="pulse-quality-value">{{ item.value }}</span>
          <span class="pulse-quality-label">{{ item.label }}</span>
          <span class="pulse-quality-note">{{ item.note }}</span>
        </div>
      </div>
      <el-row :gutter="16" class="pulse-chart-row">
        <el-col :xs="24" :lg="12">
          <div ref="pulsePatientRankChartRef" class="chart pulse-quality-chart" :style="patientChartStyle"></div>
        </el-col>
        <el-col :xs="24" :lg="12">
          <div ref="pulseQualityHeatmapRef" class="chart pulse-quality-chart" :style="patientChartStyle"></div>
        </el-col>
      </el-row>
      <el-row :gutter="16" class="pulse-chart-row">
        <el-col :xs="24" :lg="12">
          <div ref="pulseFailureStackChartRef" class="chart pulse-quality-chart" :style="patientChartStyle"></div>
        </el-col>
        <el-col :xs="24" :lg="12">
          <div ref="pulseChannelCombinationChartRef" class="chart pulse-quality-chart"></div>
        </el-col>
      </el-row>
      <el-row :gutter="16" class="pulse-chart-row">
        <el-col :xs="24" :lg="12">
          <div ref="pulseTemplateSignalScatterRef" class="chart pulse-quality-chart"></div>
        </el-col>
      </el-row>
      <el-row :gutter="16" class="pulse-chart-row">
        <el-col :xs="24" :lg="12">
          <div ref="pulseDeviceFitRiskChartRef" class="chart pulse-quality-chart" :style="deviceFitChartStyle"></div>
        </el-col>
        <el-col :xs="24" :lg="12">
          <div ref="pulseAlignmentHeatmapRef" class="chart pulse-quality-chart" :style="deviceFitChartStyle"></div>
        </el-col>
      </el-row>
      <el-alert
        v-if="pulseDeviceFitOverview.available && !pulseDeviceFitOverview.wrist_circumference_available"
        :title="pulseDeviceFitOverview.limitation_message"
        type="warning"
        show-icon
        :closable="false"
        class="pulse-fit-alert"
      />
    </el-card>

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
const pulsePatientRankChartRef = ref(null)
const pulseQualityHeatmapRef = ref(null)
const pulseFailureStackChartRef = ref(null)
const pulseChannelCombinationChartRef = ref(null)
const pulseTemplateSignalScatterRef = ref(null)
const pulseDeviceFitRiskChartRef = ref(null)
const pulseAlignmentHeatmapRef = ref(null)
const loading = ref(false)
const pulseLoading = ref(false)
const pulseQualityLoading = ref(false)
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
const pulseUsers = ref([])
const pulseRecords = ref([])
const pulseDeviceFitOverview = ref({ available: false, patients: [] })
let coverageChart
let qualityChart
let pulseValidityChart
let pulseRiskChart
let pulsePatientRankChart
let pulseQualityHeatmap
let pulseFailureStackChart
let pulseChannelCombinationChart
let pulseTemplateSignalScatter
let pulseDeviceFitRiskChart
let pulseAlignmentHeatmap
let highlightedPulseUser = null

// Overall-cohort calibration on 804 pulse records; each dimension targets about 25% pass rate.
const QUALITY_THRESHOLDS = {
  periodicSnr: 0.4055209903773839,
  templateStability: 28.09370144534219,
  signalQuality: 33.52063258926944,
  stableSegmentRatio: 0.5
}
const QUALITY_ACCEPTABLE_MAX_INSUFFICIENT_CHANNELS = 1
const QUALITY_CALIBRATION_TARGET = 0.25
const PULSE_CHANNELS = ['Cun', 'Guan', 'Chi']

const recentVisits = computed(() => summary.value.recent_visits || [])
const statCards = computed(() => [
  { label: '脱敏用户', value: summary.value.stats.user_count || 0, note: '按 canonical user 聚合' },
  { label: '标准 visit', value: summary.value.stats.visit_count || 0, note: '保留来源证据与时段口径' },
  { label: '文件资产', value: summary.value.stats.asset_count || 0, note: '图片、PDF、脉波、语音' },
  { label: '质量事件', value: summary.value.stats.quality_event_count || 0, note: '缺失、重复、兜底、聚合' }
])

const analyzedPulseRecords = computed(() => pulseRecords.value.map((record, index) => analyzePulseRecord(record, index)))
const pulsePatientQualityRows = computed(() => buildPatientQualityRows(analyzedPulseRecords.value, pulseUsers.value))
const pulseOverallQuality = computed(() => buildOverallPulseQuality(analyzedPulseRecords.value, pulsePatientQualityRows.value))
const pulseDeviceFitRows = computed(() => {
  const userMap = new Map((pulseUsers.value || []).map((user) => [user.user_id, user]))
  return (pulseDeviceFitOverview.value.patients || []).map((row) => {
    const user = userMap.get(row.user_id) || {}
    return {
      ...row,
      name: user.name || user.canonical_name || user.display_id || row.user_id
    }
  })
})
function patientChartHeight(rowCount) {
  return `${Math.min(760, Math.max(400, 118 + rowCount * 27))}px`
}
const patientChartStyle = computed(() => ({ height: patientChartHeight(Math.min(24, pulsePatientQualityRows.value.length)) }))
const deviceFitChartStyle = computed(() => ({ height: patientChartHeight(Math.min(24, pulseDeviceFitRows.value.length)) }))
const pulseQualityCards = computed(() => {
  const quality = pulseOverallQuality.value
  return [
    { label: '总患者数', value: quality.patientCount, note: '存在脉诊记录用户' },
    { label: '总记录数', value: quality.recordCount, note: '参与质量评价记录' },
    { label: '质量合格记录', value: quality.highQualityCount, note: '四项阈值且三通道均通过' },
    { label: '质量尚可记录', value: quality.acceptableQualityCount, note: '四项通过且最多1通道不足' },
    { label: '整体通过率', value: `${formatPercent(quality.qualityPassRate, 1)}%`, note: `单项校准目标 ${formatPercent(QUALITY_CALIBRATION_TARGET, 0)}%` },
    { label: '平均周期 SNR', value: formatNumber(quality.avgPeriodicSnr, 3), note: `通过 ${formatPercent(quality.dimensionRates.periodicSnr, 1)}% · 阈值 > ${formatNumber(QUALITY_THRESHOLDS.periodicSnr, 3)}` },
    { label: '平均模板稳定性', value: formatNumber(quality.avgTemplateStability, 1), note: `通过 ${formatPercent(quality.dimensionRates.templateStability, 1)}% · 阈值 > ${formatNumber(QUALITY_THRESHOLDS.templateStability, 1)}` },
    { label: '平均信号质量', value: formatNumber(quality.avgSignalQuality, 1), note: `通过 ${formatPercent(quality.dimensionRates.signalQuality, 1)}% · 阈值 > ${formatNumber(QUALITY_THRESHOLDS.signalQuality, 1)}` },
    { label: '平均稳定片段', value: `${formatPercent(quality.avgStableSegmentRatio, 1)}%`, note: `通过 ${formatPercent(quality.dimensionRates.stableSegmentRatio, 1)}% · 阈值 > ${formatPercent(QUALITY_THRESHOLDS.stableSegmentRatio, 1)}%` },
    { label: '局部通道未对准', value: quality.partialChannelCount, note: `1通道 ${quality.oneChannelCount} / 2通道 ${quality.twoChannelCount} · ${formatPercent(quality.partialChannelRate, 1)}%` },
    { label: '设备适配高风险', value: pulseDeviceFitOverview.value.high_risk_patient_count || 0, note: `持续通道异常 ${pulseDeviceFitOverview.value.persistent_alignment_patient_count || 0} 人` },
    { label: '主要瓶颈', value: quality.mainFailureLabel, note: '按失败频次统计' }
  ]
})

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

function toNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function formatNumber(value, digits = 1) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(digits) : '-'
}

function formatPercent(value, digits = 1) {
  const number = Number(value)
  return Number.isFinite(number) ? (number * 100).toFixed(digits) : '-'
}

function clamp(value, low = 0, high = 100) {
  const number = Number(value)
  if (!Number.isFinite(number)) return low
  return Math.max(low, Math.min(high, number))
}

function mean(values) {
  const numeric = values.map(Number).filter((value) => Number.isFinite(value))
  return numeric.length ? numeric.reduce((sum, value) => sum + value, 0) / numeric.length : null
}

function std(values) {
  const avg = mean(values)
  if (avg === null) return 0
  return Math.sqrt(mean(values.map((value) => (value - avg) ** 2)) || 0)
}

function variance(values) {
  const avg = mean(values)
  if (avg === null) return 0
  return mean(values.map((value) => (value - avg) ** 2)) || 0
}

function percentile(values, ratio) {
  const numeric = values.map(Number).filter((value) => Number.isFinite(value)).sort((a, b) => a - b)
  if (!numeric.length) return 0
  const index = Math.min(numeric.length - 1, Math.max(0, Math.floor((numeric.length - 1) * ratio)))
  return numeric[index]
}

function linearFit(values) {
  const numeric = values.map(Number).filter((value) => Number.isFinite(value))
  if (numeric.length < 3) return { slope: 0, residual: numeric }
  const n = numeric.length
  const xMean = (n - 1) / 2
  const yMean = mean(numeric) || 0
  let numerator = 0
  let denominator = 0
  for (let index = 0; index < n; index += 1) {
    numerator += (index - xMean) * (numeric[index] - yMean)
    denominator += (index - xMean) ** 2
  }
  const slope = denominator ? numerator / denominator : 0
  const intercept = yMean - slope * xMean
  return { slope, residual: numeric.map((value, index) => value - (intercept + slope * index)) }
}

function autocorrelationPeak(values) {
  if (values.length < 8) return { coherence: 0, lag: null }
  const avg = mean(values) || 0
  const base = values.map((value) => value - avg)
  const energy = base.reduce((sum, value) => sum + value * value, 0)
  if (!energy) return { coherence: 0, lag: null }
  let best = 0
  let bestLag = null
  const maxLag = Math.min(28, Math.floor(values.length / 2))
  for (let lag = 3; lag <= maxLag; lag += 1) {
    let numerator = 0
    for (let index = lag; index < base.length; index += 1) {
      numerator += base[index] * base[index - lag]
    }
    const corr = numerator / energy
    if (corr > best) {
      best = corr
      bestLag = lag
    }
  }
  return { coherence: Math.max(0, best), lag: bestLag }
}

function buildPeriodicTemplate(values, lag) {
  if (!lag || lag < 2 || values.length < lag * 2) return { repeated: values.map(() => 0), residual: values }
  const buckets = Array.from({ length: lag }, () => [])
  values.forEach((value, index) => buckets[index % lag].push(value))
  const template = buckets.map((bucket) => bucket.length ? (mean(bucket) || 0) : 0)
  const repeated = values.map((_, index) => template[index % lag])
  const residual = values.map((value, index) => value - repeated[index])
  return { repeated, residual }
}

function windowSegments(pointCount, lag) {
  if (pointCount < 32) return []
  let windowSize = Math.min(pointCount, Math.max(32, (lag || 10) * 4))
  if (pointCount >= 96) windowSize = Math.min(windowSize, Math.max(32, Math.floor(pointCount / 2)))
  const step = Math.max(8, Math.floor(windowSize / 2))
  const segments = []
  for (let start = 0; start + windowSize <= pointCount; start += step) {
    segments.push([start, start + windowSize])
  }
  if (segments.length && segments.at(-1)[1] < pointCount) segments.push([Math.max(0, pointCount - windowSize), pointCount])
  return segments.length ? segments : [[0, pointCount]]
}

function waveformMetrics(points) {
  const numeric = (points || []).map(Number).filter((value) => Number.isFinite(value))
  if (numeric.length < 16) {
    return { periodicSnr: 0, templateStability: 0, signalQuality: 0, stableSegmentRatio: 0, pulseEnergy: 0 }
  }
  const fit = linearFit(numeric)
  const { coherence, lag } = autocorrelationPeak(fit.residual)
  const { repeated, residual } = buildPeriodicTemplate(fit.residual, lag)
  const residualVariance = variance(residual)
  const templateVariance = variance(repeated)
  const detrendedVariance = variance(fit.residual)
  const amplitudeRange = percentile(numeric, 0.95) - percentile(numeric, 0.05)
  const residualFluctuation = amplitudeRange > 0 ? std(residual) / (amplitudeRange + 1e-6) : 1
  const templateExplained = detrendedVariance > 0 ? clamp(1 - residualVariance / detrendedVariance, 0, 1) : 0
  const periodicSnr = templateVariance / (residualVariance + 1e-6)
  const driftArtifact = amplitudeRange > 0 ? clamp(Math.abs(fit.slope) * numeric.length / (amplitudeRange + 1e-6), 0, 1) : 1
  const templateStability = clamp(templateExplained * 40 + coherence * 35 + Math.min(periodicSnr, 1) * 25 - residualFluctuation * 12 - driftArtifact * 18)
  const windows = windowSegments(numeric.length, lag).map(([start, end]) => waveformMetricsNoWindows(numeric.slice(start, end)))
  const stableSegmentRatio = windows.length
    ? windows.filter((item) => item.periodicSnr > QUALITY_THRESHOLDS.periodicSnr && item.templateStability > QUALITY_THRESHOLDS.templateStability).length / windows.length
    : 0
  const signalQuality = clamp(templateStability * 0.55 + Math.min(periodicSnr, 1) * 25 + Math.min(templateVariance * 5000, 20) - driftArtifact * 35)
  return { periodicSnr, templateStability, signalQuality, stableSegmentRatio, pulseEnergy: templateVariance }
}

function waveformMetricsNoWindows(points) {
  const numeric = (points || []).map(Number).filter((value) => Number.isFinite(value))
  if (numeric.length < 16) return { periodicSnr: 0, templateStability: 0 }
  const fit = linearFit(numeric)
  const { coherence, lag } = autocorrelationPeak(fit.residual)
  const { repeated, residual } = buildPeriodicTemplate(fit.residual, lag)
  const residualVariance = variance(residual)
  const templateVariance = variance(repeated)
  const detrendedVariance = variance(fit.residual)
  const amplitudeRange = percentile(numeric, 0.95) - percentile(numeric, 0.05)
  const residualFluctuation = amplitudeRange > 0 ? std(residual) / (amplitudeRange + 1e-6) : 1
  const templateExplained = detrendedVariance > 0 ? clamp(1 - residualVariance / detrendedVariance, 0, 1) : 0
  const periodicSnr = templateVariance / (residualVariance + 1e-6)
  const templateStability = clamp(templateExplained * 40 + coherence * 35 + Math.min(periodicSnr, 1) * 25 - residualFluctuation * 12)
  return { periodicSnr, templateStability }
}

function standardPulseChannel(name) {
  const value = String(name || '').toLowerCase()
  if (value === 'cun') return 'Cun'
  if (value === 'guan' || value === 'guanmai' || value === 'guan_mai') return 'Guan'
  if (value === 'chi') return 'Chi'
  return null
}

function metricFailures(metrics) {
  return {
    snr: metrics.periodicSnr <= QUALITY_THRESHOLDS.periodicSnr,
    template: metrics.templateStability <= QUALITY_THRESHOLDS.templateStability,
    signal: metrics.signalQuality <= QUALITY_THRESHOLDS.signalQuality,
    stable: metrics.stableSegmentRatio <= QUALITY_THRESHOLDS.stableSegmentRatio
  }
}

function analyzePulseRecord(record, index) {
  const channelMetrics = (record.waveform_preview || [])
    .map((channel) => ({ channel: standardPulseChannel(channel.name), points: channel.points }))
    .filter((channel) => channel.channel && Array.isArray(channel.points))
    .map((channel) => {
      const metrics = waveformMetrics(channel.points)
      const failures = metricFailures(metrics)
      return { channel: channel.channel, ...metrics, failures, qualityPass: !Object.values(failures).some(Boolean) }
    })
  const periodicSnr = mean(channelMetrics.map((item) => item.periodicSnr)) || 0
  const templateStability = mean(channelMetrics.map((item) => item.templateStability)) || 0
  const signalQuality = mean(channelMetrics.map((item) => item.signalQuality)) || 0
  const stableSegmentRatio = mean(channelMetrics.map((item) => item.stableSegmentRatio)) || 0
  const pulseEnergy = mean(channelMetrics.map((item) => item.pulseEnergy)) || 0
  const failures = metricFailures({ periodicSnr, templateStability, signalQuality, stableSegmentRatio })
  const failureCount = Object.values(failures).filter(Boolean).length
  const insufficientChannelCount = channelMetrics.filter((channel) => !channel.qualityPass).length
  const aggregatePass = failureCount === 0
  const qualityPass = aggregatePass && insufficientChannelCount === 0
  const qualityAcceptable = aggregatePass
    && insufficientChannelCount > 0
    && insufficientChannelCount <= QUALITY_ACCEPTABLE_MAX_INSUFFICIENT_CHANNELS
  let qualityState = '质量不足'
  if (qualityPass) qualityState = '质量合格'
  else if (qualityAcceptable) qualityState = '质量尚可'
  else if (insufficientChannelCount > 0 && insufficientChannelCount < 3) qualityState = `${insufficientChannelCount}通道质量不足`
  else if (insufficientChannelCount >= 3) qualityState = '三通道质量不足'
  return {
    ...record,
    row_id: record.record_id || record.measurement_id || record.source_measurement_id || record.source_asset_id || record.visit_id || `${record.user_id || 'record'}-${index}`,
    periodicSnr,
    templateStability,
    signalQuality,
    stableSegmentRatio,
    pulseEnergy,
    channelMetrics,
    insufficientChannelCount,
    partialChannelMisalignment: insufficientChannelCount > 0 && insufficientChannelCount < 3,
    failures,
    failureCount,
    qualityPass,
    qualityAcceptable,
    qualityState
  }
}

function buildPatientQualityRows(records, users) {
  const userMap = new Map((users || []).map((user) => [user.user_id, user]))
  const groups = new Map()
  records.forEach((record) => {
    if (!record.user_id) return
    const rows = groups.get(record.user_id) || []
    rows.push(record)
    groups.set(record.user_id, rows)
  })
  return [...groups.entries()].map(([userId, rows]) => {
    const user = userMap.get(userId) || {}
    const total = rows.length || 1
    const rates = {
      snr: rows.filter((record) => !record.failures.snr).length / total,
      template: rows.filter((record) => !record.failures.template).length / total,
      signal: rows.filter((record) => !record.failures.signal).length / total,
      stable: rows.filter((record) => !record.failures.stable).length / total,
      overall: rows.filter((record) => record.qualityPass).length / total
    }
    const channelRates = Object.fromEntries(PULSE_CHANNELS.map((channel) => {
      const channelRows = rows.map((record) => record.channelMetrics.find((item) => item.channel === channel))
      return [channel, {
        snr: channelRows.filter((item) => item && !item.failures.snr).length / total,
        template: channelRows.filter((item) => item && !item.failures.template).length / total,
        signal: channelRows.filter((item) => item && !item.failures.signal).length / total,
        stable: channelRows.filter((item) => item && !item.failures.stable).length / total
      }]
    }))
    const failureCounts = {
      snr: rows.filter((record) => record.failures.snr).length,
      template: rows.filter((record) => record.failures.template).length,
      signal: rows.filter((record) => record.failures.signal).length,
      stable: rows.filter((record) => record.failures.stable).length,
      multi: rows.filter((record) => record.failureCount > 1).length
    }
    const channelStatusCounts = {
      one: rows.filter((record) => record.insufficientChannelCount === 1).length,
      two: rows.filter((record) => record.insufficientChannelCount === 2).length
    }
    return {
      user_id: userId,
      name: user.name || user.canonical_name || user.display_id || userId,
      record_count: rows.length,
      high_quality_count: rows.filter((record) => record.qualityPass).length,
      acceptable_quality_count: rows.filter((record) => record.qualityAcceptable).length,
      rates,
      channelRates,
      failureCounts,
      channelStatusCounts,
      main_failure: mainFailureLabel(failureCounts),
      records: rows
    }
  }).sort((left, right) => right.rates.overall - left.rates.overall)
}

function mainFailureLabel(counts) {
  const labels = { snr: '周期 SNR 不足', template: '模板稳定性不足', signal: '信号质量不足', stable: '稳定片段不足', multi: '多项同时未通过' }
  const entries = Object.entries(counts).filter(([key]) => key !== 'multi').sort((a, b) => b[1] - a[1])
  return entries[0]?.[1] ? labels[entries[0][0]] : '无明显瓶颈'
}

function buildOverallPulseQuality(records, patients) {
  const total = records.length || 0
  const failureCounts = {
    snr: records.filter((record) => record.failures.snr).length,
    template: records.filter((record) => record.failures.template).length,
    signal: records.filter((record) => record.failures.signal).length,
    stable: records.filter((record) => record.failures.stable).length
  }
  const highQualityCount = records.filter((record) => record.qualityPass).length
  const acceptableQualityCount = records.filter((record) => record.qualityAcceptable).length
  const oneChannelCount = records.filter((record) => record.insufficientChannelCount === 1).length
  const twoChannelCount = records.filter((record) => record.insufficientChannelCount === 2).length
  const partialChannelCount = records.filter((record) => record.partialChannelMisalignment).length
  return {
    patientCount: patients.length,
    recordCount: total,
    highQualityCount,
    acceptableQualityCount,
    qualityPassRate: total ? highQualityCount / total : 0,
    avgPeriodicSnr: mean(records.map((record) => record.periodicSnr)),
    avgTemplateStability: mean(records.map((record) => record.templateStability)),
    avgSignalQuality: mean(records.map((record) => record.signalQuality)),
    avgStableSegmentRatio: mean(records.map((record) => record.stableSegmentRatio)),
    dimensionRates: {
      periodicSnr: total ? records.filter((record) => !record.failures.snr).length / total : 0,
      templateStability: total ? records.filter((record) => !record.failures.template).length / total : 0,
      signalQuality: total ? records.filter((record) => !record.failures.signal).length / total : 0,
      stableSegmentRatio: total ? records.filter((record) => !record.failures.stable).length / total : 0
    },
    oneChannelCount,
    twoChannelCount,
    partialChannelCount,
    partialChannelRate: total ? partialChannelCount / total : 0,
    mainFailureLabel: mainFailureLabel(failureCounts)
  }
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

function renderPulsePatientRankChart() {
  if (!pulsePatientRankChartRef.value) return
  const rows = [...pulsePatientQualityRows.value].sort((left, right) => left.rates.overall - right.rates.overall).slice(0, 20)
  pulsePatientRankChart = pulsePatientRankChart || echarts.init(pulsePatientRankChartRef.value)
  pulsePatientRankChart.setOption({
    title: { text: '患者脉诊质量通过率排名', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const row = rows[params[0].dataIndex]
        return [
          row.name,
          `患者 ID: ${row.user_id}`,
          `总记录数: ${row.record_count}`,
          `质量合格记录: ${row.high_quality_count}`,
          `质量通过率: ${formatPercent(row.rates.overall, 1)}%`,
          `SNR 通过率: ${formatPercent(row.rates.snr, 1)}%`,
          `模板通过率: ${formatPercent(row.rates.template, 1)}%`,
          `信号质量通过率: ${formatPercent(row.rates.signal, 1)}%`,
          `稳定片段通过率: ${formatPercent(row.rates.stable, 1)}%`,
          `主要失败维度: ${row.main_failure}`
        ].join('<br/>')
      }
    },
    grid: { left: 90, right: 28, top: 46, bottom: 28 },
    xAxis: { type: 'value', min: 0, max: 100, name: '%' },
    yAxis: { type: 'category', data: rows.map((row) => row.name), axisTick: { show: false }, axisLabel: { interval: 0 } },
    series: [{
      type: 'bar',
      data: rows.map((row) => Number((row.rates.overall * 100).toFixed(1))),
      label: { show: true, position: 'right', formatter: '{c}%' },
      itemStyle: {
        color: ({ value }) => (value >= 80 ? '#2f7d79' : value >= 50 ? '#d6a13d' : '#b05a4a'),
        borderRadius: [0, 4, 4, 0]
      }
    }]
  }, true)
}

function renderPulseQualityHeatmap() {
  if (!pulseQualityHeatmapRef.value) return
  const rows = pulsePatientQualityRows.value.slice(0, 24)
  const channelLabels = { Cun: '寸', Guan: '关', Chi: '尺' }
  const metricLabels = { snr: 'SNR', template: '模板', signal: '质量', stable: '片段' }
  const dimensions = ['Cun', 'Guan', 'Chi'].flatMap((channel) => (
    Object.keys(metricLabels).map((metric) => ({
      channel,
      metric,
      label: `${channelLabels[channel]} ${metricLabels[metric]}`
    }))
  )).concat([{ channel: null, metric: 'overall', label: '综合' }])
  const heatmapData = rows.flatMap((row, y) => dimensions.map((dimension, x) => [
    x,
    y,
    Number(((dimension.channel ? row.channelRates[dimension.channel][dimension.metric] : row.rates.overall) * 100).toFixed(1))
  ]))
  const values = heatmapData.map((item) => item[2])
  const dataMin = values.length ? Math.min(...values) : 0
  const dataMax = values.length ? Math.max(...values) : 100
  const visualMin = Math.max(0, dataMin - (dataMin === dataMax ? 5 : 0))
  const visualMax = Math.min(100, Math.max(visualMin + 1, dataMax + (dataMin === dataMax ? 5 : 0)))
  pulseQualityHeatmap = pulseQualityHeatmap || echarts.init(pulseQualityHeatmapRef.value)
  pulseQualityHeatmap.setOption({
    title: { text: '各患者脉诊质量维度热力图', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: {
      formatter: ({ data }) => {
        const row = rows[data[1]]
        const dim = dimensions[data[0]]
        return `${row.name}<br/>${dim.label}: ${data[2].toFixed(1)}%<br/>主要失败: ${row.main_failure}`
      }
    },
    grid: { left: 92, right: 18, top: 60, bottom: 74 },
    xAxis: { type: 'category', data: dimensions.map((item) => item.label), axisLabel: { rotate: 42, fontSize: 10 } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), axisTick: { show: false }, axisLabel: { interval: 0 } },
    visualMap: {
      min: visualMin,
      max: visualMax,
      orient: 'horizontal',
      left: 'center',
      bottom: 6,
      inRange: { color: ['#b05a4a', '#d6a13d', '#2f7d79'] }
    },
    series: [{
      type: 'heatmap',
      data: heatmapData,
      label: { show: true, formatter: ({ value }) => `${value[2].toFixed(0)}%` }
    }]
  }, true)
}

function renderPulseFailureStackChart() {
  if (!pulseFailureStackChartRef.value) return
  const rows = pulsePatientQualityRows.value.slice(0, 18)
  pulseFailureStackChart = pulseFailureStackChart || echarts.init(pulseFailureStackChartRef.value)
  pulseFailureStackChart.setOption({
    title: { text: '各患者脉诊质量构成', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    legend: { top: 0, right: 0, type: 'scroll' },
    grid: { left: 96, right: 20, top: 70, bottom: 34 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: rows.map((row) => row.name), axisTick: { show: false }, axisLabel: { interval: 0 } },
    series: [
      { key: 'passed', name: '质量合格', color: '#2f7d79' },
      { key: 'acceptable', name: '质量尚可', color: '#86a34c' },
      { key: 'one_channel', name: '1通道质量不足（未达尚可）', color: '#f59e0b' },
      { key: 'two_channel', name: '2通道质量不足', color: '#ea580c' },
      { key: 'snr', name: 'SNR 未通过', color: '#b05a4a' },
      { key: 'template', name: '模板稳定性未通过', color: '#d6a13d' },
      { key: 'signal', name: '信号质量未通过', color: '#7c3aed' },
      { key: 'stable', name: '稳定片段比例未通过', color: '#2563eb' },
      { key: 'multi', name: '多项同时未通过', color: '#6b7280' }
    ].map((item) => ({
      name: item.name,
      type: 'bar',
      stack: 'failure',
      data: rows.map((row) => {
        if (item.key === 'passed') return row.high_quality_count
        if (item.key === 'acceptable') return row.acceptable_quality_count
        if (item.key === 'one_channel') return Math.max(0, row.channelStatusCounts.one - row.acceptable_quality_count)
        if (item.key === 'two_channel') return row.channelStatusCounts.two
        return row.failureCounts[item.key]
      }),
      itemStyle: { color: item.color }
    }))
  }, true)
}

function pulseChannelPattern(record) {
  return PULSE_CHANNELS.map((channel) => (
    record.channelMetrics.find((item) => item.channel === channel)?.qualityPass ? '1' : '0'
  )).join('')
}

function pulseChannelFailureSummary(records) {
  const counts = { snr: 0, template: 0, signal: 0, stable: 0, missing: 0 }
  records.forEach((record) => {
    PULSE_CHANNELS.forEach((channel) => {
      const metrics = record.channelMetrics.find((item) => item.channel === channel)
      if (!metrics) {
        counts.missing += 1
        return
      }
      Object.keys(metrics.failures).forEach((key) => {
        if (metrics.failures[key]) counts[key] += 1
      })
    })
  })
  const labels = { snr: 'SNR 不足', template: '模板稳定不足', signal: '信号质量不足', stable: '稳定片段不足', missing: '缺少波形' }
  return Object.entries(counts)
    .filter(([, count]) => count > 0)
    .sort((left, right) => right[1] - left[1])
    .slice(0, 2)
    .map(([key, count]) => `${labels[key]} ${count}`)
    .join(' / ') || '无失败项'
}

function renderPulseChannelCombinationChart() {
  if (!pulseChannelCombinationChartRef.value) return
  const records = analyzedPulseRecords.value
  const patternDefinitions = [
    { key: '111', label: '寸关尺均合格', color: '#2f7d79' },
    { key: '011', label: '仅寸不足', color: '#e0b44f' },
    { key: '101', label: '仅关不足', color: '#d6a13d' },
    { key: '110', label: '仅尺不足', color: '#bf8731' },
    { key: '001', label: '寸关不足', color: '#f08c42' },
    { key: '010', label: '寸尺不足', color: '#ea6f2f' },
    { key: '100', label: '关尺不足', color: '#d85b27' },
    { key: '000', label: '寸关尺均不足', color: '#b05a4a' }
  ].map((pattern) => {
    const matches = records.filter((record) => pulseChannelPattern(record) === pattern.key)
    return {
      ...pattern,
      matches,
      count: matches.length,
      ratio: records.length ? matches.length / records.length : 0,
      failureSummary: pulseChannelFailureSummary(matches)
    }
  })
  const patternMap = new Map(patternDefinitions.map((pattern) => [pattern.key, pattern]))
  const groups = [
    { name: '质量合格', keys: ['111'], color: '#2f7d79' },
    { name: '1通道质量不足', keys: ['011', '101', '110'], color: '#d6a13d' },
    { name: '2通道质量不足', keys: ['001', '010', '100'], color: '#ea6f2f' },
    { name: '三通道质量不足', keys: ['000'], color: '#b05a4a' }
  ].map((group) => {
    const children = group.keys.map((key) => patternMap.get(key)).filter((pattern) => pattern.count > 0)
    const matches = group.keys.flatMap((key) => patternMap.get(key).matches)
    return {
      name: group.name,
      value: matches.length,
      ratio: records.length ? matches.length / records.length : 0,
      failureSummary: pulseChannelFailureSummary(matches),
      itemStyle: { color: group.color },
      children: children.map((pattern) => ({
        name: pattern.label,
        value: pattern.count,
        ratio: pattern.ratio,
        failureSummary: pattern.failureSummary,
        itemStyle: { color: pattern.color }
      }))
    }
  }).filter((group) => group.value > 0)
  pulseChannelCombinationChart = pulseChannelCombinationChart || echarts.init(pulseChannelCombinationChartRef.value)
  pulseChannelCombinationChart.setOption({
    title: { text: '寸关尺通道质量组合分布', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: {
      formatter: ({ data }) => `${data.name}<br/>记录数: ${data.value}<br/>占比: ${formatPercent(data.ratio, 1)}%<br/>常见失败: ${data.failureSummary}`
    },
    graphic: [{
      type: 'text',
      left: 'center',
      top: '49%',
      style: {
        text: `${records.length}\n总记录`,
        textAlign: 'center',
        fill: '#303133',
        fontSize: 12,
        fontWeight: 600,
        lineHeight: 18
      }
    }],
    series: [{
      type: 'sunburst',
      data: groups,
      center: ['50%', '55%'],
      radius: ['20%', '82%'],
      sort: null,
      nodeClick: false,
      minAngle: 2,
      label: { formatter: '{b}' },
      levels: [
        {},
        {
          r0: '20%',
          r: '50%',
          label: { rotate: 'tangential', fontSize: 11, minAngle: 8 }
        },
        {
          r0: '50%',
          r: '82%',
          label: { rotate: 'radial', fontSize: 10, minAngle: 10 }
        }
      ],
      emphasis: { focus: 'ancestor' }
    }]
  }, true)
}

function renderPulseTemplateSignalScatter() {
  if (!pulseTemplateSignalScatterRef.value) return
  const rows = analyzedPulseRecords.value
  const userIds = [...new Set(rows.map((row) => row.user_id || 'unknown'))]
  const userLabels = new Map(pulsePatientQualityRows.value.map((row) => [row.user_id, row.name]))
  const labelCounts = new Map()
  userIds.forEach((userId) => {
    const label = userLabels.get(userId) || userId
    labelCounts.set(label, (labelCounts.get(label) || 0) + 1)
  })
  const seriesLabels = new Map(userIds.map((userId) => {
    const label = userLabels.get(userId) || userId
    return [userId, labelCounts.get(label) > 1 ? `${label} (${userId})` : label]
  }))
  if (highlightedPulseUser && ![...seriesLabels.values()].includes(highlightedPulseUser)) {
    highlightedPulseUser = null
  }
  const colors = ['#2563eb', '#16a34a', '#dc2626', '#d97706', '#7c3aed', '#0891b2', '#be185d', '#475569']
  pulseTemplateSignalScatter = pulseTemplateSignalScatter || echarts.init(pulseTemplateSignalScatterRef.value)
  pulseTemplateSignalScatter.off('click')
  pulseTemplateSignalScatter.off('legendselectchanged')
  pulseTemplateSignalScatter.on('click', ({ data }) => {
    if (!data?.[5] || !data?.[6]) return
    router.push({ path: '/pulse-analysis', query: { view: 'detail', user_id: data[5], record_id: data[6] } })
  })
  pulseTemplateSignalScatter.on('legendselectchanged', ({ name }) => {
    highlightedPulseUser = highlightedPulseUser === name ? null : name
    renderPulseTemplateSignalScatter()
  })
  pulseTemplateSignalScatter.setOption({
    title: {
      text: '模板稳定性与信号质量关系图',
      subtext: highlightedPulseUser ? `当前患者：${highlightedPulseUser}` : '',
      left: 0,
      top: 0,
      textStyle: { fontSize: 14, fontWeight: 600 },
      subtextStyle: { fontSize: 11, color: '#667085' }
    },
    tooltip: {
      formatter: ({ data }) => `${data[4]}<br/>模板稳定: ${data[0].toFixed(1)}<br/>信号质量: ${data[1].toFixed(1)}<br/>SNR: ${data[2].toFixed(3)}<br/>状态: ${data[3]}<br/>点击查看记录`
    },
    legend: {
      top: 26,
      right: 0,
      type: 'scroll',
      width: '62%',
      selected: Object.fromEntries([...seriesLabels.values()].map((label) => [label, true]))
    },
    grid: { left: 48, right: 28, top: highlightedPulseUser ? 76 : 64, bottom: 42 },
    xAxis: { type: 'value', name: 'template_stability_score', min: 0, max: 100 },
    yAxis: { type: 'value', name: 'signal_quality_score', min: 0, max: 100 },
    series: userIds.map((userId, index) => ({
      name: seriesLabels.get(userId),
      type: 'scatter',
      data: rows
        .filter((row) => (row.user_id || 'unknown') === userId)
        .map((row) => [row.templateStability, row.signalQuality, row.periodicSnr, row.qualityState, userLabels.get(row.user_id) || row.user_name || row.user_id || row.row_id, row.user_id, row.row_id]),
      symbolSize: (data) => Math.max(5, Math.min(20, 5 + Number(data[2] || 0) * 12)),
      itemStyle: {
        color: colors[index % colors.length],
        opacity: !highlightedPulseUser || highlightedPulseUser === seriesLabels.get(userId) ? 0.8 : 0.12
      },
      markLine: index === 0 ? {
        symbol: 'none',
        data: [{ xAxis: QUALITY_THRESHOLDS.templateStability }, { yAxis: QUALITY_THRESHOLDS.signalQuality }],
        lineStyle: { type: 'dashed', color: '#7a858f' }
      } : undefined
    }))
  }, true)
}

function fitPatternName(pattern) {
  if (!pattern || pattern === 'none') return '未形成固定模式'
  return String(pattern)
    .replaceAll('cun', '寸')
    .replaceAll('guan', '关')
    .replaceAll('chi', '尺')
}

function renderPulseDeviceFitRiskChart() {
  if (!pulseDeviceFitRiskChartRef.value) return
  const rows = [...pulseDeviceFitRows.value].sort((left, right) => Number(left.patient_device_fit_risk_score) - Number(right.patient_device_fit_risk_score))
  pulseDeviceFitRiskChart = pulseDeviceFitRiskChart || echarts.init(pulseDeviceFitRiskChartRef.value)
  pulseDeviceFitRiskChart.setOption({
    title: { text: '设备适配风险患者排名', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      formatter: (params) => {
        const row = rows[params[0].dataIndex]
        return `${row.name}<br/>风险评分: ${Number(row.patient_device_fit_risk_score).toFixed(1)}<br/>长期异常模式: ${fitPatternName(row.persistent_channel_failure_pattern)}<br/>记录数: ${row.measurement_count}`
      }
    },
    grid: { left: 92, right: 30, top: 48, bottom: 28 },
    xAxis: { type: 'value', min: 0, max: 100, name: 'risk' },
    yAxis: { type: 'category', data: rows.map((row) => row.name), axisTick: { show: false }, axisLabel: { interval: 0 } },
    series: [{
      type: 'bar',
      data: rows.map((row) => Number(row.patient_device_fit_risk_score)),
      label: { show: true, position: 'right', formatter: ({ value }) => Number(value).toFixed(1) },
      itemStyle: {
        color: ({ value }) => (value >= 60 ? '#b05a4a' : value >= 35 ? '#d6a13d' : '#2f7d79'),
        borderRadius: [0, 4, 4, 0]
      }
    }]
  }, true)
}

function renderPulseAlignmentHeatmap() {
  if (!pulseAlignmentHeatmapRef.value) return
  const rows = pulseDeviceFitRows.value.slice(0, 24)
  const channels = [
    { key: 'cun_alignment_suspicion_rate', label: '寸' },
    { key: 'guan_alignment_suspicion_rate', label: '关' },
    { key: 'chi_alignment_suspicion_rate', label: '尺' }
  ]
  const data = rows.flatMap((row, y) => channels.map((channel, x) => [x, y, Number((Number(row[channel.key] || 0) * 100).toFixed(1))]))
  const values = data.map((item) => item[2])
  const maximum = values.length ? Math.max(...values) : 100
  pulseAlignmentHeatmap = pulseAlignmentHeatmap || echarts.init(pulseAlignmentHeatmapRef.value)
  pulseAlignmentHeatmap.setOption({
    title: { text: '患者 × 通道疑似未对准比例', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: {
      formatter: ({ data: item }) => {
        const row = rows[item[1]]
        return `${row.name}<br/>${channels[item[0]].label}: ${item[2].toFixed(1)}%<br/>长期异常模式: ${fitPatternName(row.persistent_channel_failure_pattern)}`
      }
    },
    grid: { left: 92, right: 18, top: 52, bottom: 58 },
    xAxis: { type: 'category', data: channels.map((channel) => channel.label), axisTick: { show: false } },
    yAxis: { type: 'category', data: rows.map((row) => row.name), axisTick: { show: false }, axisLabel: { interval: 0 } },
    visualMap: {
      min: 0,
      max: Math.max(1, maximum),
      orient: 'horizontal',
      left: 'center',
      bottom: 5,
      inRange: { color: ['#2f7d79', '#d6a13d', '#b05a4a'] }
    },
    series: [{
      type: 'heatmap',
      data,
      label: { show: true, formatter: ({ value }) => `${value[2].toFixed(0)}%` }
    }]
  }, true)
}

function renderPulseQualityCharts() {
  renderPulsePatientRankChart()
  renderPulseQualityHeatmap()
  renderPulseFailureStackChart()
  renderPulseChannelCombinationChart()
  renderPulseTemplateSignalScatter()
  renderPulseDeviceFitRiskChart()
  renderPulseAlignmentHeatmap()
}

function resizeCharts() {
  coverageChart?.resize()
  qualityChart?.resize()
  pulseValidityChart?.resize()
  pulseRiskChart?.resize()
  pulsePatientRankChart?.resize()
  pulseQualityHeatmap?.resize()
  pulseFailureStackChart?.resize()
  pulseChannelCombinationChart?.resize()
  pulseTemplateSignalScatter?.resize()
  pulseDeviceFitRiskChart?.resize()
  pulseAlignmentHeatmap?.resize()
}

onMounted(async () => {
  loading.value = true
  pulseLoading.value = true
  pulseQualityLoading.value = true
  try {
    const [summaryResult, pulseResult, usersResult, pulseRecordsResult, deviceFitResult] = await Promise.allSettled([
      api.summary(),
      api.pulsePhase1Summary(),
      api.getPulseUsers(),
      api.getPulseUserRecords(null),
      api.getPulseDeviceFitOverview()
    ])
    if (summaryResult.status === 'fulfilled') {
      summary.value = summaryResult.value
    }
    if (pulseResult.status === 'fulfilled') {
      pulseSummary.value = pulseResult.value
    }
    if (usersResult.status === 'fulfilled') {
      pulseUsers.value = Array.isArray(usersResult.value) ? usersResult.value : usersResult.value.items || []
    }
    if (pulseRecordsResult.status === 'fulfilled') {
      pulseRecords.value = Array.isArray(pulseRecordsResult.value) ? pulseRecordsResult.value : []
    }
    if (deviceFitResult.status === 'fulfilled') {
      pulseDeviceFitOverview.value = deviceFitResult.value
    }
  } finally {
    loading.value = false
    pulseLoading.value = false
    pulseQualityLoading.value = false
  }
  await nextTick()
  renderCoverageChart()
  renderQualityChart()
  renderPulseValidityChart()
  renderPulseRiskChart()
  renderPulseQualityCharts()
  window.addEventListener('resize', resizeCharts)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeCharts)
  coverageChart?.dispose()
  qualityChart?.dispose()
  pulseValidityChart?.dispose()
  pulseRiskChart?.dispose()
  pulsePatientRankChart?.dispose()
  pulseQualityHeatmap?.dispose()
  pulseFailureStackChart?.dispose()
  pulseChannelCombinationChart?.dispose()
  pulseTemplateSignalScatter?.dispose()
  pulseDeviceFitRiskChart?.dispose()
  pulseAlignmentHeatmap?.dispose()
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
.pulse-quality-panel {
  margin-bottom: 16px;
}
.pulse-quality-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin-bottom: 14px;
}
.pulse-quality-card {
  background: #f7faf9;
  border: 1px solid #e2ecea;
  border-radius: 6px;
  min-width: 0;
  padding: 10px 12px;
}
.pulse-quality-value {
  color: #1f4f4c;
  display: block;
  font-size: 22px;
  font-weight: 700;
  line-height: 1.1;
  overflow-wrap: anywhere;
}
.pulse-quality-label {
  color: #303133;
  display: block;
  font-size: 12px;
  margin-top: 7px;
}
.pulse-quality-note {
  color: #7a858f;
  display: block;
  font-size: 11px;
  margin-top: 5px;
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
.pulse-quality-chart {
  height: 400px;
}
.pulse-fit-alert {
  margin-top: 12px;
}
.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
@media (max-width: 768px) {
  .pulse-quality-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .pulse-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
