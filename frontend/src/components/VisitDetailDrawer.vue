<template>
  <el-drawer v-model="visible" title="visit 详细数据" size="58%" destroy-on-close>
    <div v-loading="loading" class="visit-detail-drawer">
      <template v-if="detail.visit_id">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="采集时间">{{ detail.visit_time }}</el-descriptions-item>
          <el-descriptions-item label="用户">{{ detail.user_name }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ sourceName(detail.source_vendor) }}</el-descriptions-item>
          <el-descriptions-item label="来源ID">{{ detail.source_visit_id }}</el-descriptions-item>
          <el-descriptions-item label="时段">{{ detail.time_window_slot }}</el-descriptions-item>
          <el-descriptions-item label="质量">
            <el-tag size="small" :type="qualityType(detail.quality_status)">
              {{ qualityName(detail.quality_status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="聚合ID" :span="2">{{ detail.source_record_group_id }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">模态数据</el-divider>
        <el-table :data="detail.modality_records || []" size="small" border>
          <el-table-column prop="modality_type" label="模态" width="90">
            <template #default="{ row }">{{ modalityName(row.modality_type) }}</template>
          </el-table-column>
          <el-table-column prop="completion_status" label="状态" width="110" />
          <el-table-column label="标准化结构化数据" min-width="360">
            <template #default="{ row }">
              <div v-if="row.structured_data_json" class="structured-block">
                <div class="structured-meta">
                  {{ row.structured_data_json.source_vendor }} · {{ row.structured_data_json.asset_count }} 个解析资产
                </div>
                <el-collapse>
                  <el-collapse-item
                    v-for="asset in row.structured_data_json.assets"
                    :key="asset.asset_id"
                    :title="`${asset.asset_type} · ${asset.file_name} · ${asset.parse_status}`"
                  >
                    <pre class="json-preview">{{ compactJson(asset.structured || asset) }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </div>
              <pre v-else class="json-preview">{{ compactJson(row.feature_summary_json || row.parsed_structured_data_json) }}</pre>
            </template>
          </el-table-column>
        </el-table>

        <el-divider content-position="left">文件资产</el-divider>
        <div class="asset-grid">
          <div v-for="asset in detail.assets || []" :key="asset.asset_id" class="asset-card">
            <el-image
              v-if="isImage(asset)"
              :src="assetUrl(asset)"
              :preview-src-list="[assetUrl(asset)]"
              fit="cover"
              class="asset-image"
              lazy
            />
            <div v-else class="asset-placeholder">{{ asset.asset_type }}</div>
            <div class="asset-name" :title="asset.file_name">{{ asset.file_name }}</div>
            <div class="asset-meta">{{ asset.asset_type }} · {{ formatSize(asset.file_size) }}</div>
          </div>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api, apiUrl } from '../services/api'

const props = defineProps({
  modelValue: Boolean,
  visitId: String
})
const emit = defineEmits(['update:modelValue'])
const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})
const loading = ref(false)
const detail = ref({})

const modalityLabels = {
  ask: '问诊',
  pulse: '脉诊',
  tongue: '舌诊',
  face: '面诊',
  voice: '声诊',
  report: '报告'
}

watch(() => [props.modelValue, props.visitId], async ([open, visitId]) => {
  if (!open || !visitId) return
  loading.value = true
  try {
    detail.value = await api.visitDetail(visitId)
  } finally {
    loading.value = false
  }
}, { immediate: true })

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

function compactJson(value) {
  if (!value || Object.keys(value).length === 0) return '{}'
  const text = JSON.stringify(value, null, 2)
  return text.length > 2400 ? `${text.slice(0, 2400)}\n...` : text
}

function isImage(asset) {
  return String(asset.mime_type || '').startsWith('image/')
}

function assetUrl(asset) {
  return apiUrl(asset.preview_url || `/api/demo/assets/${asset.asset_id}/file`)
}

function formatSize(value) {
  const size = Number(value || 0)
  if (size > 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  if (size > 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${size} B`
}
</script>

<style scoped>
.visit-detail-drawer {
  min-height: 360px;
}
.json-preview {
  color: #606266;
  font-size: 12px;
  line-height: 1.35;
  margin: 0;
  max-height: 260px;
  overflow: auto;
  white-space: pre-wrap;
}
.structured-block {
  min-width: 0;
}
.structured-meta {
  color: #7a858f;
  font-size: 12px;
  margin-bottom: 8px;
}
.asset-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
}
.asset-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  min-width: 0;
  padding: 8px;
}
.asset-image,
.asset-placeholder {
  align-items: center;
  background: #f5f7fa;
  border-radius: 4px;
  display: flex;
  height: 118px;
  justify-content: center;
  width: 100%;
}
.asset-placeholder {
  color: #909399;
  font-size: 12px;
}
.asset-name {
  color: #303133;
  font-size: 12px;
  margin-top: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asset-meta {
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}
</style>
