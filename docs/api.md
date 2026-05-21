# 多模态数据平台 API 与路由索引

更新时间：2026-05-20

## 1. 基础信息

- 后端入口：`backend/run.py`
- Flask 应用工厂：`backend/app/__init__.py`
- Demo API 蓝图：`backend/app/demo_api.py`，注册前缀 `/api/demo`
- Ingest API 蓝图：`backend/app/ingest_api.py`，注册前缀 `/api/ingest`
- 健康检查：`GET /api/health`
- 前端 API base：`frontend/src/services/api.js` 中的 `API_BASE`
- 默认开发 API base：`http://localhost:5000`
- 响应格式：当前 demo 接口直接返回 JSON payload，不包裹统一 `code/data/message`

## 2. 前端路由

路由定义：`frontend/src/router/index.js`

| 路由 | 组件 | 主要 API |
| --- | --- | --- |
| `/` | `Dashboard.vue` | `GET /api/demo/summary`、`GET /api/demo/visits` |
| `/checkin-matrix` | `CheckinMatrix.vue` | `GET /api/demo/checkin-matrix` |
| `/patients` | `Patients.vue` | `GET /api/demo/users` |
| `/patients/:id` | `PatientDetail.vue` | `GET /api/demo/users/{user_id}/timeline`、`GET /api/demo/pulse/user-trend` |
| `/examinations` | `Examinations.vue` | `GET /api/demo/visits` |
| `/pulse-analysis` | `PulseAnalysis.vue` | `GET /api/demo/pulse/*` |
| `/import` | `Import.vue` | 说明页/后续导入入口 |
| `/export` | `Export.vue` | `GET /api/demo/dataset-versions` |

## 3. Demo API

### 3.1 `GET /api/demo/summary`

用途：数据总览。

返回字段：

| 字段 | 说明 |
| --- | --- |
| `stats` | 用户数、visit 数、资产数、质量事件数 |
| `modality_coverage` | 各模态存在记录数 |
| `quality_distribution` | 质量事件分布 |
| `recent_visits` | 最近 visit 列表 |

### 3.2 `GET /api/demo/checkin-matrix`

用途：打卡矩阵页面。

Query：

| 参数 | 说明 |
| --- | --- |
| `month` | 可选，格式 `YYYY-MM` |

返回字段：

| 字段 | 说明 |
| --- | --- |
| `dates` | 当前月份/筛选范围内的日期列 |
| `slots` | 时段列表，当前为 `早`、`中`、`晚` |
| `months` | 可选月份列表 |
| `rows` | 用户行 |
| `summary` | 用户数、日期数、visit 数、有效 visit 数 |

`rows[]`：

| 字段 | 说明 |
| --- | --- |
| `user_id` | `dim_user.user_id`，前端跳转患者详情使用 |
| `display_id` | 脱敏展示 ID |
| `user_name` | 当前 demo 显示姓名 |
| `total_count` | 用户总 visit 数 |
| `valid_count` | 用户有效 visit 数 |
| `cells` | `cells[visit_date][visit_slot]` |

`cells[visit_date][visit_slot]`：

| 字段 | 说明 |
| --- | --- |
| `count` | 该用户、日期、时段的 visit 数 |
| `valid_count` | 该时段有效 visit 数 |
| `sources` | 来源平台，如 `zhongke`、`yushengtang` |
| `quality_statuses` | 原始质量状态集合 |
| `modalities` | 存在的模态集合 |
| `visit_ids` | 该单元格内的 visit ID |
| `visit_times` | 采集时间 |
| `status` | 后端时段级状态：`valid`、`mixed`、`invalid` |

当前前端展示规则：

- 展示为 `用户 × 日期`，不展示早中晚子列。
- 前端聚合同一用户同一天的早中晚单元格。
- 单元格只显示 `数字`、`有效/无效`、`来源`。
- 聚合后 `count == valid_count` 显示 `有效`，否则显示 `无效`。
- 无打卡的空单元格留空，不显示 `0`、`无效` 或来源占位。
- 姓名区域跳转 `/patients/{user_id}`。

### 3.3 `GET /api/demo/users`

