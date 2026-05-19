<template>
  <div class="dataset-page">
    <el-row :gutter="16">
      <el-col :xs="24" :lg="9">
        <el-card shadow="never" class="panel-card">
          <template #header>新建数据集快照</template>
          <el-form label-width="108px">
            <el-form-item label="任务类型">
              <el-select v-model="form.taskType" class="full-width">
                <el-option label="脉诊特征分析" value="pulse_feature_analysis" />
                <el-option label="多模态体质分类" value="multimodal_constitution" />
                <el-option label="舌象分类" value="tongue_classification" />
              </el-select>
            </el-form-item>
            <el-form-item label="模态组合">
              <el-checkbox-group v-model="form.modalities">
                <el-checkbox label="ask">问诊</el-checkbox>
                <el-checkbox label="pulse">脉诊</el-checkbox>
                <el-checkbox label="tongue">舌诊</el-checkbox>
                <el-checkbox label="face">面诊</el-checkbox>
              </el-checkbox-group>
            </el-form-item>
            <el-form-item label="质量策略">
              <el-radio-group v-model="form.qualityPolicy">
                <el-radio label="valid_only">仅有效</el-radio>
                <el-radio label="explicit_missing">允许显式缺失</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="划分策略">
              <el-select v-model="form.splitStrategy" class="full-width">
                <el-option label="按用户划分" value="by_user" />
                <el-option label="按日期划分" value="by_date" />
                <el-option label="手工划分" value="manual" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary">生成静态 manifest 预览</el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="15">
        <el-card shadow="never" class="panel-card">
          <template #header>
            <div class="panel-header">
              <span>数据集版本</span>
              <el-tag>demo manifest</el-tag>
            </div>
          </template>
          <el-table v-loading="loading" :data="datasetVersions" stripe>
            <el-table-column prop="dataset_id" label="数据集" width="130" />
            <el-table-column prop="version" label="版本" min-width="160" />
            <el-table-column prop="task_type" label="任务" min-width="160" />
            <el-table-column prop="samples" label="样本" width="80" />
            <el-table-column prop="users" label="用户" width="80" />
            <el-table-column prop="split_strategy" label="划分" width="100" />
            <el-table-column label="模态" min-width="160">
              <template #default="{ row }">
                <el-space wrap>
                  <el-tag v-for="modality in row.modalities" :key="modality" size="small" effect="plain">
                    {{ modality }}
                  </el-tag>
                </el-space>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="90">
              <template #default="{ row }">
                <el-tag size="small" :type="row.status === 'ready' ? 'success' : 'info'">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="never" class="panel-card manifest-card">
          <template #header>manifest 样例</template>
          <pre class="manifest">{{ manifestPreview }}</pre>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { api } from '../services/api'

const form = ref({
  taskType: 'pulse_feature_analysis',
  modalities: ['pulse'],
  qualityPolicy: 'valid_only',
  splitStrategy: 'by_user'
})
const datasetVersions = ref([])
const loading = ref(false)

const manifestPreview = computed(() => JSON.stringify({
  sample_id: 'demo-sample-001',
  dataset_version: datasetVersions.value[0]?.version || 'v2026.05.demo.001',
  split: 'train',
  user_id: 'DEID-001',
  visit_id: 'V001',
  modalities: form.value.modalities,
  quality_policy: form.value.qualityPolicy,
  split_strategy: form.value.splitStrategy,
  assets: [
    {
      asset_id: 'A002',
      modality: 'pulse',
      asset_type: 'pulse_raw_left',
      path: 'files/pulse/U001/V001_left.bin',
      sha256: 'demo_hash'
    }
  ],
  label: {
    pulse_type: '弦细'
  }
}, null, 2))

onMounted(async () => {
  loading.value = true
  try {
    datasetVersions.value = await api.datasetVersions()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.panel-card {
  border-radius: 6px;
}
.panel-header {
  align-items: center;
  display: flex;
  justify-content: space-between;
}
.full-width {
  width: 100%;
}
.manifest-card {
  margin-top: 16px;
}
.manifest {
  background: #f7f8fa;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  color: #303133;
  font-size: 12px;
  line-height: 1.55;
  margin: 0;
  overflow: auto;
  padding: 12px;
}
</style>
