<template>
  <div class="examinations">
    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="header-row">
          <div>
            <div class="title">多模态检查记录</div>
            <div class="subtitle">按 visit 粒度分页查看采集记录、模态覆盖、质量标签和文件资产。</div>
          </div>
          <el-space wrap>
            <el-select v-model="filters.source" placeholder="来源" clearable class="filter-item" @change="reloadFirstPage">
              <el-option label="中科" value="zhongke" />
              <el-option label="玉生堂" value="yushengtang" />
            </el-select>
            <el-select v-model="filters.quality" placeholder="质量状态" clearable class="filter-item" @change="reloadFirstPage">
              <el-option label="有效" value="valid" />
              <el-option label="不完整" value="incomplete" />
              <el-option label="疑似异常" value="suspicious" />
            </el-select>
            <el-select v-model="filters.modality" placeholder="包含模态" clearable class="filter-item" @change="reloadFirstPage">
              <el-option v-for="(label, value) in modalityLabels" :key="value" :label="label" :value="value" />
            </el-select>
            <el-input v-model="filters.keyword" placeholder="搜索用户、visit ID 或质量标签" clearable class="search-input" @input="handleSearch" />
          </el-space>
        </div>
      </template>

      <el-table v-loading="loading" :data="visits" stripe height="calc(100vh - 258px)" @row-dblclick="openVisit">
        <el-table-column prop="visit_time" label="采集时间" width="150" />
        <el-table-column prop="user_name" label="用户" width="100" />
        <el-table-column prop="source_vendor" label="来源" width="96">
          <template #default="{ row }">
            <el-tag size="small" :type="row.source_vendor === 'zhongke' ? 'primary' : 'success'">
              {{ sourceName(row.source_vendor) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="source_visit_id" label="来源 visit ID" min-width="190" />
        <el-table-column prop="time_window_slot" label="时段" width="70" />
        <el-table-column label="模态覆盖" min-width="260">
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
        <el-table-column label="质量标签" min-width="220">
          <template #default="{ row }">
            <el-space v-if="row.quality_flags.length" wrap>
              <el-tag v-for="flag in row.quality_flags" :key="flag" size="small" type="info">
                {{ flag }}
              </el-tag>
            </el-space>
            <span v-else class="empty-text">无</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="openVisit(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-row">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[20, 50, 100]"
          :total="pagination.total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="loadVisits"
          @current-change="loadVisits"
        />
      </div>
    </el-card>

    <VisitDetailDrawer v-model="detailVisible" :visit-id="selectedVisitId" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import VisitDetailDrawer from '../components/VisitDetailDrawer.vue'
import { api } from '../services/api'

const filters = ref({
  source: '',
  quality: '',
  modality: '',
  keyword: ''
})
const visits = ref([])
const loading = ref(false)
const detailVisible = ref(false)
const selectedVisitId = ref('')
const pagination = ref({
  page: 1,
  pageSize: 50,
  total: 0
})
let searchTimer

const modalityLabels = {
  ask: '问诊',
  pulse: '脉诊',
  tongue: '舌诊',
  face: '面诊',
  voice: '声诊',
  report: '报告'
}

async function loadVisits() {
  loading.value = true
  try {
    const payload = await api.visits({
      page: pagination.value.page,
      page_size: pagination.value.pageSize,
      ...filters.value
    })
    visits.value = payload.items || payload
    pagination.value.total = payload.total ?? visits.value.length
  } finally {
    loading.value = false
  }
}

function reloadFirstPage() {
  pagination.value.page = 1
  loadVisits()
}

function handleSearch() {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(reloadFirstPage, 260)
}

function openVisit(row) {
  selectedVisitId.value = row.visit_id
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

onMounted(loadVisits)
</script>

<style scoped>
.examinations {
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
.filter-item {
  width: 128px;
}
.search-input {
  width: 260px;
}
.empty-text {
  color: #a8abb2;
  font-size: 12px;
}
.pager-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}
</style>
