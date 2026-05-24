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
                <span class="patient-meta">
                  <span class="patient-id">{{ patient.user_id }}</span>
                  <el-tag size="small" :type="patientDataStatusType(patient)">{{ patient.data_status }}</el-tag>
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

              <div v-if="patientSummaryLoading || selectedPatientRecords.length" class="patient-visualization-panel">
                <div class="visualization-header">
                  <div>
                    <strong>单用户脉诊在线分析</strong>
                    <span v-if="patientPulseSummary?.selected_measurement_start_time">
                      示例记录 {{ patientPulseSummary.selected_measurement_start_time }}
                    </span>
                  </div>
                  <el-tag v-if="patientPulseSummary?.patient_periodic_rows !== undefined" size="small" type="success">
                    周期通道 {{ patientPulseSummary.patient_periodic_rows }}
                  </el-tag>
                </div>
                <el-skeleton v-if="patientSummaryLoading" animated :rows="5" />
                <template v-else>
                  <div ref="patientOnlineAnalysisChartRef" class="patient-online-analysis-chart"></div>
                  <div class="visualization-meta">
                    <span>{{ selectedPatientRecords.length }} 条记录</span>
                    <span>{{ selectedPatientRecords.reduce((sum, record) => sum + (record.template_metrics?.length || 0), 0) }} 条通道样本</span>
                    <span>平均 SNR {{ formatNumber(selectedPatient?.avg_periodic_snr ?? patientPulseSummary?.patient_avg_periodic_snr, 3) }}</span>
                    <span>模式稳定 {{ formatNumber(patientPulseSummary?.pattern_summary?.pattern_stability_score ?? averageTemplateStability(selectedPatientRecords), 1) }}</span>
                    <span v-if="patientPulseSummary?.pattern_summary?.best_segment_duration">
                      推荐片段 {{ formatNumber(patientPulseSummary.pattern_summary.best_segment_start_time, 1) }}s-{{ formatNumber(patientPulseSummary.pattern_summary.best_segment_end_time, 1) }}s
                    </span>
                  </div>
                </template>
              </div>

              <div class="patient-visualization-panel" v-loading="patientBaselineLoading">
                <div class="visualization-header">
                  <div>
                    <strong>个人脉波基线模板</strong>
                    <span>仅纳入质量可用且无长期未对准风险的通道记录</span>
                  </div>
                  <el-tag size="small" :type="patientBaselineAvailableChannels.length ? 'success' : 'warning'">
                    可用 {{ patientBaselineAvailableChannels.length }} / 3 通道
                  </el-tag>
                </div>
                <el-alert
                  v-if="patientPersonalBaseline?.interpretation_note"
                  :title="patientPersonalBaseline.interpretation_note"
                  type="info"
                  :closable="false"
                  show-icon
                  class="baseline-note"
                />
                <div v-if="patientBaselineAvailableChannels.length" ref="patientBaselineChartRef" class="patient-baseline-chart"></div>
                <el-empty v-else-if="!patientBaselineLoading" description="当前患者尚无满足条件的个人基线通道" :image-size="72" />
                <el-table v-if="patientBaselineChannels.length" :data="patientBaselineChannels" size="small" class="baseline-status-table">
                  <el-table-column label="通道" width="70">
                    <template #default="{ row }">{{ baselineChannelName(row.standard_channel_name) }}</template>
                  </el-table-column>
                  <el-table-column label="状态" min-width="130">
                    <template #default="{ row }">
                      <el-tag size="small" :type="baselineStatusType(row.baseline_status)">{{ baselineStatusName(row.baseline_status) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="eligible_record_count" label="入选样本" width="92" />
                  <el-table-column label="周期 SNR 正常范围" min-width="158">
                    <template #default="{ row }">{{ baselineRangeLabel(row, 'periodic_snr') }}</template>
                  </el-table-column>
                </el-table>
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
                <el-table-column label="时段" width="70">
                  <template #default="{ row }">{{ displaySlot(row.slot) }}</template>
                </el-table-column>
                <el-table-column prop="source_vendor" label="来源" width="96">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.source_vendor === 'zhongke' ? 'primary' : 'success'">
                      {{ sourceName(row.source_vendor) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="pulse_type" label="脉象" min-width="120" show-overflow-tooltip />
                <el-table-column prop="pulse_rate" label="脉率" width="82" />
                <el-table-column prop="template_stability_score" label="模板稳定" width="96">
                  <template #default="{ row }">{{ formatNumber(recordQualityScore(row), 1) }}</template>
                </el-table-column>
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
                  <el-option label="质量合格" value="valid" />
                  <el-option label="质量尚可" value="acceptable" />
                  <el-option label="质量不足" value="invalid" />
                </el-select>
              </div>
            </template>
            <div class="record-filter-grid">
              <el-select v-model="recordSlotFilter" size="small" placeholder="时段">
                <el-option label="全部时段" value="all" />
                <el-option label="早" value="早" />
                <el-option label="中" value="中" />
                <el-option label="晚" value="晚" />
              </el-select>
              <el-select v-model="recordDeviceFilter" size="small" placeholder="设备">
                <el-option label="全部设备" value="all" />
                <el-option v-for="device in selectedPatientDevices" :key="device" :label="device" :value="device" />
              </el-select>
              <el-select v-model="recordEventFilter" size="small" placeholder="位移">
                <el-option label="全部位移" value="all" />
                <el-option label="存在位移事件" value="has_event" />
                <el-option label="无位移事件" value="no_event" />
                <el-option label="疑似未对准" value="alignment" />
              </el-select>
            </div>
            <div class="record-list">
              <button
                v-for="record in pagedPatientRecords"
                :key="record.row_key"
                type="button"
                class="record-row"
                :class="{ active: record.row_key === selectedRecord?.row_key }"
                @click="selectRecord(record)"
              >
                <span class="record-date">{{ record.visit_date || '-' }} {{ record.visit_time || '' }}</span>
                <span class="record-meta">
                  <span class="record-id">{{ recordRecordId(record) }}</span>
                  <el-tag size="small" :type="record.source_vendor === 'zhongke' ? 'primary' : 'success'">
                    {{ sourceName(record.source_vendor) }}
                  </el-tag>
                  <el-tag v-if="displaySlot(record.slot) !== '-'" size="small">{{ displaySlot(record.slot) }}</el-tag>
                  <el-tag size="small" :type="recordValidityType(record)">{{ recordValidityName(record) }}</el-tag>
                  <el-tag
                    v-if="recordSourceReviewName(record)"
                    size="small"
                    :type="recordSourceReviewType(record)"
                  >
                    {{ recordSourceReviewName(record) }}
                  </el-tag>
                  <el-tag
                    v-if="recordResearchIssueName(record)"
                    size="small"
                    type="danger"
                  >
                    {{ recordResearchIssueName(record) }}
                  </el-tag>
                  <el-tag
                    v-if="recordQualityAcceptable(record) && recordInsufficientChannelCount(record) > 0"
                    size="small"
                    type="warning"
                  >
                    {{ recordInsufficientChannelCount(record) }}通道质量不足
                  </el-tag>
                </span>
                <span class="record-values">
                  SNR {{ formatNumber(recordOverallMetric(record, 'periodicSnr'), 2) }} · 模板 {{ formatNumber(recordQualityScore(record), 1) }} · 事件 {{ recordDisplacementEvents(record).length }}
                </span>
                <span class="record-values">
                  device {{ recordDeviceId(record) }} · 质量 {{ formatNumber(recordSignalQualityScore(record), 1) }} · {{ recordAlignmentFlag(record) ? '疑似未对准' : '对准风险低' }}
                </span>
                <span class="record-reasons">
                  {{ recordQualityReasonText(record) }}
                </span>
              </button>
            </div>
            <el-pagination
              v-model:current-page="recordPage"
              :page-size="recordPageSize"
              :total="filteredPatientRecords.length"
              small
              layout="prev, pager, next"
              class="record-pagination"
            />
          </el-card>
        </el-col>

        <el-col :xs="24" :lg="16">
          <el-card shadow="never" class="panel-card">
            <template #header>
              <div class="panel-header">
                <span>记录波形与分析</span>
                <div class="header-actions">
                  <el-switch
                    v-model="phaseAlignmentEnabled"
                    size="small"
                    :disabled="!selectedRecord?.template_metrics?.length"
                    active-text="模板对齐相位"
                    inactive-text="原相位"
                  />
                  <span class="table-note">{{ selectedRecordTitle }}</span>
                </div>
              </div>
            </template>
            <el-empty v-if="!selectedRecord" description="请选择左侧脉诊记录" :image-size="96" />
            <template v-else>
              <div class="record-summary-grid">
                <div v-for="item in selectedRecordSummaryCards" :key="item.label" class="record-summary-item">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </div>
              </div>

              <el-alert
                v-if="selectedRecordAlignmentWarning"
                type="warning"
                show-icon
                :closable="false"
                :title="selectedRecordAlignmentWarning"
                class="alignment-warning"
              />

              <section class="period-consistency-panel" v-loading="selectedRecordPeriodLoading">
                <div class="subpanel-header">
                  <strong>原始波形 PulseNumbers 周期一致性</strong>
                  <el-tag v-if="selectedRecordPeriodAnalysis?.available" size="small" type="info">
                    {{ selectedRecordPeriodAnalysis.period_selection_method }} · 仅周期对齐
                  </el-tag>
                </div>
                <el-alert
                  v-if="selectedRecordPeriodWarning"
                  type="warning"
                  show-icon
                  :closable="false"
                  :title="selectedRecordPeriodWarning"
                  class="alignment-warning"
                />
                <el-empty
                  v-if="!selectedRecordPeriodLoading && !selectedRecordPeriodAnalysis?.available"
                  description="该记录暂无原始波形周期分析结果"
                  :image-size="56"
                />
                <el-table v-else-if="selectedRecordPeriodAnalysis?.available" :data="selectedRecordPeriodRows" size="small" class="period-consistency-table">
                  <el-table-column prop="channel_label" label="通道" width="58" />
                  <el-table-column label="PulseNumbers 周期" width="128">
                    <template #default="{ row }">{{ formatNumber(row.expected_period_seconds, 3) }}s</template>
                  </el-table-column>
                  <el-table-column label="周期对齐模板" width="126">
                    <template #default="{ row }">{{ formatNumber(row.selected_period_seconds, 3) }}s</template>
                  </el-table-column>
                  <el-table-column label="一致性" width="88">
                    <template #default="{ row }">{{ formatNumber(row.pulse_rate_period_consistency * 100, 1) }}%</template>
                  </el-table-column>
                  <el-table-column label="半周期候选" width="112">
                    <template #default="{ row }">{{ candidatePeriodLabel(row.half_period_candidate) }}</template>
                  </el-table-column>
                  <el-table-column label="倍周期候选" width="112">
                    <template #default="{ row }">{{ candidatePeriodLabel(row.double_period_candidate) }}</template>
                  </el-table-column>
                  <el-table-column label="形态主导模式" min-width="154">
                    <template #default="{ row }">
                      <el-tag :type="periodConsistencyTagType(row)" size="small">{{ periodConsistencyLabel(row) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="对齐/形态相关性" width="132">
                    <template #default="{ row }">
                      {{ formatNumber(row.selected_template_coherence, 3) }} / {{ formatNumber(row.morphology_dominant_template?.coherence, 3) }}
                    </template>
                  </el-table-column>
                </el-table>
              </section>

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
                    <el-descriptions-item label="有效性">{{ recordValidityName(selectedRecord) }}</el-descriptions-item>
                    <el-descriptions-item label="device_id">{{ recordDeviceId(selectedRecord) }}</el-descriptions-item>
                  </el-descriptions>
                </el-col>
                <el-col :xs="24" :lg="13">
                  <div ref="recordFeatureChartRef" class="chart feature-chart"></div>
                </el-col>
              </el-row>

              <el-table :data="selectedRecordEvents" size="small" class="event-table" empty-text="未检测到疑似位移事件">
                <el-table-column prop="event_id" label="事件" width="70" />
                <el-table-column prop="start_time" label="开始" width="80" />
                <el-table-column prop="end_time" label="结束" width="80" />
                <el-table-column prop="duration" label="持续" width="80" />
                <el-table-column prop="affected_channels" label="通道" width="110" />
                <el-table-column prop="event_type" label="类型" min-width="150" />
                <el-table-column prop="severity" label="严重度" width="90" />
                <el-table-column prop="confidence" label="置信度" width="90" />
                <el-table-column prop="description" label="说明" min-width="260" show-overflow-tooltip />
              </el-table>

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
import { useRoute, useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { api } from '../services/api'

const router = useRouter()
const route = useRoute()
const viewMode = ref('patients')
const loading = ref(false)
const users = ref([])
const pulseRecords = ref([])
const patientPulseSummary = ref(null)
const patientSummaryLoading = ref(false)
const patientPersonalBaseline = ref(null)
const patientBaselineLoading = ref(false)
const selectedRecordPeriodAnalysis = ref(null)
const selectedRecordPeriodLoading = ref(false)
const selectedUserId = ref('')
const selectedRecord = ref(null)
const patientKeyword = ref('')
const patientPage = ref(1)
const patientPageSize = 12
const recordFilter = ref('all')
const recordSlotFilter = ref('all')
const recordDeviceFilter = ref('all')
const recordEventFilter = ref('all')
const recordPage = ref(1)
const recordPageSize = 12
// Keep record labels aligned with the overall-cohort thresholds used on the dashboard.
const QUALITY_THRESHOLDS = {
  periodicSnr: 0.4055209903773839,
  templateStability: 28.09370144534219,
  signalQuality: 33.52063258926944,
  stableSegmentRatio: 0.5
}
const QUALITY_ACCEPTABLE_MAX_INSUFFICIENT_CHANNELS = 1
const PHASE_ALIGNMENT_STORAGE_KEY = 'pulse-waveform-template-phase-alignment'
const phaseAlignmentEnabled = ref(loadPhaseAlignmentSetting())

const patientTrendChartRef = ref(null)
const patientSlotChartRef = ref(null)
const patientOnlineAnalysisChartRef = ref(null)
const patientBaselineChartRef = ref(null)
const waveformChartRef = ref(null)
const recordFeatureChartRef = ref(null)
const signalQualityChartRef = ref(null)
let patientTrendChart
let patientSlotChart
let patientOnlineAnalysisChart
let patientBaselineChart
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
  return pulseRecords.value.map((record, index) => {
    const templateStability = recordTemplateStability(record)
    return {
      ...record,
      row_key: `${record.visit_id || 'visit'}-${record.source_asset_id || index}`,
      pulse_rate: toNumber(record.pulse_rate),
      force: toNumber(record.force),
      tension: toNumber(record.tension),
      fluency: toNumber(record.fluency),
      amplitude: toNumber(record.amplitude),
      stability_score: toNumber(record.stability_score),
      template_stability_score: templateStability.score,
      template_stability_label: templateStability.label,
      template_artifact_score: templateStability.artifactScore,
      template_metrics: templateStability.channels,
      displacement_event_count: templateStability.events.length,
      alignment_suspicion_flag: templateStability.alignmentSuspicion,
      overall_periodic_snr: templateStability.periodicSnr,
      overall_signal_quality_score: templateStability.signalQualityScore,
      stable_segment_ratio: templateStability.stableSegmentRatio,
      insufficient_channel_count: recordInsufficientChannelCount({ template_metrics: templateStability.channels }),
      record_id: recordRecordId(record),
      device_id: recordDeviceId(record)
    }
  })
})

const patientSummaries = computed(() => {
  return users.value.map((user) => {
    const records = normalizedRecords.value.filter((record) => record.user_id === user.user_id)
    const validRecords = records.filter((record) => recordResearchUsable(record))
    const last = [...records].sort(recordTimeCompare).at(-1)
    return {
      ...user,
      pulse_count: records.length,
      valid_pulse_count: validRecords.length,
      last_pulse_date: last?.visit_date || null,
      avg_pulse_rate: average(records, 'pulse_rate'),
      avg_force: average(records, 'force'),
      avg_stability: averageTemplateStability(records),
      avg_periodic_snr: average(records, 'overall_periodic_snr'),
      misalignment_ratio: records.length ? records.filter((record) => recordAlignmentFlag(record)).length / records.length : 0,
      partial_channel_misalignment_ratio: records.length ? records.filter((record) => {
        const count = recordInsufficientChannelCount(record)
        return count > 0 && count < 3
      }).length / records.length : 0,
      displacement_event_count: records.reduce((sum, record) => sum + recordDisplacementEvents(record).length, 0),
      data_status: patientDataStatus(records)
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

const selectedPatientDevices = computed(() => {
  return [...new Set(selectedPatientRecords.value.map((record) => recordDeviceId(record)).filter(Boolean))].sort()
})

const selectedPatientRecentRecords = computed(() => [...selectedPatientRecords.value].reverse().slice(0, 8))

const filteredPatientRecords = computed(() => {
  return selectedPatientRecords.value.filter((record) => {
    const qualified = recordQualityQualified(record)
    const acceptable = recordQualityAcceptable(record)
    if (recordSlotFilter.value !== 'all' && record.slot !== recordSlotFilter.value) return false
    if (recordDeviceFilter.value !== 'all' && recordDeviceId(record) !== recordDeviceFilter.value) return false
    if (recordEventFilter.value === 'has_event' && recordDisplacementEvents(record).length === 0) return false
    if (recordEventFilter.value === 'no_event' && recordDisplacementEvents(record).length > 0) return false
    if (recordEventFilter.value === 'alignment' && !recordAlignmentFlag(record)) return false
    if (recordFilter.value === 'valid') return qualified
    if (recordFilter.value === 'acceptable') return acceptable
    if (recordFilter.value === 'invalid') return !qualified && !acceptable
    return true
  }).reverse()
})

const pagedPatientRecords = computed(() => {
  const start = (recordPage.value - 1) * recordPageSize
  return filteredPatientRecords.value.slice(start, start + recordPageSize)
})

const patientMetricCards = computed(() => {
  const records = selectedPatientRecords.value
  const validCount = records.filter((record) => recordResearchUsable(record)).length
  const sourceReviewCount = records.filter((record) => recordSourceReviewName(record)).length
  return [
    { label: '脉诊记录', value: records.length, note: `${sourceReviewCount} 条需来源复核` },
    { label: '有效记录', value: validCount, note: '波形质量合格或尚可' },
    { label: '平均脉率', value: `${formatNumber(average(records, 'pulse_rate'), 0)} bpm`, note: '当前患者全部脉诊' },
    { label: '平均脉力', value: formatNumber(average(records, 'force'), 1), note: '玉生堂/中科标准字段' },
    { label: '纵向周期 SNR', value: formatNumber(selectedPatient.value?.avg_periodic_snr ?? patientPulseSummary.value?.patient_avg_periodic_snr, 3), note: '寸关尺通道均值' },
    { label: '模板稳定性', value: formatNumber(averageTemplateStability(records), 1), note: '波形模板质量基准' },
    { label: '疑似未对准', value: `${formatNumber((selectedPatient.value?.misalignment_ratio || 0) * 100, 1)}%`, note: '低能量/低周期/高偏移' },
    { label: '局部通道未对准', value: `${formatNumber((selectedPatient.value?.partial_channel_misalignment_ratio || 0) * 100, 1)}%`, note: '1-2 通道质量不足' },
    { label: '个人基线通道', value: `${patientPersonalBaseline.value?.baseline_available_count || 0} / 3`, note: '排除长期未对准通道' },
    { label: '位移事件', value: selectedPatient.value?.displacement_event_count || 0, note: '窗口级疑似事件' }
  ]
})

const patientBaselineChannels = computed(() => patientPersonalBaseline.value?.channels || [])
const patientBaselineAvailableChannels = computed(() => patientBaselineChannels.value.filter((row) => row.baseline_status === 'available'))

function baselineChannelName(channel) {
  return { cun: '寸', guan: '关', chi: '尺' }[channel] || channel
}

function baselineStatusName(status) {
  return {
    available: '可用基线',
    excluded_persistent_alignment: '长期未对准排除',
    insufficient_eligible_records: '高质量样本不足'
  }[status] || status
}

function baselineStatusType(status) {
  return { available: 'success', excluded_persistent_alignment: 'danger', insufficient_eligible_records: 'warning' }[status] || 'info'
}

function baselineRangeLabel(channel, featureName) {
  const row = (channel.normal_ranges || []).find((item) => item.feature_name === featureName)
  if (!row) return '-'
  return `${formatNumber(row.normal_lower, 3)} - ${formatNumber(row.normal_upper, 3)}`
}

const selectedRecordTitle = computed(() => {
  if (!selectedRecord.value) return '-'
  return `${selectedRecord.value.visit_date || '-'} ${selectedRecord.value.visit_time || ''} · ${sourceName(selectedRecord.value.source_vendor)}`
})

const selectedRecordEvents = computed(() => recordDisplacementEvents(selectedRecord.value))

const selectedRecordSummaryCards = computed(() => {
  const record = selectedRecord.value
  if (!record) return []
  return [
    { label: 'record_id', value: recordRecordId(record) },
    { label: '采集时间', value: `${record.visit_date || '-'} ${record.visit_time || ''}`.trim() },
    { label: 'device_id', value: recordDeviceId(record) },
    { label: '记录时长', value: recordDurationLabel(record) },
    { label: '周期 SNR', value: formatNumber(recordOverallMetric(record, 'periodicSnr'), 3) },
    { label: '模板稳定', value: formatNumber(recordQualityScore(record), 1) },
    { label: '信号质量', value: formatNumber(recordSignalQualityScore(record), 1) },
    { label: '稳定片段', value: `${formatNumber(recordStableSegmentRatio(record) * 100, 1)}%` },
    { label: '有效性', value: recordValidityName(record) },
    { label: '位移事件', value: recordDisplacementEvents(record).length },
    { label: '疑似未对准', value: recordAlignmentFlag(record) ? '是' : '否' },
    { label: '质量不足通道', value: recordInsufficientChannelCount(record) ? `${recordInsufficientChannelCount(record)} 个` : '无' }
  ]
})

const selectedRecordAlignmentWarning = computed(() => {
  const record = selectedRecord.value
  if (!record?.template_metrics?.length) return ''
  const risky = record.template_metrics.find((channel) => {
    const stable = Number(channel.templateStability) >= 45
    const lowSnr = Number(channel.periodicSnr) < 0.08
    const lowEnergy = Number(channel.pulseEnergy) < 0.0001
    const highAlignment = Number(channel.alignmentSuspicionScore) >= 60
    return stable && (lowSnr || lowEnergy || highAlignment)
  })
  if (!risky) return ''
  return `${risky.channel} 通道波形偏移较小，但周期化脉搏信噪比和脉搏能量较低，疑似未对准或接触不足，不应判定为高质量稳定模板。`
})

const selectedRecordPeriodRows = computed(() => {
  const expectedPeriod = selectedRecordPeriodAnalysis.value?.expected_period_seconds
  return (selectedRecordPeriodAnalysis.value?.channels || []).map((row) => ({
    ...row,
    expected_period_seconds: expectedPeriod,
    channel_label: { cun: '寸', guan: '关', chi: '尺' }[row.standard_channel_name] || row.standard_channel_name
  }))
})

const selectedRecordPeriodWarning = computed(() => {
  const dominant = selectedRecordPeriodRows.value.filter((row) => row.double_period_dominant_flag)
  if (!dominant.length) return ''
  const names = dominant.map((row) => row.channel_label).join('、')
  return `${names}通道检测到倍周期形态主导。PulseNumbers 对齐模板仅用于周期校验，形态模板保留倍周期证据；不得仅按对齐周期判定为高质量。`
})

const selectedRecordStabilityRows = computed(() => {
  const rows = []
  const record = selectedRecord.value
  if (!record?.waveform_preview) return rows
  for (const channel of record.waveform_preview) {
    const channelName = standardPulseChannel(channel.name)
    if (!channelName || !Array.isArray(channel.points)) continue
    const analysis = waveformTemplateAnalysis(channel.points)
    for (const item of analysis.windows) {
      rows.push({
        record,
        channel: channelName,
        ...item
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

function averageTemplateStability(records) {
  const values = records.map((record) => recordQualityScore(record)).filter((value) => Number.isFinite(value))
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
}

function recordQualityScore(record) {
  const templateScore = Number(record?.template_stability_score)
  if (Number.isFinite(templateScore)) return templateScore
  const fallback = Number(record?.stability_score)
  return Number.isFinite(fallback) ? fallback : null
}

function formatNumber(value, digits = 1) {
  const number = Number(value)
  return Number.isFinite(number) ? number.toFixed(digits) : '-'
}

function candidatePeriodLabel(candidate) {
  if (!candidate) return '-'
  return `${formatNumber(candidate.period_seconds, 3)}s / ${formatNumber(candidate.coherence, 3)}`
}

function periodConsistencyLabel(row) {
  return {
    double_period_dominant: '倍周期主导',
    half_period_dominant: '半周期主导',
    pulse_rate_consistent: '周期一致',
    pulse_rate_locked_low_coherence: '对齐但相关性低'
  }[row.pulse_rate_period_consistency_label] || row.pulse_rate_period_consistency_label || '-'
}

function periodConsistencyTagType(row) {
  if (row.double_period_dominant_flag || row.half_period_dominant_flag) return 'warning'
  return row.pulse_rate_period_consistency_label === 'pulse_rate_consistent' ? 'success' : 'info'
}

function percentScore(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number * 100 : null
}

function formatDateTimeLabel(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

function sourceName(value) {
  return { zhongke: '中科', yushengtang: '玉生堂' }[value] || value || '-'
}

function displaySlot(value) {
  return value === '重复' ? '-' : (value || '-')
}

function qualityName(value) {
  return { valid: '有效', incomplete: '不完整', suspicious: '疑似异常', duplicate: '-' }[value] || value || '-'
}

function patientDataStatus(records) {
  if (!records.length) return '无脉诊'
  const waveformCount = records.filter((record) => Array.isArray(record.waveform_preview) && record.waveform_preview.length).length
  if (waveformCount === records.length) return '波形完整'
  if (waveformCount > 0) return '部分波形'
  return '仅特征'
}

function patientDataStatusType(patient) {
  if (patient.data_status === '波形完整') return 'success'
  if (patient.data_status === '部分波形') return 'warning'
  return 'info'
}

function recordRecordId(record) {
  return record?.record_id || record?.measurement_id || record?.source_measurement_id || record?.source_asset_id || record?.visit_id || record?.row_key || '-'
}

function recordDeviceId(record) {
  return record?.device_id || record?.source_device_id || record?.device_model || record?.source_vendor || '-'
}

function recordDurationSeconds(record) {
  const duration = Number(record?.duration_seconds ?? record?.duration)
  if (Number.isFinite(duration) && duration > 0) return duration
  const sampleCount = Number(record?.sample_count)
  const samplingRate = Number(record?.sampling_rate)
  if (sampleCount > 0 && samplingRate > 0) return sampleCount / samplingRate
  return null
}

function recordDurationLabel(record) {
  const duration = recordDurationSeconds(record)
  return duration ? `${formatNumber(duration, 1)}s` : '-'
}

function recordOverallMetric(record, key) {
  const values = (record?.template_metrics || []).map((channel) => Number(channel[key])).filter((value) => Number.isFinite(value))
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
}

function recordDisplacementEvents(record) {
  if (!record) return []
  if (Array.isArray(record.displacement_events)) return record.displacement_events
  const events = buildDisplacementEvents(record.template_metrics || [], recordDurationSeconds(record))
  record.displacement_events = events
  return events
}

function recordAlignmentFlag(record) {
  if (!record) return false
  if (record.alignment_suspicion_flag !== undefined) return Boolean(record.alignment_suspicion_flag)
  return (record.template_metrics || []).some((channel) => Number(channel.alignmentSuspicionScore) >= 60)
}

function recordStableSegmentRatio(record) {
  const values = (record?.template_metrics || []).flatMap((channel) => channel.windows || [])
  if (!values.length) return Number(record?.stable_segment_ratio) || 0
  const stable = values.filter((window) => (
    Number(window.periodicSnr) > QUALITY_THRESHOLDS.periodicSnr
    && Number(window.templateStability) > QUALITY_THRESHOLDS.templateStability
    && Number(window.artifactSeverityScore) < 0.7
  ))
  return stable.length / values.length
}

function recordSignalQualityScore(record) {
  const stability = Number(recordQualityScore(record)) || 0
  const snr = Number(recordOverallMetric(record, 'periodicSnr')) || 0
  const energy = Number(recordOverallMetric(record, 'pulseEnergy')) || 0
  const artifact = Number(record?.template_artifact_score)
  const artifactPenalty = Number.isFinite(artifact) ? artifact * 35 : 0
  return clampScore(stability * 0.55 + Math.min(snr, 1) * 25 + Math.min(energy * 5000, 20) - artifactPenalty)
}

function channelStableSegmentRatio(channel) {
  const windows = channel?.windows || []
  if (!windows.length) return 0
  return windows.filter((window) => (
    Number(window.periodicSnr) > QUALITY_THRESHOLDS.periodicSnr
    && Number(window.templateStability) > QUALITY_THRESHOLDS.templateStability
    && Number(window.artifactSeverityScore) < 0.7
  )).length / windows.length
}

function channelSignalQualityScore(channel) {
  const stability = Number(channel?.templateStability) || 0
  const snr = Number(channel?.periodicSnr) || 0
  const energy = Number(channel?.pulseEnergy) || 0
  const artifact = Number(channel?.artifactSeverityScore) || 0
  return clampScore(stability * 0.55 + Math.min(snr, 1) * 25 + Math.min(energy * 5000, 20) - artifact * 35)
}

function channelQualityReasons(channel) {
  const reasons = []
  if (Number(channel?.periodicSnr) <= QUALITY_THRESHOLDS.periodicSnr) reasons.push('SNR')
  if (Number(channel?.templateStability) <= QUALITY_THRESHOLDS.templateStability) reasons.push('模板')
  if (channelSignalQualityScore(channel) <= QUALITY_THRESHOLDS.signalQuality) reasons.push('质量')
  if (channelStableSegmentRatio(channel) <= QUALITY_THRESHOLDS.stableSegmentRatio) reasons.push('片段')
  return reasons
}

function recordInsufficientChannels(record) {
  return (record?.template_metrics || [])
    .map((channel) => ({ channel: channel.channel, reasons: channelQualityReasons(channel) }))
    .filter((channel) => channel.reasons.length)
}

function recordInsufficientChannelCount(record) {
  return recordInsufficientChannels(record).length
}

function recordQualityMetrics(record) {
  return {
    periodicSnr: Number(recordOverallMetric(record, 'periodicSnr')) || 0,
    templateStability: Number(recordQualityScore(record)) || 0,
    signalQuality: Number(recordSignalQualityScore(record)) || 0,
    stableSegmentRatio: Number(recordStableSegmentRatio(record)) || 0
  }
}

function recordQualityReasons(record) {
  const metrics = recordQualityMetrics(record)
  const reasons = []
  if (metrics.periodicSnr <= QUALITY_THRESHOLDS.periodicSnr) reasons.push(`SNR≤${formatNumber(QUALITY_THRESHOLDS.periodicSnr, 3)}`)
  if (metrics.templateStability <= QUALITY_THRESHOLDS.templateStability) reasons.push(`模板≤${formatNumber(QUALITY_THRESHOLDS.templateStability, 1)}`)
  if (metrics.signalQuality <= QUALITY_THRESHOLDS.signalQuality) reasons.push(`质量≤${formatNumber(QUALITY_THRESHOLDS.signalQuality, 1)}`)
  if (metrics.stableSegmentRatio <= QUALITY_THRESHOLDS.stableSegmentRatio) reasons.push(`稳定片段≤${formatNumber(QUALITY_THRESHOLDS.stableSegmentRatio * 100, 1)}%`)
  return reasons
}

function recordQualityQualified(record) {
  return recordQualityReasons(record).length === 0 && recordInsufficientChannelCount(record) === 0
}

function recordQualityAcceptable(record) {
  const insufficientCount = recordInsufficientChannelCount(record)
  return recordQualityReasons(record).length === 0
    && insufficientCount > 0
    && insufficientCount <= QUALITY_ACCEPTABLE_MAX_INSUFFICIENT_CHANNELS
}

function recordResearchUsable(record) {
  return recordQualityQualified(record) || recordQualityAcceptable(record)
}

function recordSourceReviewName(record) {
  const status = record?.source_review_status || (record?.quality_status === 'suspicious' ? 'suspected_duplicate' : '')
  if (status === 'suspected_duplicate') return '疑似重复来源'
  if (status === 'incomplete_source') return '来源不完整'
  return ''
}

function recordSourceReviewType(record) {
  return record?.source_review_status === 'suspected_duplicate' || record?.quality_status === 'suspicious' ? 'warning' : 'info'
}

function recordResearchIssueName(record) {
  return record?.research_inclusion_status === 'insufficient_pulse_data' ? '脉诊载荷不足' : ''
}

function recordQualityReasonText(record) {
  const reasons = recordQualityReasons(record)
  const channelReasons = recordInsufficientChannels(record).map((channel) => `${channel.channel}[${channel.reasons.join('/')}]`)
  const sourceReasons = recordSourceReviewName(record) ? [`来源复核：${recordSourceReviewName(record)}`] : []
  const researchReasons = recordResearchIssueName(record) ? [`研究纳入：${recordResearchIssueName(record)}`] : []
  const allReasons = [...reasons, ...channelReasons, ...sourceReasons, ...researchReasons]
  if (recordQualityAcceptable(record)) {
    return `质量尚可：记录级4项达标；提示：${allReasons.join(' / ')}`
  }
  if (recordQualityQualified(record)) {
    return sourceReasons.length ? `波形质量合格；提示：${sourceReasons.join(' / ')}` : '原因：4项阈值及三通道均达标'
  }
  return allReasons.length ? `原因：${allReasons.join(' / ')}` : '原因：4项阈值及三通道均达标'
}

function recordValidityName(record) {
  if (recordQualityQualified(record)) return '质量合格'
  if (recordQualityAcceptable(record)) return '质量尚可'
  const insufficientCount = recordInsufficientChannelCount(record)
  if (insufficientCount === 1) return '1通道质量不足'
  if (insufficientCount === 2) return '2通道质量不足'
  if (insufficientCount >= 3) return '三通道质量不足'
  return '质量不足'
}

function recordValidityType(record) {
  if (recordQualityQualified(record)) return 'success'
  if (recordQualityAcceptable(record)) return 'warning'
  if (recordInsufficientChannelCount(record) > 0) return 'warning'
  return 'danger'
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
  patientOnlineAnalysisChart?.dispose()
  patientBaselineChart?.dispose()
  patientTrendChart = null
  patientSlotChart = null
  patientOnlineAnalysisChart = null
  patientBaselineChart = null
}

function disposeDetailCharts() {
  waveformChart?.dispose()
  recordFeatureChart?.dispose()
  signalQualityChart?.dispose()
  waveformChart = null
  recordFeatureChart = null
  signalQualityChart = null
}

async function fetchPatientPulseSummary() {
  const userId = selectedUserId.value
  if (!userId) {
    patientPulseSummary.value = null
    patientPersonalBaseline.value = null
    return
  }
  patientSummaryLoading.value = true
  patientBaselineLoading.value = true
  try {
    const [summaryResult, baselineResult] = await Promise.allSettled([
      api.getPulseUserSummary(userId),
      api.getPulsePersonalBaseline(userId)
    ])
    if (selectedUserId.value === userId) {
      patientPulseSummary.value = summaryResult.status === 'fulfilled' && summaryResult.value?.available ? summaryResult.value : null
      patientPersonalBaseline.value = baselineResult.status === 'fulfilled' && baselineResult.value?.available ? baselineResult.value : null
    }
  } catch (error) {
    if (selectedUserId.value === userId) {
      patientPulseSummary.value = null
      patientPersonalBaseline.value = null
    }
  } finally {
    if (selectedUserId.value === userId) {
      patientSummaryLoading.value = false
      patientBaselineLoading.value = false
    }
  }
  await nextTick()
  renderPatientOnlineAnalysisChart()
  renderPatientBaselineChart()
}

async function fetchSelectedRecordPeriodAnalysis() {
  const record = selectedRecord.value
  if (viewMode.value !== 'detail' || !record || !selectedUserId.value) {
    selectedRecordPeriodAnalysis.value = null
    return
  }
  const recordId = recordRecordId(record)
  selectedRecordPeriodLoading.value = true
  selectedRecordPeriodAnalysis.value = null
  try {
    const payload = await api.getPulsePeriodConsistency(selectedUserId.value, recordId)
    if (selectedRecord.value?.row_key === record.row_key) {
      selectedRecordPeriodAnalysis.value = payload?.available ? payload : null
    }
  } catch (error) {
    if (selectedRecord.value?.row_key === record.row_key) {
      selectedRecordPeriodAnalysis.value = null
    }
  } finally {
    if (selectedRecord.value?.row_key === record.row_key) {
      selectedRecordPeriodLoading.value = false
    }
  }
}

function selectPatient(userId) {
  selectedUserId.value = userId
  selectedRecord.value = selectedPatientRecords.value.at(-1) || null
  fetchPatientPulseSummary()
  nextTick(() => {
    renderPatientCharts()
    renderDetailCharts()
  })
}

function openPulseDetail() {
  disposeDetailCharts()
  viewMode.value = 'detail'
  recordPage.value = 1
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
  return ['早', '中', '晚'].map((slot) => {
    const items = records.filter((record) => record.slot === slot)
    return {
      slot,
      count: items.length,
      template_stability_score: averageTemplateStability(items),
      template_artifact_score: average(items, 'template_artifact_score')
    }
  })
}

function renderPatientCharts() {
  if (viewMode.value !== 'patients') return
  renderPatientTrendChart()
  renderPatientSlotChart()
  renderPatientOnlineAnalysisChart()
  renderPatientBaselineChart()
}

function renderPatientTrendChart() {
  patientTrendChart = ensureChart(patientTrendChart, patientTrendChartRef.value)
  if (!patientTrendChart) return
  const records = selectedPatientRecords.value
  patientTrendChart.setOption({
    title: { text: '质量阈值四指标趋势', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, right: 0 },
    grid: { left: 42, right: 48, top: 48, bottom: 36 },
    xAxis: { type: 'category', data: records.map((record) => `${record.visit_date || ''}\n${record.visit_time || ''}`) },
    yAxis: [
      { type: 'value', name: '分数/%', min: 0, max: 100 },
      { type: 'value', name: 'SNR', min: 0, max: 1 }
    ],
    series: [
      {
        name: '周期 SNR',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        data: records.map((record) => recordQualityMetrics(record).periodicSnr),
        symbolSize: 7,
        markLine: { symbol: 'none', data: [{ yAxis: QUALITY_THRESHOLDS.periodicSnr, name: 'SNR阈值' }] }
      },
      {
        name: '模板稳定',
        type: 'line',
        smooth: true,
        data: records.map((record) => recordQualityMetrics(record).templateStability),
        symbolSize: 7,
        markLine: { symbol: 'none', data: [{ yAxis: QUALITY_THRESHOLDS.templateStability, name: '模板阈值' }] }
      },
      {
        name: '信号质量',
        type: 'line',
        smooth: true,
        data: records.map((record) => recordQualityMetrics(record).signalQuality),
        symbolSize: 7,
        markLine: { symbol: 'none', data: [{ yAxis: QUALITY_THRESHOLDS.signalQuality, name: '质量阈值' }] }
      },
      {
        name: '稳定片段%',
        type: 'bar',
        data: records.map((record) => recordQualityMetrics(record).stableSegmentRatio * 100),
        itemStyle: { color: 'rgba(214, 161, 61, 0.42)', borderRadius: [4, 4, 0, 0] },
        markLine: { symbol: 'none', data: [{ yAxis: QUALITY_THRESHOLDS.stableSegmentRatio * 100, name: '片段阈值' }] }
      }
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
      { name: '模板稳定性', type: 'bar', data: rows.map((row) => row.template_stability_score), itemStyle: { color: '#2f7d79', borderRadius: [4, 4, 0, 0] } },
      { name: '漂移伪影', type: 'bar', data: rows.map((row) => percentScore(row.template_artifact_score)), itemStyle: { color: '#d6a13d', borderRadius: [4, 4, 0, 0] } }
    ]
  }, true)
}

function renderPatientOnlineAnalysisChart() {
  patientOnlineAnalysisChart = ensureChart(patientOnlineAnalysisChart, patientOnlineAnalysisChartRef.value)
  if (!patientOnlineAnalysisChart) return
  const records = selectedPatientRecords.value
  if (!records.length) {
    patientOnlineAnalysisChart.clear()
    return
  }
  const channels = ['Cun', 'Guan', 'Chi']
  const colors = { Cun: '#2563eb', Guan: '#16a34a', Chi: '#dc2626' }
  const templates = patientTypicalTemplates(records)
  const templateLength = Math.max(0, ...templates.map((row) => row.points.length))
  const channelRows = records.flatMap((record) => (record.template_metrics || []).map((channel) => ({ record, ...channel })))
  const slots = ['早', '中', '晚']
  patientOnlineAnalysisChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0, right: 0 },
    grid: [
      { left: 48, top: 48, width: '42%', height: 170 },
      { right: 24, top: 48, width: '42%', height: 170 },
      { left: 48, bottom: 44, width: '42%', height: 170 },
      { right: 24, bottom: 44, width: '42%', height: 170 }
    ],
    title: [
      { text: '个人典型脉波模板', left: 0, top: 12, textStyle: { fontSize: 13, fontWeight: 600 } },
      { text: '能量与偏移散点', left: '52%', top: 12, textStyle: { fontSize: 13, fontWeight: 600 } },
      { text: '模板稳定性统计', left: 0, top: '52%', textStyle: { fontSize: 13, fontWeight: 600 } },
      { text: '早中晚变化统计', left: '52%', top: '52%', textStyle: { fontSize: 13, fontWeight: 600 } }
    ],
    xAxis: [
      { type: 'category', gridIndex: 0, data: Array.from({ length: templateLength }, (_, index) => index + 1), axisLabel: { fontSize: 10 } },
      { type: 'value', gridIndex: 1, name: 'pulse_energy' },
      { type: 'category', gridIndex: 2, data: channels, axisTick: { show: false } },
      { type: 'category', gridIndex: 3, data: slots, axisTick: { show: false } }
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, name: 'template' },
      { type: 'value', gridIndex: 1, name: 'artifact', min: 0, max: 1 },
      { type: 'value', gridIndex: 2, name: 'score', min: 0, max: 100 },
      { type: 'value', gridIndex: 3, name: 'score', min: 0, max: 100 }
    ],
    series: [
      ...channels.map((channel) => ({
        name: `${channel} 模板`,
        type: 'line',
        smooth: true,
        xAxisIndex: 0,
        yAxisIndex: 0,
        showSymbol: false,
        data: templates.find((row) => row.channel === channel)?.points || [],
        itemStyle: { color: colors[channel] }
      })),
      ...channels.map((channel) => ({
        name: `${channel} 偏移`,
        type: 'scatter',
        xAxisIndex: 1,
        yAxisIndex: 1,
        symbolSize: 7,
        data: channelRows
          .filter((row) => row.channel === channel)
          .map((row) => [row.pulseEnergy, row.artifactSeverityScore]),
        itemStyle: { color: colors[channel], opacity: 0.72 }
      })),
      {
        name: '平均模板稳定',
        type: 'bar',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: channels.map((channel) => average(channelRows.filter((row) => row.channel === channel), 'templateStability')),
        itemStyle: { color: '#2f7d79', borderRadius: [4, 4, 0, 0] }
      },
      {
        name: '疑似未对准比例',
        type: 'bar',
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: channels.map((channel) => {
          const rows = channelRows.filter((row) => row.channel === channel)
          return rows.length ? rows.filter((row) => row.alignmentSuspicionScore >= 60).length / rows.length * 100 : null
        }),
        itemStyle: { color: '#d6a13d', borderRadius: [4, 4, 0, 0] }
      },
      {
        name: '模板稳定性',
        type: 'bar',
        xAxisIndex: 3,
        yAxisIndex: 3,
        data: slots.map((slot) => averageTemplateStability(records.filter((record) => record.slot === slot))),
        itemStyle: { color: '#2f7d79', borderRadius: [4, 4, 0, 0] }
      },
      {
        name: '漂移伪影',
        type: 'bar',
        xAxisIndex: 3,
        yAxisIndex: 3,
        data: slots.map((slot) => (average(records.filter((record) => record.slot === slot), 'template_artifact_score') || 0) * 100),
        itemStyle: { color: '#d6a13d', borderRadius: [4, 4, 0, 0] }
      }
    ]
  }, true)
}

function renderPatientBaselineChart() {
  if (!patientBaselineChartRef.value) {
    patientBaselineChart?.dispose()
    patientBaselineChart = null
    return
  }
  patientBaselineChart = ensureChart(patientBaselineChart, patientBaselineChartRef.value)
  if (!patientBaselineChart) return
  const rows = patientBaselineAvailableChannels.value
  if (!rows.length) {
    patientBaselineChart.clear()
    return
  }
  const colors = { cun: '#2563eb', guan: '#16a34a', chi: '#dc2626' }
  const pointCount = Math.max(...rows.map((row) => (row.personal_baseline_template || []).length))
  patientBaselineChart.setOption({
    title: { text: '质量筛选后的三通道个人基线', left: 0, top: 0, textStyle: { fontSize: 13, fontWeight: 600 } },
    tooltip: { trigger: 'axis' },
    legend: { top: 0, right: 0 },
    grid: { left: 46, right: 22, top: 44, bottom: 34 },
    xAxis: { type: 'category', data: Array.from({ length: pointCount }, (_, index) => index + 1), name: '标准化相位' },
    yAxis: { type: 'value', name: '归一化幅值' },
    series: rows.map((row) => ({
      name: `${baselineChannelName(row.standard_channel_name)}基线`,
      type: 'line',
      smooth: true,
      showSymbol: false,
      data: row.personal_baseline_template || [],
      itemStyle: { color: colors[row.standard_channel_name] }
    }))
  }, true)
}

function renderDetailCharts() {
  if (viewMode.value !== 'detail') return
  renderWaveformChart()
  renderRecordFeatureChart()
  renderSignalQualityChart()
}

function loadPhaseAlignmentSetting() {
  if (typeof window === 'undefined') return false
  return window.localStorage.getItem(PHASE_ALIGNMENT_STORAGE_KEY) === 'true'
}

function circularShift(values, offset) {
  if (!Array.isArray(values) || !values.length) return []
  const normalized = ((Number(offset) || 0) % values.length + values.length) % values.length
  if (!normalized) return [...values]
  return values.slice(normalized).concat(values.slice(0, normalized))
}

function waveformPhaseOffset(channels) {
  if (!phaseAlignmentEnabled.value || !channels.length) return 0
  const anchor = [...channels].sort((left, right) => (Number(right.pulseEnergy) || 0) - (Number(left.pulseEnergy) || 0))[0]
  const template = anchor?.template || []
  if (!template.length) return 0
  return template.reduce((peakIndex, value, index) => (
    Number(value) > Number(template[peakIndex]) ? index : peakIndex
  ), 0)
}

function alignedIndex(index, pointCount, offset) {
  if (!phaseAlignmentEnabled.value || !pointCount || !offset) return index
  return ((index - offset) % pointCount + pointCount) % pointCount
}

function shiftedArea(startIndex, endIndex, pointCount, offset, style, label = null) {
  const start = alignedIndex(startIndex, pointCount, offset)
  const end = alignedIndex(endIndex, pointCount, offset)
  const first = { xAxis: start + 1, itemStyle: style, ...(label ? { label } : {}) }
  if (!phaseAlignmentEnabled.value || !offset || start <= end) {
    return [[first, { xAxis: end + 1 }]]
  }
  return [
    [first, { xAxis: pointCount }],
    [{ xAxis: 1, itemStyle: style }, { xAxis: end + 1 }]
  ]
}

function renderWaveformChart() {
  waveformChart = ensureChart(waveformChart, waveformChartRef.value)
  if (!waveformChart) return
  const channels = selectedRecord.value?.template_metrics || []
  if (!channels.length) {
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
    return
  }
  const displayChannels = ['Cun', 'Guan', 'Chi'].map((name) => channels.find((channel) => channel.channel === name)).filter(Boolean)
  const phaseOffset = waveformPhaseOffset(displayChannels)
  const overlayIndex = displayChannels.length
  const channelColors = { Cun: '#2563eb', Guan: '#16a34a', Chi: '#dc2626' }
  const grids = [...displayChannels, { channel: '三通道叠加' }].map((_, index) => ({
    left: 54,
    right: 36,
    top: 72 + index * 142,
    height: 98
  }))
  const xAxis = [...displayChannels, displayChannels[0]].map((channel, index) => ({
    type: 'category',
    gridIndex: index,
    data: channel.values.map((_, pointIndex) => pointIndex + 1),
    axisLabel: { fontSize: 10 }
  }))
  const yAxis = [...displayChannels, { channel: '叠加' }].map((channel, index) => ({ type: 'value', gridIndex: index, name: channel.channel }))
  const series = []
  for (const [index, channel] of displayChannels.entries()) {
    const events = selectedRecordEvents.value.filter((event) => event.affected_channels.includes(channel.channel))
    const markAreaData = [
      ...channel.windows.flatMap((window) => shiftedArea(
        window.startIndex,
        window.endIndex,
        channel.pointCount,
        phaseOffset,
        { color: artifactSeverityColor(window.artifactSeverityScore, 0.18) }
      )),
      ...events.flatMap((event) => shiftedArea(
        event.start_index,
        event.end_index,
        channel.pointCount,
        phaseOffset,
        { color: 'rgba(220, 38, 38, 0.16)' },
        { show: true, formatter: event.event_id, color: '#7c2d12', fontWeight: 700 }
      ))
    ]
    const markLineData = events.map((event) => ({
      xAxis: alignedIndex(event.start_index, channel.pointCount, phaseOffset) + 1,
      name: event.event_id,
      label: { formatter: event.event_id, color: '#991b1b' },
      lineStyle: { color: '#991b1b', type: 'dashed', width: 1.5 }
    }))
    series.push(
      {
        name: `${channel.channel} waveform`,
        type: 'line',
        xAxisIndex: index,
        yAxisIndex: index,
        showSymbol: false,
        data: circularShift(channel.values, phaseOffset),
        lineStyle: { color: '#1f2937', width: 1.3 },
        markArea: { silent: true, data: markAreaData },
        markLine: { symbol: 'none', data: markLineData }
      },
      {
        name: `${channel.channel} reference_template`,
        type: 'line',
        xAxisIndex: index,
        yAxisIndex: index,
        showSymbol: false,
        data: circularShift(channel.referenceTemplateRaw, phaseOffset),
        lineStyle: { color: channelColors[channel.channel], width: 1.8 }
      }
    )
  }
  for (const channel of displayChannels) {
    const color = channelColors[channel.channel]
    series.push(
      {
        name: `${channel.channel} original overlay`,
        type: 'line',
        xAxisIndex: overlayIndex,
        yAxisIndex: overlayIndex,
        showSymbol: false,
        data: circularShift(channel.values, phaseOffset),
        lineStyle: { color, width: 1, opacity: 0.24 }
      },
      {
        name: `${channel.channel} template overlay`,
        type: 'line',
        xAxisIndex: overlayIndex,
        yAxisIndex: overlayIndex,
        showSymbol: false,
        data: circularShift(channel.referenceTemplateRaw, phaseOffset),
        lineStyle: { color, width: 2 }
      }
    )
  }
  waveformChart.setOption({
    title: {
      text: '三通道脉波 + 参考模板 + 偏移伪影热度',
      subtext: phaseAlignmentEnabled.value ? `统一模板相位偏移 ${phaseOffset} 点` : '',
      left: 0,
      top: 0,
      textStyle: { fontSize: 14, fontWeight: 600 },
      subtextStyle: { color: '#667085', fontSize: 11 }
    },
    tooltip: { trigger: 'axis' },
    legend: {
      top: 34,
      right: 0,
      data: displayChannels.map((channel) => `${channel.channel} template overlay`),
      formatter: (name) => name.replace(' template overlay', ' 模板')
    },
    grid: grids,
    xAxis,
    yAxis,
    visualMap: {
      show: false,
      min: 0,
      max: 1,
      inRange: { color: ['#16a34a', '#d6a13d', '#dc2626'] }
    },
    series
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
    ['模板稳定', recordQualityScore(record)],
    ['漂移伪影', record.template_artifact_score]
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

function clampScore(value, low = 0, high = 100) {
  const number = Number(value)
  if (!Number.isFinite(number)) return low
  return Math.max(low, Math.min(high, number))
}

function mean(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0
}

function std(values) {
  if (values.length < 2) return 0
  const avg = mean(values)
  return Math.sqrt(mean(values.map((value) => (value - avg) ** 2)))
}

function variance(values) {
  if (values.length < 2) return 0
  const avg = mean(values)
  return mean(values.map((value) => (value - avg) ** 2))
}

function linearFit(values) {
  const numeric = values.map(Number).filter((value) => Number.isFinite(value))
  if (numeric.length < 3) {
    return { slope: 0, intercept: mean(numeric), trend: numeric.map(() => mean(numeric)), residual: numeric }
  }
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
  const trend = numeric.map((_, index) => intercept + slope * index)
  return {
    slope,
    intercept,
    trend,
    residual: numeric.map((value, index) => value - trend[index])
  }
}

function detrend(values) {
  return linearFit(values).residual
}

function autocorrelationPeakWithLag(values) {
  if (values.length < 8) return { coherence: 0, lag: null }
  const base = values.map((value) => value - mean(values))
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

function autocorrelationPeak(values) {
  return autocorrelationPeakWithLag(values).coherence
}

function buildPeriodicTemplate(values, lag) {
  if (!lag || lag < 2 || values.length < lag * 2) {
    return { template: [], repeated: values.map(() => 0), residual: values }
  }
  const buckets = Array.from({ length: lag }, () => [])
  values.forEach((value, index) => buckets[index % lag].push(value))
  const template = buckets.map((bucket) => bucket.length ? mean(bucket) : 0)
  const repeated = values.map((_, index) => template[index % lag])
  const residual = values.map((value, index) => value - repeated[index])
  return { template, repeated, residual }
}

function templateMetricsForValues(points) {
  const numeric = points.map(Number).filter((value) => Number.isFinite(value))
  if (numeric.length < 16) {
    return {
      values: numeric,
      detrendedValues: numeric,
      referenceTemplate: numeric.map(() => 0),
      referenceTemplateRaw: numeric.map(() => mean(numeric)),
      template: [],
      pointCount: numeric.length,
      templateStability: null,
      templateCoherence: 0,
      templateExplained: 0,
      periodicSnr: 0,
      pulseEnergy: 0,
      residualFluctuation: 1,
      artifactSeverityScore: 1,
      driftArtifactScore: 100,
      alignmentSuspicionScore: 100,
      dominantLag: null
    }
  }
  const fit = linearFit(numeric)
  const detrended = fit.residual
  const { coherence, lag } = autocorrelationPeakWithLag(detrended)
  const { template, repeated, residual } = buildPeriodicTemplate(detrended, lag)
  const referenceTemplateRaw = repeated.map((value) => value + mean(numeric))
  const detrendedVariance = variance(detrended)
  const residualVariance = variance(residual)
  const templateVariance = variance(repeated)
  const amplitudeRange = percentile(numeric, 0.95) - percentile(numeric, 0.05)
  const residualFluctuation = amplitudeRange > 0 ? std(residual) / (amplitudeRange + 1e-6) : 1
  const templateExplained = detrendedVariance > 0 ? clampScore(1 - residualVariance / detrendedVariance, 0, 1) : 0
  const periodicSnr = templateVariance / (residualVariance + 1e-6)
  const pulseEnergy = templateVariance
  const artifactSeverityScore = amplitudeRange > 0
    ? clampScore(Math.abs(fit.slope) * numeric.length / (amplitudeRange + 1e-6), 0, 1)
    : 1
  const driftArtifactScore = artifactSeverityScore * 100
  const lowEnergyPenalty = pulseEnergy < 0.0001 ? 35 : pulseEnergy < 0.0005 ? 18 : 0
  const lowSnrPenalty = periodicSnr < 0.08 ? 30 : periodicSnr < 0.15 ? 12 : 0
  const alignmentSuspicionScore = clampScore(artifactSeverityScore * 45 + lowEnergyPenalty + lowSnrPenalty + (coherence < 0.08 ? 20 : 0))
  const templateStability = clampScore(
    templateExplained * 40
    + coherence * 35
    + Math.min(periodicSnr, 1) * 25
    - residualFluctuation * 12
    - driftArtifactScore * 0.18
  )
  return {
    values: numeric,
    detrendedValues: detrended,
    referenceTemplate: repeated,
    referenceTemplateRaw,
    template,
    pointCount: numeric.length,
    templateStability,
    templateCoherence: coherence,
    templateExplained,
    periodicSnr,
    pulseEnergy,
    residualFluctuation,
    artifactSeverityScore,
    driftArtifactScore,
    alignmentSuspicionScore,
    dominantLag: lag
  }
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
  if (segments.length && segments.at(-1)[1] < pointCount) {
    segments.push([Math.max(0, pointCount - windowSize), pointCount])
  }
  return segments.length ? segments : [[0, pointCount]]
}

function waveformTemplateAnalysis(points) {
  const numeric = points.map(Number).filter((value) => Number.isFinite(value))
  const overall = templateMetricsForValues(numeric)
  const windows = windowSegments(numeric.length, overall.dominantLag).map(([start, end], index) => {
    const metrics = templateMetricsForValues(numeric.slice(start, end))
    return {
      windowIndex: index,
      startIndex: start,
      endIndex: end - 1,
      templateStability: metrics.templateStability,
      templateCoherence: metrics.templateCoherence,
      templateExplained: metrics.templateExplained,
      periodicSnr: metrics.periodicSnr,
      pulseEnergy: metrics.pulseEnergy,
      residualFluctuation: metrics.residualFluctuation,
      artifactSeverityScore: metrics.artifactSeverityScore,
      driftArtifactScore: metrics.driftArtifactScore,
      alignmentSuspicionScore: metrics.alignmentSuspicionScore
    }
  })
  return { ...overall, windows }
}

function standardPulseChannel(name) {
  const value = String(name || '').toLowerCase()
  if (value === 'cun') return 'Cun'
  if (value === 'guan' || value === 'guanmai' || value === 'guan_mai') return 'Guan'
  if (value === 'chi') return 'Chi'
  return null
}

function recordTemplateStability(record) {
  const channels = []
  if (Array.isArray(record?.waveform_preview)) {
    for (const channel of record.waveform_preview) {
      const name = standardPulseChannel(channel.name)
      if (!name || !Array.isArray(channel.points)) continue
      channels.push({ channel: name, ...waveformTemplateAnalysis(channel.points) })
    }
  }
  const scores = channels.map((channel) => channel.templateStability).filter((value) => Number.isFinite(value))
  const artifacts = channels.map((channel) => channel.driftArtifactScore).filter((value) => Number.isFinite(value))
  const snrs = channels.map((channel) => channel.periodicSnr).filter((value) => Number.isFinite(value))
  const score = scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null
  const artifactScore = artifacts.length ? artifacts.reduce((sum, value) => sum + value, 0) / artifacts.length / 100 : null
  const avgSnr = snrs.length ? snrs.reduce((sum, value) => sum + value, 0) / snrs.length : null
  let label = 'no_waveform'
  if (score !== null) {
    label = score >= 60 ? 'stable_template' : score >= 35 ? 'usable_template' : 'unstable_template'
  }
  const events = buildDisplacementEvents(channels, recordDurationSeconds(record))
  return {
    score: score === null ? null : Number(score.toFixed(3)),
    artifactScore: artifactScore === null ? null : Number(artifactScore.toFixed(3)),
    label,
    channels,
    events,
    periodicSnr: avgSnr === null ? null : Number(avgSnr.toFixed(6)),
    signalQualityScore: score === null ? null : Number(clampScore(score * 0.65 + Math.min((avgSnr || 0), 1) * 25 - (artifactScore || 0) * 20).toFixed(3)),
    stableSegmentRatio: channels.flatMap((channel) => channel.windows || []).filter((window) => window.templateStability >= 50 && window.artifactSeverityScore < 0.7).length / Math.max(1, channels.flatMap((channel) => channel.windows || []).length),
    alignmentSuspicion: channels.some((channel) => channel.alignmentSuspicionScore >= 60)
  }
}

function artifactSeverityColor(score, alpha = 0.24) {
  const value = Number(score)
  if (!Number.isFinite(value) || value < 0.35) return `rgba(22, 163, 74, ${alpha})`
  if (value < 0.7) return `rgba(214, 161, 61, ${alpha})`
  return `rgba(220, 38, 38, ${alpha})`
}

function artifactSeverityLabel(score) {
  const value = Number(score)
  if (!Number.isFinite(value) || value < 0.35) return '轻'
  if (value < 0.7) return '中'
  return '重'
}

function displacementEventType(window, affectedCount) {
  if (affectedCount >= 2 && window.artifactSeverityScore >= 0.35) return 'multi_channel_shift'
  if (window.artifactSeverityScore >= 0.35) return 'single_channel_shift'
  if (window.pulseEnergy < 0.0001) return 'amplitude_drop'
  if (window.alignmentSuspicionScore >= 70) return 'persistent_alignment_issue'
  if (window.templateCoherence < 0.08) return 'template_mismatch'
  return 'baseline_shift'
}

function buildDisplacementEvents(channels, durationSeconds = null) {
  const events = []
  if (!channels.length) return events
  const windows = new Map()
  for (const channel of channels) {
    for (const window of channel.windows || []) {
      const risk = Number(window.artifactSeverityScore) >= 0.35
        || Number(window.alignmentSuspicionScore) >= 60
        || Number(window.templateCoherence) < 0.08
        || Number(window.pulseEnergy) < 0.0001
      if (!risk) continue
      const item = windows.get(window.windowIndex) || { windowIndex: window.windowIndex, rows: [] }
      item.rows.push({ channel: channel.channel, ...window })
      windows.set(window.windowIndex, item)
    }
  }
  const pointCount = Math.max(1, ...channels.map((channel) => channel.pointCount || 1))
  const secondsPerPoint = durationSeconds ? durationSeconds / Math.max(1, pointCount - 1) : null
  ;[...windows.values()].sort((left, right) => left.windowIndex - right.windowIndex).forEach((item, index) => {
    const first = item.rows[0]
    const startIndex = Math.min(...item.rows.map((row) => row.startIndex))
    const endIndex = Math.max(...item.rows.map((row) => row.endIndex))
    const severity = Math.max(...item.rows.map((row) => Number(row.artifactSeverityScore) || 0))
    const confidence = clampScore(
      severity * 0.55
      + Math.max(...item.rows.map((row) => Number(row.alignmentSuspicionScore) || 0)) / 100 * 0.30
      + Math.min(1, item.rows.length / 3) * 0.15,
      0,
      1
    )
    const startTime = secondsPerPoint ? startIndex * secondsPerPoint : startIndex
    const endTime = secondsPerPoint ? endIndex * secondsPerPoint : endIndex
    const eventType = displacementEventType(first, item.rows.length)
    events.push({
      event_id: `E${index + 1}`,
      start_index: startIndex,
      end_index: endIndex,
      start_time: secondsPerPoint ? `${formatNumber(startTime, 1)}s` : `${startIndex}`,
      end_time: secondsPerPoint ? `${formatNumber(endTime, 1)}s` : `${endIndex}`,
      duration: secondsPerPoint ? `${formatNumber(Math.max(0, endTime - startTime), 1)}s` : `${Math.max(0, endIndex - startIndex)}`,
      affected_channels: [...new Set(item.rows.map((row) => row.channel))].join(', '),
      event_type: eventType,
      severity: artifactSeverityLabel(severity),
      severity_score: Number(severity.toFixed(3)),
      confidence: Number(confidence.toFixed(3)),
      description: eventDescription(eventType, severity, item.rows)
    })
  })
  return events
}

function eventDescription(eventType, severity, rows) {
  const channels = [...new Set(rows.map((row) => row.channel))].join('/')
  const severityText = artifactSeverityLabel(severity)
  const text = {
    single_channel_shift: '单通道窗口出现偏移伪影，需结合模板匹配判断是否可用。',
    multi_channel_shift: '多个通道同时出现偏移伪影，疑似采集姿态或设备接触变化。',
    amplitude_drop: '脉搏能量明显偏低，稳定波形也可能来自未对准或接触不足。',
    baseline_shift: '基线漂移较明显，可能影响模板叠加和周期估计。',
    template_mismatch: '周期模板匹配较差，稳定性不能直接作为高质量依据。',
    persistent_alignment_issue: '持续疑似未对准，建议剔除或重采。'
  }[eventType]
  return `${channels}：${severityText}度；${text}`
}

function patientTypicalTemplates(records) {
  const channels = ['Cun', 'Guan', 'Chi']
  return channels.map((channel) => {
    const vectors = records
      .flatMap((record) => record.template_metrics || [])
      .filter((item) => item.channel === channel && Array.isArray(item.template) && item.template.length)
      .map((item) => normalizeSeries(item.template))
    const maxLength = Math.max(0, ...vectors.map((vector) => vector.length))
    const points = Array.from({ length: maxLength }, (_, index) => {
      const values = vectors.map((vector) => vector[index]).filter((value) => Number.isFinite(value))
      return values.length ? Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(4)) : null
    })
    return { channel, points }
  })
}

function normalizeSeries(values) {
  const numeric = values.map(Number).filter((value) => Number.isFinite(value))
  const valueMean = mean(numeric)
  const valueStd = std(numeric)
  return valueStd ? numeric.map((value) => (value - valueMean) / valueStd) : numeric.map(() => 0)
}

function waveformSignalMetrics(points) {
  const metrics = waveformTemplateAnalysis(points)
  const templateStability = Number(metrics.templateStability)
  return {
    amplitudeRange: 0,
    fluctuation: Number(metrics.residualFluctuation.toFixed(4)),
    noise: Number(metrics.driftArtifactScore.toFixed(4)),
    periodicity: Number(metrics.templateCoherence.toFixed(4)),
    periodicSnr: Number(metrics.periodicSnr.toFixed(4)),
    templateStability: Number.isFinite(templateStability) ? templateStability : null
  }
}

function renderSignalQualityChart() {
  signalQualityChart = ensureChart(signalQualityChart, signalQualityChartRef.value)
  if (!signalQualityChart) return
  const rows = selectedRecordStabilityRows.value
  const windowIndexes = [...new Set(rows.map((row) => row.windowIndex))].sort((left, right) => left - right)
  const channels = ['Cun', 'Guan', 'Chi']
  const colors = { Cun: '#2563eb', Guan: '#16a34a', Chi: '#dc2626' }
  if (!rows.length) {
    signalQualityChart.clear()
    return
  }
  signalQualityChart.setOption({
    title: { text: '该条记录模板稳定性与漂移伪影', left: 0, top: 0, textStyle: { fontSize: 14, fontWeight: 600 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        const lines = [`窗口 ${params[0]?.axisValue || ''}`]
        for (const item of params) {
          const row = item.data?.row
          lines.push(`${item.marker}${item.seriesName}: ${formatNumber(item.value, 1)} 模板=${formatNumber(row?.templateCoherence, 2)} 残差=${formatNumber(row?.residualFluctuation, 2)}`)
        }
        return lines.join('<br/>')
      }
    },
    legend: { top: 0, right: 0 },
    grid: { left: 42, right: 48, top: 48, bottom: 44 },
    xAxis: { type: 'category', data: windowIndexes.map((index) => index + 1) },
    yAxis: [
      { type: 'value', name: '稳定', min: 0, max: 100 },
      { type: 'value', name: '伪影', min: 0, max: 100 }
    ],
    series: [
      ...channels.map((channel) => ({
        name: `${channel} 模板稳定`,
        type: 'line',
        smooth: true,
        symbolSize: 7,
        data: windowIndexes.map((windowIndex) => {
          const row = rows.find((item) => item.windowIndex === windowIndex && item.channel === channel)
          return row ? { value: row.templateStability, row } : null
        }),
        itemStyle: { color: colors[channel] }
      })),
      {
        name: '漂移伪影',
        type: 'bar',
        yAxisIndex: 1,
        barMaxWidth: 18,
        data: windowIndexes.map((windowIndex) => {
          const matches = rows.filter((item) => item.windowIndex === windowIndex)
          const artifact = average(matches, 'driftArtifactScore')
          return { value: artifact, row: { templateCoherence: null, residualFluctuation: null } }
        }),
        itemStyle: { color: 'rgba(214, 161, 61, 0.36)' }
      }
    ]
  }, true)
}

function resizeCharts() {
  patientTrendChart?.resize()
  patientSlotChart?.resize()
  patientOnlineAnalysisChart?.resize()
  patientBaselineChart?.resize()
  waveformChart?.resize()
  recordFeatureChart?.resize()
  signalQualityChart?.resize()
}

onMounted(async () => {
  loading.value = true
  const requestedUserId = String(route.query.user_id || '')
  const requestedRecordId = String(route.query.record_id || '')
  const openRequestedDetail = route.query.view === 'detail' || Boolean(requestedRecordId)
  try {
    const [usersPayload, pulsePayload] = await Promise.all([
      api.getPulseUsers(),
      api.getPulseUserRecords(null)
    ])
    users.value = Array.isArray(usersPayload) ? usersPayload : usersPayload.items || []
    pulseRecords.value = pulsePayload
    selectedUserId.value = patientSummaries.value.some((patient) => patient.user_id === requestedUserId)
      ? requestedUserId
      : (patientSummaries.value[0]?.user_id || users.value[0]?.user_id || '')
    selectedRecord.value = selectedPatientRecords.value.at(-1) || null
    await fetchPatientPulseSummary()
    if (openRequestedDetail) {
      viewMode.value = 'detail'
      selectedRecord.value = selectedPatientRecords.value.find((record) => String(recordRecordId(record)) === requestedRecordId)
        || selectedPatientRecords.value.at(-1)
        || null
    }
  } finally {
    loading.value = false
  }
  await nextTick()
  renderPatientCharts()
  renderDetailCharts()
  window.addEventListener('resize', resizeCharts)
})

watch([selectedUserId, pulseRecords], async () => {
  recordPage.value = 1
  recordSlotFilter.value = 'all'
  recordDeviceFilter.value = 'all'
  recordEventFilter.value = 'all'
  selectedRecord.value = selectedPatientRecords.value.at(-1) || null
  fetchPatientPulseSummary()
  await nextTick()
  renderPatientCharts()
  renderDetailCharts()
})

watch([recordFilter, recordSlotFilter, recordDeviceFilter, recordEventFilter, viewMode], async () => {
  recordPage.value = 1
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

watch(phaseAlignmentEnabled, async (enabled) => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(PHASE_ALIGNMENT_STORAGE_KEY, String(enabled))
  }
  await nextTick()
  renderWaveformChart()
})

watch(() => [viewMode.value, selectedRecord.value?.row_key], () => {
  fetchSelectedRecordPeriodAnalysis()
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

.header-actions {
  flex-wrap: wrap;
  justify-content: flex-end;
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
  flex: 0 0 auto;
}

.record-filter-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 10px;
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

.record-reasons {
  color: #b45309;
  font-size: 12px;
  line-height: 1.35;
}

.record-id {
  color: #7a858f;
  flex: 1;
  font-size: 11px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.patient-pagination,
.record-pagination {
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
  font-size: 22px;
  font-weight: 700;
  line-height: 1.1;
  overflow-wrap: anywhere;
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

.patient-visualization-panel {
  border: 1px solid #e2ecea;
  border-radius: 6px;
  margin-bottom: 16px;
  padding: 12px;
}

.visualization-header {
  align-items: center;
  display: flex;
  gap: 12px;
  justify-content: space-between;
  margin-bottom: 10px;
}

.visualization-header div {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.visualization-header strong {
  color: #1f2d3d;
  font-size: 14px;
  font-weight: 600;
}

.visualization-header span,
.visualization-meta {
  color: #7a858f;
  font-size: 12px;
}

.patient-online-analysis-chart {
  background: #fff;
  border: 1px solid #eef2f1;
  border-radius: 4px;
  height: 500px;
  width: 100%;
}

.baseline-note {
  margin-bottom: 10px;
}

.patient-baseline-chart {
  background: #fff;
  border: 1px solid #eef2f1;
  border-radius: 4px;
  height: 280px;
  margin-bottom: 10px;
  width: 100%;
}

.baseline-status-table {
  margin-top: 10px;
}

.visualization-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
}

.chart {
  height: 304px;
  width: 100%;
}

.waveform-chart {
  height: 650px;
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
.measurement-table,
.event-table {
  margin-top: 14px;
}

.alignment-warning {
  margin-bottom: 14px;
}

.period-consistency-panel {
  border: 1px solid #e3e9e7;
  border-radius: 6px;
  margin-bottom: 16px;
  padding: 12px;
}

.subpanel-header {
  align-items: center;
  display: flex;
  gap: 10px;
  justify-content: space-between;
  margin-bottom: 10px;
}

.period-consistency-table {
  width: 100%;
}

@media (max-width: 768px) {
  .metric-grid,
  .record-summary-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .record-filter-grid {
    grid-template-columns: 1fr;
  }

  .waveform-chart {
    height: 700px;
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

}
</style>