用途：用户列表。

返回数组字段：

| 字段 | 说明 |
| --- | --- |
| `user_id` | 标准用户 ID |
| `display_id` | 脱敏 ID |
| `name` | 姓名 |
| `sex` | 性别 |
| `age` | 年龄 |
| `cohort` | 队列 |
| `visit_count` | visit 数 |
| `last_visit` | 最近 visit 日期 |
| `modality_completion` | 模态完整率 |
| `quality_status` | 用户聚合质量状态 |

### 3.4 `GET /api/demo/users/{user_id}/timeline`

用途：患者随访详情页。

返回字段：

| 字段 | 说明 |
| --- | --- |
| `user` | 用户基础信息 |
| `visits` | 该用户所有 visit，按时间倒序 |

`visits[]` 使用 `visit_payload` 结构：

| 字段 | 说明 |
| --- | --- |
| `visit_id` | visit ID |
| `user_id` | 用户 ID |
| `user_name` | 用户名 |
| `source_vendor` | 来源平台 |
| `source_vendor_name` | 来源平台中文名 |
| `source_visit_id` | 来源 visit ID |
| `source_record_group_id` | 来源聚合组 |
| `visit_time` | `YYYY-MM-DD HH:mm` |
| `visit_date` | `YYYY-MM-DD` |
| `time_window_slot` | `早`、`中`、`晚` |
| `sequence_slot` | 当日序号 |
| `quality_status` | `valid/incomplete/suspicious` |
| `modalities` | 存在模态 |
| `missing_modalities` | 缺失模态 |
| `quality_flags` | 质量标签 |

### 3.5 `GET /api/demo/visits`

用途：全局 visit 列表。

Query：

| 参数 | 说明 |
| --- | --- |
| `page` | 可选，页码 |
| `page_size` | 可选，每页数量 |

无分页参数时返回数组；有分页参数时返回 `{ items, total, page, page_size }`。

### 3.6 `GET /api/demo/visits/{visit_id}`

用途：visit 多模态详情抽屉。

返回字段：

| 字段 | 说明 |
| --- | --- |
| visit payload 字段 | 同上 |
| `modalities_detail` | 模态记录详情 |
| `assets` | 文件资产 |

### 3.7 `GET /api/demo/assets`

用途：资产审核/预览列表。

返回数组字段：

| 字段 | 说明 |
| --- | --- |
| `asset_id` | 资产 ID |
| `visit_id` | visit ID |
| `asset_type` | 资产类型 |
| `asset_role` | 资产角色 |
| `file_name` | 文件名 |
| `storage_uri` | 存储 URI |
| `file_hash` | hash |
| `file_size` | 文件大小 |
| `mime_type` | MIME |
| `source_vendor` | 来源 |
| `visit_date` | visit 日期 |
| `download_url` | 文件接口路径 |

### 3.8 `GET /api/demo/assets/{asset_id}/file`

用途：读取本地标准存储中的文件资产。

注意：生产环境不得直接暴露原始目录，应通过权限校验和 Nginx 内部转发或短期 URL。

### 3.9 `GET /api/demo/quality-events`

用途：质量事件列表。

返回 `fact_quality_event` 的核心字段：`quality_event_id`、`entity_type`、`entity_id`、`quality_flag`、`severity`、`status`、`rule_version`、`evidence_json`、`created_at`。

### 3.10 `GET /api/demo/dataset-versions`

用途：数据集版本页面。

返回 `dataset_version` 的核心字段：`dataset_version_id`、`dataset_id`、`version_name`、`task_type`、`status`、`modality_filter_json`、`quality_filter_json`、`split_strategy`、`summary_json`、`created_at`。

## 4. 脉诊分析 API

当前 `/api/demo/pulse/*` 仍是展示型 demo API。脉诊分析模块与数据平台保持低耦合，平台长期对外契约应是通用数据集下载、manifest、脱敏和审计能力，而不是绑定脉诊专用 analysis-ready API。详细边界见 `docs/脉诊分析下游闭环接口需求.md`。

### 4.1 `GET /api/demo/pulse/records`

用途：脉诊记录明细。

