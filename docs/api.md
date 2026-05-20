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
- 空单元格显示 `0 / 无效 / -`。
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

## 5. Ingest API

### 5.1 `POST /api/ingest/standard-storage`

用途：标准化本地存储相关入口。

### 5.2 `POST /api/ingest/parse-structured-data`

用途：结构化解析相关入口。

## 6. 文档维护要求

后续新增、删除或修改任何接口时，必须同步更新：

1. 本文件的接口表、字段表和展示规则。
2. `docs/开发计划.md` 中的当前 API 与前端路由索引。
3. 如果涉及展示逻辑或数据结构，也要更新 `docs/多模态数据展示平台总体设计.md`。
