<template>
  <div class="checkin-page">
    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="header-row">
          <div>
            <div class="title">打卡矩阵</div>
            <div class="subtitle">按用户和日期查看聚合后的打卡次数、有效性和来源。</div>
          </div>
          <el-space>
            <el-select v-model="selectedMonth" placeholder="月份" class="month-select" @change="loadMatrix">
              <el-option v-for="month in availableMonths" :key="month" :label="month" :value="month" />
            </el-select>
            <el-radio-group v-model="viewMode" size="small">
              <el-radio-button label="thumbnail">缩略图</el-radio-button>
              <el-radio-button label="table">展开视图</el-radio-button>
            </el-radio-group>
          </el-space>
        </div>
      </template>

      <div v-loading="loading" class="matrix-body">
        <div class="matrix-viewport">
          <div class="date-matrix" :class="`date-matrix--${viewMode}`" :style="matrixGridStyle">
            <div class="matrix-header user-header">用户</div>
            <div v-for="date in matrix.dates" :key="date" class="matrix-header date-header">{{ date }}</div>

            <template v-for="row in matrixRows" :key="row.user_id">
              <router-link class="user-cell" :to="`/patients/${row.user_id}`">
                <span class="user-name">{{ row.user_name }}</span>
                <span class="user-id">{{ row.display_id }}</span>
              </router-link>
              <div v-for="date in matrix.dates" :key="`${row.user_id}-${date}`">
                <div
                  v-if="matrixCell(row, date)"
                  class="matrix-cell"
                  :class="cellClass(matrixCell(row, date))"
                  :title="cellTitle(row, date)"
                >
                  <span class="cell-count">{{ matrixCell(row, date).count }}</span>
                  <span class="cell-status">{{ cellStatusName(matrixCell(row, date)) }}</span>
                  <span class="cell-source">{{ sourceLabels(matrixCell(row, date).sources) }}</span>
                </div>
                <div v-else class="matrix-cell cell-empty" :title="cellTitle(row, date)">
                  <span class="cell-count">0</span>
                  <span class="cell-status">无效</span>
                  <span class="cell-source">-</span>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../services/api'

const loading = ref(false)
const selectedMonth = ref('')
const availableMonths = ref([])
const viewMode = ref('thumbnail')
const matrix = ref({
  dates: [],
  slots: ['早', '中', '晚'],
  rows: [],
  summary: {}
})

const matrixGridStyle = computed(() => {
  const columns = Math.max(1, matrix.value.dates.length)
  return {
    '--date-columns': columns
  }
})

const matrixRows = computed(() => matrix.value.rows.map((row) => {
  const dateCells = {}
  matrix.value.dates.forEach((date) => {
    const cell = aggregateDateCell(row, date)
    if (cell) dateCells[date] = cell
  })
  return { ...row, date_cells: dateCells }
}))

async function loadMatrix() {
  loading.value = true
  try {
    const payload = await api.checkinMatrix({ month: selectedMonth.value })
    matrix.value = payload
    availableMonths.value = payload.months || []
    if (!selectedMonth.value && availableMonths.value.length) {
      selectedMonth.value = availableMonths.value[availableMonths.value.length - 1]
      await loadMatrix()
    }
  } finally {
    loading.value = false
  }
}

function matrixCell(row, date) {
  return row.date_cells?.[date] || null
}

function aggregateDateCell(row, date) {
  const slotCells = row.cells?.[date]
  if (!slotCells) return null

  const merged = {
    count: 0,
    valid_count: 0,
    sources: [],
    visit_ids: []
  }
  Object.values(slotCells).forEach((cell) => {
    merged.count += cell.count || 0
    merged.valid_count += cell.valid_count || 0
    ;(cell.sources || []).forEach((source) => {
      if (!merged.sources.includes(source)) merged.sources.push(source)
    })
    ;(cell.visit_ids || []).forEach((visitId) => merged.visit_ids.push(visitId))
  })

  if (!merged.count) return null
  merged.sources.sort()
  merged.status = merged.count === merged.valid_count ? 'valid' : 'invalid'
  return merged
}