Query：

| 参数 | 说明 |
| --- | --- |
| `user_id` | 可选，按用户过滤 |
| `include_suspicious` | 可选，是否纳入疑似异常 |

返回字段来自脉诊 `parsed_structured_data_json.records[]`，并补充 `visit_id`、`modality_record_id`、`user_id`、`user_name`、`source_vendor`、`visit_date`、`visit_time`、`slot`、`quality_status`。

### 4.2 `GET /api/demo/pulse/user-trend`

用途：单用户纵向趋势。参数同 `pulse/records`，返回按 `visit_date + visit_time` 排序的记录。

### 4.3 `GET /api/demo/pulse/slot-stability`

用途：同一用户同槽位稳定性分析。

Query：

| 参数 | 说明 |
| --- | --- |
| `user_id` | 可选 |
| `slot` | 可选，`早/中/晚` |

### 4.4 `GET /api/demo/pulse/cross-user`

用途：多用户横向对比。

返回按用户聚合后的脉诊特征统计。

### 4.5 `GET /api/demo/pulse/feature-drift`

用途：不同时段特征变化。

Query：

| 参数 | 说明 |
| --- | --- |
| `user_id` | 可选 |

## 5. 脉诊模块辅助 API

一阶段新增独立蓝图，注册前缀 `/api/pulse`。这些接口用于当前脉诊研究模块的本地验证和样本检查，不是数据平台面向独立研究者的通用下载契约。未来独立研究者应优先通过通用数据集下载接口获取版本化数据包。

### 5.1 `GET /api/pulse/analysis/phase1-summary`

用途：读取已生成的一阶段分析结果，返回首页可视化面板所需的聚合指标。

当前默认读取：

```text
storage/datasets/DS-PULSE-PHASE1/v2026.05.phase1.001/analysis/phase1/
```

核心字段：

| 字段 | 说明 |
| --- | --- |
| `measurement_count` | 一阶段 measurement 总数 |
| `valid_count` / `partial_valid_count` / `invalid_count` | 有效性分布 |
| `duration_unavailable_count` | 缺少真实或可推断时长的 measurement 数 |
| `source_quality` | 按来源统计的有效性、平均质量分、平均漂移 |
| `slot_quality` | 按时段统计的有效性、平均质量分、平均漂移 |
| `feature_risks` | 特征可靠性风险排序，来自 `feature_reliability.csv` |
| `quality_drift_scatter` | 质量分与漂移指数散点采样 |

### 5.2 `GET /api/pulse/analysis/user-visualization`

用途：查询某个用户是否已有离线生成的单用户脉诊可视化图片，供 `/pulse-analysis` 患者 summary 区展示。

Query：
| 参数 | 说明 |
| --- | --- |
| `user_id` | 必填，标准用户 ID |

返回字段：
| 字段 | 说明 |
| --- | --- |
| `available` | 是否存在该用户的可视化结果 |
| `image_url` | 图片读取接口路径，存在结果时返回 |
| `selected_measurement_id` | 可视化中选用的示例 measurement |
| `patient_measurements` / `patient_channel_rows` / `patient_periodic_rows` | 用户级样本统计 |
| `patient_avg_periodic_snr` | 用户三通道平均周期信噪比 |

### 5.3 `GET /api/pulse/analysis/user-visualization/{user_id}/image`

用途：返回离线生成的单用户脉诊可视化 PNG 文件。

### 5.4 `GET /api/pulse/measurements`

用途：查询脉诊 measurement 样本主表。

Query：

| 参数 | 说明 |
| --- | --- |
| `user_id` | 可选，按用户过滤 |
| `source_vendor` | 可选，按来源过滤 |
| `visit_slot` | 可选，`早/中/晚` |
| `quality_status` | 可选，按 visit 质量过滤 |
| `device_id` | 可选，按设备过滤 |
| `has_waveform` | 可选，`true/false` |

返回字段：

