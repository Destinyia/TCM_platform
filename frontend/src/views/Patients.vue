<template>
  <div class="patients">
    <el-card shadow="never" class="panel-card">
      <template #header>
        <div class="header-row">
          <div>
            <div class="title">用户纵向随访</div>
            <div class="subtitle">以脱敏用户为主线，展示 visit 覆盖、质量状态和最近采集情况。</div>
          </div>
          <el-input v-model="keyword" placeholder="搜索姓名或脱敏 ID" clearable class="search-input" @input="handleSearch" />
        </div>
      </template>
      <el-table v-loading="loading" :data="users" stripe height="calc(100vh - 258px)">
        <el-table-column prop="display_id" label="脱敏ID" width="110" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column prop="sex" label="性别" width="70" />
        <el-table-column prop="age" label="年龄" width="70" />
        <el-table-column prop="cohort" label="队列" width="130" />
        <el-table-column prop="visit_count" label="visit数" width="90" />
        <el-table-column prop="last_visit" label="最近采集" width="120" />
        <el-table-column label="模态覆盖率" min-width="180">
          <template #default="{ row }">
            <el-progress :percentage="Math.round(row.modality_coverage * 100)" :stroke-width="8" />
          </template>
        </el-table-column>
        <el-table-column prop="quality_status" label="质量状态" width="105">
          <template #default="{ row }">
            <el-tag size="small" :type="qualityType(row.quality_status)">
              {{ qualityName(row.quality_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="router.push('/patients/' + row.user_id)">随访详情</el-button>
            <el-button size="small" type="primary" link @click="router.push('/pulse-analysis')">脉诊分析</el-button>
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
          @size-change="loadUsers"
          @current-change="loadUsers"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../services/api'

const router = useRouter()
const keyword = ref('')
const users = ref([])
const loading = ref(false)
const pagination = ref({
  page: 1,
  pageSize: 50,
  total: 0
})
let searchTimer

function qualityName(value) {
  return { valid: '有效', incomplete: '不完整', suspicious: '疑似异常' }[value] || value
}

function qualityType(value) {
  return { valid: 'success', incomplete: 'warning', suspicious: 'danger' }[value] || 'info'
}

async function loadUsers() {
  loading.value = true
  try {
    const payload = await api.users({
      page: pagination.value.page,
      page_size: pagination.value.pageSize,
      keyword: keyword.value
    })
    users.value = payload.items || payload
    pagination.value.total = payload.total ?? users.value.length
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    pagination.value.page = 1
    loadUsers()
  }, 260)
}

onMounted(async () => {
  await loadUsers()
})
</script>

<style scoped>
.patients {
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
.search-input {
  width: 260px;
}
.pager-row {
  display: flex;
  justify-content: flex-end;
  padding-top: 14px;
}
</style>
