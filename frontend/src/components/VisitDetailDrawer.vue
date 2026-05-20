<template>
  <el-drawer v-model="visible" :title="ui.drawerTitle" size="68%" destroy-on-close>
    <div v-loading="loading" class="visit-detail-drawer">
      <template v-if="detail.visit_id">
        <el-alert
          v-if="detail.load_error"
          type="error"
          show-icon
          :closable="false"
          :title="detail.load_error"
          class="detail-error"
        />

        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item :label="ui.visitTime">{{ detail.visit_time || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="ui.user">{{ detail.user_name || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="ui.source">{{ sourceName(detail.source_vendor) }}</el-descriptions-item>
          <el-descriptions-item :label="ui.sourceId">{{ detail.source_visit_id || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="ui.slot">{{ detail.time_window_slot || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="ui.quality">
            <el-tag size="small" :type="qualityType(detail.quality_status)">
              {{ qualityName(detail.quality_status) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item :label="ui.groupId" :span="2">
            {{ detail.source_record_group_id || '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">{{ ui.featureWide }}</el-divider>
        <div v-if="featureGroups.length" class="feature-wide-panel">
          <div class="feature-wide-meta">
            <span>{{ ui.featureCount }}: {{ detail.feature_wide?.feature_count || 0 }}</span>
            <span>{{ ui.parserVersion }}: {{ detail.feature_wide?.parser_version || '-' }}</span>
            <span>{{ ui.updatedAt }}: {{ formatDateTime(detail.feature_wide?.updated_at) }}</span>
          </div>
          <el-collapse v-model="activeFeatureGroups">
            <el-collapse-item
              v-for="group in featureGroups"
              :key="group.key"
              :name="group.key"
              :title="`${group.label} / ${group.items.length}`"
            >
              <div class="feature-grid">
                <div v-for="item in group.items" :key="item.key" class="feature-item">
                  <div class="feature-key" :title="item.key">{{ item.key }}</div>
                  <div class="feature-value" :title="stringValue(item.value)">
                    {{ displayValue(item.value) }}
                  </div>
                </div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
        <el-empty v-else :description="ui.noFeatureWide" :image-size="72" />

        <el-divider content-position="left">{{ ui.modalityParsedData }}</el-divider>
        <el-table :data="detail.modality_records || []" size="small" border>
          <el-table-column prop="modality_type" :label="ui.modality" width="100">
            <template #default="{ row }">{{ modalityName(row.modality_type) }}</template>
          </el-table-column>
          <el-table-column prop="completion_status" :label="ui.status" width="110" />
          <el-table-column :label="ui.structuredData" min-width="360">
            <template #default="{ row }">
              <div v-if="row.structured_data_json" class="structured-block">
                <div class="structured-meta">
                  {{ row.structured_data_json.source_vendor || '-' }} /
                  {{ row.structured_data_json.asset_count || 0 }} {{ ui.assetsUnit }}
                </div>
                <div v-if="row.modality_type === 'pulse' && row.structured_data_json.records?.length" class="pulse-records">
                  <div class="pulse-records-title">
                    {{ ui.pulseRecords }} / {{ row.structured_data_json.records.length }}
                  </div>
                  <el-table :data="row.structured_data_json.records" size="small" border>
                    <el-table-column prop="side" :label="ui.side" width="70" />
                    <el-table-column prop="pulse_type" :label="ui.pulseType" min-width="110" show-overflow-tooltip />
                    <el-table-column prop="pulse_rate" :label="ui.pulseRate" width="84" />
                    <el-table-column prop="force" :label="ui.force" width="84" />
                    <el-table-column prop="tension" :label="ui.tension" width="84" />
                    <el-table-column prop="fluency" :label="ui.fluency" width="84" />
                    <el-table-column prop="amplitude" :label="ui.amplitude" width="88" />
                    <el-table-column prop="stability_score" :label="ui.stability" width="92" />
                  </el-table>
                </div>
                <el-collapse>
                  <el-collapse-item
                    v-for="asset in row.structured_data_json.assets || []"
                    :key="asset.asset_id"
                    :title="`${asset.asset_type || '-'} / ${asset.file_name || '-'} / ${asset.parse_status || '-'}`"
                  >
                    <pre class="json-preview">{{ compactJson(asset.structured || asset) }}</pre>
                  </el-collapse-item>
                </el-collapse>
              </div>
              <pre v-else class="json-preview">{{ compactJson(row.feature_summary_json || row.parsed_structured_data_json) }}</pre>
            </template>
          </el-table-column>
        </el-table>

        <el-divider content-position="left">{{ ui.fileAssets }}</el-divider>
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
            <div class="asset-meta">{{ asset.asset_type }} / {{ formatSize(asset.file_size) }}</div>
          </div>
        </div>
      </template>
      <el-empty v-else-if="!loading" :description="ui.noVisitSelected" :image-size="72" />
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
const activeFeatureGroups = ref(['base', 'pulse', 'tongue'])

const ui = {
  drawerTitle: '\u68c0\u67e5\u8be6\u60c5',
  visitTime: '\u91c7\u96c6\u65f6\u95f4',
  user: '\u7528\u6237',
  source: '\u6765\u6e90',
  sourceId: '\u6765\u6e90 ID',
  slot: '\u65f6\u6bb5',
  quality: '\u8d28\u91cf',
  groupId: '\u805a\u5408 ID',
  featureWide: '\u7ed3\u6784\u5316\u5bbd\u8868\u5b57\u6bb5',
  featureCount: '\u53d8\u91cf\u6570',
  parserVersion: '\u89e3\u6790\u7248\u672c',
  updatedAt: '\u66f4\u65b0\u65f6\u95f4',
  noFeatureWide: '\u5c1a\u672a\u751f\u6210 visit \u7ea7\u7ed3\u6784\u5316\u5bbd\u8868',
  modalityParsedData: '\u6a21\u6001\u89e3\u6790\u7ed3\u679c',
  modality: '\u6a21\u6001',
  status: '\u72b6\u6001',
  structuredData: '\u6807\u51c6\u5316\u7ed3\u6784\u5316\u6570\u636e',
  assetsUnit: '\u4e2a\u8d44\u4ea7',
  pulseRecords: '\u8109\u8bca\u89e3\u6790\u8bb0\u5f55',
  side: '\u4fa7\u522b',
  pulseType: '\u8109\u8c61',
  pulseRate: '\u8109\u7387',
  force: '\u8109\u529b',
  tension: '\u7d27\u5f20\u5ea6',
  fluency: '\u6d41\u5229\u5ea6',
  amplitude: '\u5e45\u503c',
  stability: '\u7a33\u5b9a\u6027',
  fileAssets: '\u6587\u4ef6\u8d44\u4ea7',
  noVisitSelected: '\u5c1a\u672a\u9009\u62e9 visit'
}

const modalityLabels = {
  ask: '\u95ee\u8bca',
  pulse: '\u8109\u8bca',
  tongue: '\u820c\u8bca',
  face: '\u9762\u8bca',
  voice: '\u58f0\u8bca',
  report: '\u62a5\u544a'
}

const sourceLabels = {
  zhongke: '\u4e2d\u79d1',
  yushengtang: '\u7389\u751f\u5802'
}

const qualityLabels = {
  valid: '\u6709\u6548',
  incomplete: '\u4e0d\u5b8c\u6574',
  suspicious: '\u7591\u4f3c\u5f02\u5e38'
}

const featureGroups = computed(() => {
  const groups = detail.value.feature_wide?.groups || {}
  return Object.entries(groups)
    .map(([key, group]) => {
      const fields = group?.fields || {}
      return {
        key,
        label: group?.label || modalityName(key),
        items: Object.entries(fields).map(([fieldKey, value]) => ({ key: fieldKey, value }))
      }
    })
    .filter((group) => group.items.length > 0)
})

watch(
  () => [props.modelValue, props.visitId],
  async ([open, visitId]) => {
    if (!open || !visitId) return
    loading.value = true
    try {
      detail.value = await api.visitDetail(visitId)
      const groupKeys = Object.keys(detail.value.feature_wide?.groups || {})
      activeFeatureGroups.value = groupKeys.slice(0, 4)
    } catch (error) {
      detail.value = {
        visit_id: visitId,
        load_error: error?.message || String(error)
      }
    } finally {
      loading.value = false
    }
  },
  { immediate: true }
)

function modalityName(value) {
  return modalityLabels[value] || value || '-'
}

function sourceName(value) {
  return sourceLabels[value] || value || '-'
}

function qualityName(value) {
  return qualityLabels[value] || value || '-'
}

function qualityType(value) {
  return { valid: 'success', incomplete: 'warning', suspicious: 'danger' }[value] || 'info'
}

function compactJson(value) {
  if (!value || Object.keys(value).length === 0) return '{}'
  const text = JSON.stringify(value, null, 2)
  return text.length > 2400 ? `${text.slice(0, 2400)}\n...` : text
}

function stringValue(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function displayValue(value) {
  const text = stringValue(value)
  return text.length > 120 ? `${text.slice(0, 120)}...` : text
}

function formatDateTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 19)
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

.detail-error {
  margin-bottom: 12px;
}

.feature-wide-panel {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 12px;
}

.feature-wide-meta {
  color: #606266;
  display: flex;
  flex-wrap: wrap;
  font-size: 12px;
  gap: 12px;
  margin-bottom: 10px;
}

.feature-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
}

.feature-item {
  background: #f8fafc;
  border: 1px solid #edf0f5;
  border-radius: 4px;
  min-width: 0;
  padding: 8px;
}

.feature-key {
  color: #7a858f;
  font-size: 12px;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.feature-value {
  color: #1f2d3d;
  font-size: 13px;
  line-height: 1.45;
  margin-top: 4px;
  overflow-wrap: anywhere;
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

.pulse-records {
  margin-bottom: 10px;
}

.pulse-records-title {
  color: #303133;
  font-size: 13px;
  font-weight: 600;
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
