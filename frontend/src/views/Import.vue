<template>
  <div class="demo-data">
    <el-alert
      title="一阶段不做自动化导入。这里仅展示静态 demo 数据如何映射到后续 Flask API 与标准层实体。"
      type="info"
      show-icon
      :closable="false"
      class="notice"
    />

    <el-row :gutter="16">
      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>静态数据对象</template>
          <el-table v-loading="loading" :data="dataObjects" size="small">
            <el-table-column prop="name" label="对象" width="170" />
            <el-table-column prop="count" label="样例数" width="90" />
            <el-table-column prop="mapsTo" label="后续映射" />
          </el-table>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="12">
        <el-card shadow="never" class="panel-card">
          <template #header>后续接口调试清单</template>
          <el-timeline>
            <el-timeline-item timestamp="/api/demo/summary" type="primary">驱动首页统计和覆盖率图表</el-timeline-item>
            <el-timeline-item timestamp="/api/demo/users" type="success">驱动用户纵向随访列表</el-timeline-item>
            <el-timeline-item timestamp="/api/demo/visits/{id}" type="success">驱动多模态 visit 详情</el-timeline-item>
            <el-timeline-item timestamp="/api/demo/pulse/*" type="warning">驱动脉诊横向、纵向和稳定性分析</el-timeline-item>
          </el-timeline>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../services/api'

const loading = ref(false)
const summary = ref({ stats: {} })
const pulseRecords = ref([])
const datasetVersions = ref([])

const dataObjects = computed(() => [
  { name: 'users', count: summary.value.stats.user_count || 0, mapsTo: 'dim_user / dim_user_identity_map' },
  { name: 'visits', count: summary.value.stats.visit_count || 0, mapsTo: 'fact_visit / mart_user_day_panel' },
  { name: 'pulseRecords', count: pulseRecords.value.length, mapsTo: 'fact_modality_record / feature_pulse_observation' },
  { name: 'assets', count: summary.value.stats.asset_count || 0, mapsTo: 'fact_file_asset' },
  { name: 'qualityEvents', count: summary.value.stats.quality_event_count || 0, mapsTo: 'fact_quality_event' },
  { name: 'datasetVersions', count: datasetVersions.value.length, mapsTo: 'dataset_definition / dataset_version' }
])

onMounted(async () => {
  loading.value = true
  try {
    const [summaryPayload, pulsePayload, datasetPayload] = await Promise.all([
      api.summary(),
      api.pulseRecords({ include_suspicious: true }),
      api.datasetVersions()
    ])
    summary.value = summaryPayload
    pulseRecords.value = pulsePayload
    datasetVersions.value = datasetPayload
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.demo-data {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.notice,
.panel-card {
  border-radius: 6px;
}
</style>
