<template>
  <div class="patient-detail">
    <el-page-header @back="router.back()">
      <template #content>
        <span>{{ user.name || '用户' }} 的多模态随访详情</span>
      </template>
    </el-page-header>

    <div class="detail-layout">
      <main class="left-pane">
        <el-card shadow="never" class="panel-card">
          <template #header>用户信息</template>
          <el-descriptions :column="2" size="small" border>
            <el-descriptions-item label="脱敏ID">{{ user.display_id }}</el-descriptions-item>
            <el-descriptions-item label="姓名">{{ user.name }}</el-descriptions-item>
            <el-descriptions-item label="性别">{{ user.sex }}</el-descriptions-item>
            <el-descriptions-item label="年龄">{{ user.age }}岁</el-descriptions-item>
            <el-descriptions-item label="队列">{{ user.cohort }}</el-descriptions-item>
            <el-descriptions-item label="最近采集">{{ user.last_visit || '-' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>

        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>脉诊纵向趋势</span>
              <el-button type="primary" link @click="router.push('/pulse-analysis')">进入脉诊分析</el-button>
            </div>
          </template>
          <div ref="pulseChartRef" class="trend-chart"></div>
        </el-card>

        <el-card shadow="never" class="panel-card">
          <template #header>分析摘要</template>
          <el-row :gutter="12">
            <el-col :xs="24" :sm="8" v-for="item in summaryCards" :key="item.label">
              <div class="metric-card">
                <div class="metric-value">{{ item.value }}</div>
                <div class="metric-label">{{ item.label }}</div>
              </div>
            </el-col>
          </el-row>
        </el-card>
      </main>

      <aside class="right-pane">
        <el-card shadow="never" class="panel-card timeline-card">
          <template #header>
            <div class="panel-header">
              <span>visit 时间线</span>
              <el-tag size="small">{{ userVisits.length }} 条</el-tag>
            </div>
          </template>
          <el-timeline>
            <el-timeline-item
              v-for="visit in userVisits"
              :key="visit.visit_id"
              :timestamp="visit.visit_time"
              placement="top"
              :type="visit.quality_status === 'valid' ? 'success' : 'warning'"
            >
              <button class="visit-card" @click="openVisit(visit)">
                <div class="visit-title">
                  <span>{{ sourceName(visit.source_vendor) }} · {{ visit.source_visit_id }}</span>
                  <el-tag size="small" :type="qualityType(visit.quality_status)">
                    {{ qualityName(visit.quality_status) }}
                  </el-tag>
                </div>
                <div class="visit-meta">
                  {{ visit.time_window_slot || '-' }}时段 · {{ visit.sequence_slot || '-' }}
                </div>
                <el-space wrap class="modality-tags">
                  <el-tag v-for="modality in visit.modalities" :key="modality" size="small" effect="plain">
                    {{ modalityName(modality) }}
                  </el-tag>
                  <el-tag v-for="modality in visit.missing_modalities" :key="modality" size="small" type="warning" effect="plain">
                    缺 {{ modalityName(modality) }}
                  </el-tag>
                </el-space>
              </button>
            </el-timeline-item>
          </el-timeline>
        </el-card>
      </aside>
    </div>

    <VisitDetailDrawer v-model="detailVisible" :visit-id="selectedVisitId" />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import * as echarts from 'echarts'
import VisitDetailDrawer from '../components/VisitDetailDrawer.vue'
import { api } from '../services/api'

const router = useRouter()
const route = useRoute()
const pulseChartRef = ref(null)
const user = ref({})
const userVisits = ref([])
const userPulseRecords = ref([])
const detailVisible = ref(false)
const selectedVisitId = ref('')
let pulseChart

const modalityLabels = {
  ask: '问诊',
  pulse: '脉诊',
  tongue: '舌诊',
  face: '面诊',
  voice: '声诊',
  report: '报告'
}

const summaryCards = computed(() => [
  { label: 'visit 数', value: userVisits.value.length },
  { label: '脉诊记录', value: userPulseRecords.value.length },
  { label: '异常/不完整', value: userVisits.value.filter((item) => item.quality_status !== 'valid').length }
])

function openVisit(visit) {
  selectedVisitId.value = visit.visit_id
  detailVisible.value = true
}

function modalityName(value) {
  return modalityLabels[value] || value
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

function renderPulseChart() {
  const records = userPulseRecords.value || []
  pulseChart = pulseChart || echarts.init(pulseChartRef.value)
  pulseChart.setOption({
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    grid: { left: 40, right: 18, top: 42, bottom: 30 },
    xAxis: { type: 'category', data: records.map((record) => `${record.visit_date}\n${record.slot}`) },
    yAxis: { type: 'value' },
    series: [
      { name: '脉率', type: 'line', smooth: true, data: records.map((record) => record.pulse_rate) },
      { name: '脉力', type: 'line', smooth: true, data: records.map((record) => record.force) },
      { name: '稳定性', type: 'line', smooth: true, data: records.map((record) => record.stability_score) }
    ]
  }, true)
}

function resizeChart() {
  pulseChart?.resize()
}

onMounted(async () => {
  const payload = await api.userTimeline(route.params.id)
  user.value = payload.user
  userVisits.value = payload.visits
  userPulseRecords.value = await api.pulseUserTrend({ user_id: route.params.id })
  await nextTick()
  renderPulseChart()
  window.addEventListener('resize', resizeChart)
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeChart)
  pulseChart?.dispose()
})
</script>

<style scoped>
.patient-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: calc(100vh - 100px);
  min-height: 0;
}
.detail-layout {
  display: grid;
  flex: 1;
  gap: 16px;
  grid-template-columns: minmax(0, 1fr) 390px;
  min-height: 0;
}
.left-pane,
.right-pane {
  min-height: 0;
  overflow: auto;
}
.left-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel-card {
  border-radius: 6px;
}
.timeline-card {
  min-height: 100%;
}
.panel-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
}
.trend-chart {
  height: 320px;
  width: 100%;
}
.metric-card {
  background: #f7f9fb;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 14px;
}
.metric-value {
  color: #1f4f4c;
  font-size: 24px;
  font-weight: 700;
}
.metric-label {
  color: #7a858f;
  font-size: 12px;
  margin-top: 4px;
}
.visit-card {
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  cursor: pointer;
  display: block;
  padding: 10px;
  text-align: left;
  width: 100%;
}
.visit-card:hover {
  border-color: #409eff;
}
.visit-title {
  align-items: center;
  color: #303133;
  display: flex;
  font-weight: 700;
  gap: 8px;
  justify-content: space-between;
}
.visit-meta {
  color: #7a858f;
  font-size: 12px;
  margin-top: 6px;
}
.modality-tags {
  margin-top: 10px;
}
@media (max-width: 1100px) {
  .patient-detail {
    height: auto;
  }
  .detail-layout {
    grid-template-columns: 1fr;
  }
}
</style>