| 字段 | 说明 |
| --- | --- |
| `measurement_id` | 脉诊测量 ID |
| `visit_id` / `modality_record_id` | 平台追溯键 |
| `user_id` / `user_name` | 用户信息 |
| `source_vendor` / `source_measurement_id` | 来源信息 |
| `start_time` / `duration_seconds` | 采集时间与时长 |
| `visit_slot` / `collection_hour` | 离散和连续时间变量 |
| `hand_side` / `pulse_position` | 采集侧别和部位 |
| `device_id` / `device_model` / `source_device_id` | 设备信息 |
| `quality_status` / `quality_flags` | 质量状态 |
| `feature_json` | measurement 级特征摘要 |

### 5.5 `GET /api/pulse/measurements/{measurement_id}`

用途：查询单次脉诊 measurement 详情。

### 5.6 `GET /api/pulse/measurements/{measurement_id}/waveforms`

用途：查询单次测量的波形资产索引和预览点。

返回字段来自 `fact_pulse_waveform_asset`，包括 `channel_name`、`sample_count`、`sampling_rate`、`storage_uri`、`data_format`、`preview_json`、`summary_json`。

### 5.7 `GET /api/pulse/measurements/{measurement_id}/position-features`

用途：查询单次测量的部位级特征明细。

返回字段来自 `fact_pulse_position_feature`，包括 `hand_side`、`pulse_position`、`feature_name`、`feature_value`、`source_field`、`parser_version`、`quality_weight`。

### 5.8 `GET /api/pulse/features`

用途：查询 measurement 级扁平特征行。

Query：

| 参数 | 说明 |
| --- | --- |
| `feature_name` | 可选，按变量名过滤 |

### 5.9 `GET /api/pulse/feature-variables`

用途：查询脉诊变量字典。

返回字段来自 `dim_feature_variable`，包括变量名、中文名、模态、粒度、数据类型、单位、类别、是否可进入机器学习、是否质量字段和合理范围。

## 6. 通用数据集下载 API（规划）

平台应提供模态无关的研究数据下载能力，供脉诊、舌诊、面诊、声诊、多模态融合等独立研究者使用。

规划接口：

```text
POST /api/datasets
POST /api/datasets/{dataset_id}/versions
GET  /api/datasets/{dataset_id}/versions
GET  /api/datasets/{dataset_id}/versions/{version_id}
GET  /api/datasets/{dataset_id}/versions/{version_id}/manifest
GET  /api/datasets/{dataset_id}/versions/{version_id}/files
GET  /api/datasets/{dataset_id}/versions/{version_id}/artifact
```

通用下载包建议包含：

| 文件 | 说明 |
| --- | --- |
| `dataset_card.md` | 数据集说明、用途、限制、脱敏策略 |
| `manifest.jsonl` | 样本级索引，包含 `sample_id`、`user_id`、`visit_id`、模态、资产、质量字段 |
| `visits.parquet` | visit 级元数据 |
| `modality_records.parquet` | 模态记录与结构化 records |
| `feature_wide.parquet` | visit 级宽表 |
| `feature_variables.parquet` | 变量字典 |
| `assets_manifest.jsonl` | 文件资产索引，不直接暴露原始绝对路径 |
| `files/` | 按权限策略打包的原始或标准化资产 |

通用过滤条件应至少支持：

| 参数 | 说明 |
| --- | --- |
| `modalities` | 模态集合，如 `pulse/tongue/face/voice/ask` |
| `source_vendor` | 来源平台 |
| `date_range` | 日期范围 |
| `quality_policy` | 质量过滤策略 |
| `asset_policy` | 是否包含文件资产、预览、原始文件 |
| `deidentify` | 是否脱敏，研究导出默认 true |
| `format` | `jsonl/parquet/csv/zip` |

## 7. Ingest API

### 7.1 `POST /api/ingest/standard-storage`

用途：标准化本地存储相关入口。

### 7.2 `POST /api/ingest/parse-structured-data`

用途：结构化解析相关入口。

## 8. 文档维护要求

后续新增、删除或修改任何接口时，必须同步更新：

1. 本文件的接口表、字段表和展示规则。
2. `docs/开发计划.md` 中的当前 API 与前端路由索引。
3. 如果涉及展示逻辑或数据结构，也要更新 `docs/多模态数据展示平台总体设计.md`。