function cellTitle(row, date) {
  const cell = matrixCell(row, date)
  if (!cell) return `${row.user_name} ${date}: 0 次 无效 -`
  return `${row.user_name} ${date}: ${cell.count} 次 ${cellStatusName(cell)} ${sourceLabels(cell.sources)}`
}

function sourceName(value) {
  return value === 'zhongke' ? '中科' : value === 'yushengtang' ? '玉生堂' : value
}

function sourceLabels(sources = []) {
  const labels = sources.map(sourceName).filter(Boolean)
  return labels.length ? labels.join('/') : '-'
}

function cellStatusName(cell) {
  return cell.status === 'valid' ? '有效' : '无效'
}

function cellClass(cell) {
  return `cell-${cell.status}`
}

onMounted(loadMatrix)
</script>

<style scoped>
.checkin-page {
  min-height: calc(100vh - 100px);
}
.panel-card {
  border-radius: 6px;
}
.header-row {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: space-between;
}
.title {
  color: #303133;
  font-size: 16px;
  font-weight: 700;
}
.subtitle {
  color: #7a858f;
  font-size: 12px;
  margin-top: 4px;
}
.month-select {
  width: 132px;
}
.matrix-body {
  min-height: calc(100vh - 220px);
}
.matrix-viewport {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  height: calc(100vh - 236px);
  overflow: auto;
}
.date-matrix {
  display: grid;
  gap: 1px;
  grid-template-columns: 136px repeat(var(--date-columns), minmax(108px, 1fr));
  min-width: max-content;
}
.date-matrix--thumbnail {
  grid-template-columns: 112px repeat(var(--date-columns), minmax(76px, 1fr));
}
.matrix-header {
  align-items: center;
  background: #f5f7fa;
  color: #606266;
  display: flex;
  font-size: 12px;
  font-weight: 700;
  justify-content: center;
  min-height: 34px;
  padding: 0 8px;
  position: sticky;
  top: 0;
  z-index: 2;
}
.user-header {
  left: 0;
  justify-content: flex-start;
  z-index: 3;
}
.date-header {
  white-space: nowrap;
}
.user-cell {
  align-items: flex-start;
  background: #fff;
  color: #303133;
  display: flex;
  flex-direction: column;
  font-size: 12px;
  font-weight: 700;
  justify-content: center;
  left: 0;
  min-height: 58px;
  padding: 8px;
  position: sticky;
  text-decoration: none;
  z-index: 1;
}
.date-matrix--thumbnail .user-cell {
  min-height: 40px;
  padding: 6px;
}
.user-cell:hover .user-name {
  color: #409eff;
}
.user-name {
  line-height: 1.3;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.user-id {
  color: #909399;
  font-size: 11px;
  font-weight: 500;
  line-height: 1.3;
  margin-top: 2px;
}
.matrix-cell {
  align-items: center;
  background: #fff;
  display: grid;
  gap: 2px;
  grid-template-rows: 1fr auto auto;
  justify-items: center;
  min-height: 58px;
  padding: 6px;
  text-align: center;
}
.date-matrix--thumbnail .matrix-cell {
  gap: 1px;
  min-height: 40px;
  padding: 4px;
}
.cell-valid {
  background: #edf8f2;
}
.cell-invalid {
  background: #fef0f0;
}
.cell-empty {
  background: #f7f9fb;
}
.cell-count {
  color: #1f4f4c;
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
}
.date-matrix--thumbnail .cell-count {
  font-size: 14px;
}
.cell-status,
.cell-source {
  color: #606266;
  font-size: 11px;
  line-height: 1.2;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  word-break: break-all;
}
.cell-valid .cell-status {
  color: #2f8f52;
}
.cell-invalid .cell-status,
.cell-empty .cell-status {
  color: #c45656;
}
.cell-empty .cell-count,
.cell-empty .cell-source {
  color: #a8abb2;
}
@media (max-width: 900px) {
  .header-row {
    align-items: flex-start;
    flex-direction: column;
  }
  .date-matrix,
  .date-matrix--thumbnail {
    grid-template-columns: 104px repeat(var(--date-columns), minmax(72px, 1fr));
  }
}
</style>
