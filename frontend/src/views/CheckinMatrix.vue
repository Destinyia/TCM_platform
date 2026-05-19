<template>
  <div class="checkin-page">
    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="header-row">
          <div>
            <div class="title">打卡矩阵</div>
            <div class="subtitle">按用户、日期、早中晚时段查看打卡覆盖、来源和质量状态。</div>
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
        <div v-if="viewMode === 'thumbnail'" class="thumbnail-grid" :style="thumbnailStyle">
          <div v-for="row in matrix.rows" :key="row.user_id" class="user-strip">
            <div class="strip-name">{{ row.user_name }}</div>
            <div class="strip-cells">
              <template v-for="date in matrix.dates" :key="date">
                <div
                  v-for="slot in matrix.slots"
                  :key="`${row.user_id}-${date}-${slot}`"
                  class="mini-cell"
                  :class="miniCellClass(matrixCell(row, date, slot))"
                  :title="cellTitle(row, date, slot)"
                />
              </template>
            </div>
          </div>
        </div>

        <el-table
          v-else
          :data="matrix.rows"
          size="small"
          border
          class="matrix-table"
          height="calc(100vh - 236px)"
        >
          <el-table-column prop="display_id" label="脱敏ID" width="96" fixed />
          <el-table-column prop="user_name" label="用户" width="100" fixed />
          <el-table-column prop="total_count" label="次数" width="72" fixed />
          <el-table-column v-for="date in matrix.dates" :key="date" :label="date" align="center">
            <el-table-column
              v-for="slot in matrix.slots"
              :key="`${date}-${slot}`"
              :label="slot"
              width="126"
              align="center"
            >
              <template #default="{ row }">
                <div v-if="matrixCell(row, date, slot)" class="matrix-cell" :class="cellClass(matrixCell(row, date, slot))">
                  <div class="cell-top">
                    <span class="cell-count">{{ matrixCell(row, date, slot).count }}</span>
                    <el-tag size="small" :type="cellQualityType(matrixCell(row, date, slot))">
                      {{ cellQualityName(matrixCell(row, date, slot)) }}
                    </el-tag>
                  </div>
                  <div class="cell-meta">{{ matrixCell(row, date, slot).sources.map(sourceName).join('/') }}</div>
                  <div class="cell-modalities">{{ matrixCell(row, date, slot).modalities.map(modalityName).join('、') }}</div>
                </div>
                <span v-else class="empty-cell">-</span>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>
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

const modalityLabels = {
  ask: '问诊',
  pulse: '脉诊',
  tongue: '舌诊',
  face: '面诊',
  voice: '声诊',
  report: '报告'
}

const thumbnailStyle = computed(() => {
  const columns = Math.max(1, matrix.value.dates.length * matrix.value.slots.length)
  return {
    '--matrix-columns': columns
  }
})

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

function matrixCell(row, date, slot) {
  return row.cells?.[date]?.[slot]
}

function miniCellClass(cell) {
  if (!cell) return 'mini-empty'
  return `mini-${cell.status}`
}

function cellTitle(row, date, slot) {
  const cell = matrixCell(row, date, slot)
  if (!cell) return `${row.user_name} ${date} ${slot}: 无`
  return `${row.user_name} ${date} ${slot}: ${cell.count} 次 ${cell.sources.map(sourceName).join('/')}`
}

function sourceName(value) {
  return value === 'zhongke' ? '中科' : value === 'yushengtang' ? '玉生堂' : value
}

function modalityName(value) {
  return modalityLabels[value] || value
}

function cellQualityName(cell) {
  if (cell.status === 'valid') return '有效'
  if (cell.status === 'mixed') return '混合'
  return '异常'
}

function cellQualityType(cell) {
  if (cell.status === 'valid') return 'success'
  if (cell.status === 'mixed') return 'warning'
  return 'danger'
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
.thumbnail-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: calc(100vh - 236px);
  overflow: auto;
}
.user-strip {
  align-items: stretch;
  display: grid;
  gap: 8px;
  grid-template-columns: 96px 1fr;
  min-height: 24px;
}
.strip-name {
  color: #303133;
  font-size: 12px;
  font-weight: 700;
  overflow: hidden;
  padding-top: 2px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.strip-cells {
  display: grid;
  gap: 2px;
  grid-template-columns: repeat(var(--matrix-columns), minmax(4px, 1fr));
}
.mini-cell {
  border-radius: 2px;
  min-height: 20px;
}
.mini-empty {
  background: #edf0f3;
}
.mini-valid {
  background: #45b36b;
}
.mini-mixed {
  background: #e6a23c;
}
.mini-invalid {
  background: #d9534f;
}
.matrix-table {
  width: 100%;
}
.matrix-cell {
  border-radius: 4px;
  min-height: 74px;
  padding: 6px;
  text-align: left;
}
.cell-valid {
  background: #edf8f2;
}
.cell-mixed {
  background: #fff7e8;
}
.cell-invalid {
  background: #fef0f0;
}
.cell-top {
  align-items: center;
  display: flex;
  justify-content: space-between;
}
.cell-count {
  color: #1f4f4c;
  font-size: 18px;
  font-weight: 700;
}
.cell-meta,
.cell-modalities {
  color: #606266;
  font-size: 12px;
  line-height: 1.35;
  margin-top: 4px;
  word-break: break-all;
}
.empty-cell {
  color: #a8abb2;
}
</style>
