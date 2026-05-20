# API 补充：结构化宽表

更新时间：2026-05-20

## `POST /api/ingest/parse-structured-data`

用途：解析数据库中已入库的文件资产，写入 `fact_modality_record.parsed_structured_data_json`，并同步重建 `mart_visit_feature_wide`。

请求示例：

```bash
curl -X POST http://localhost:5000/api/ingest/parse-structured-data \
  -H "Content-Type: application/json" \
  -d '{}'
```

可选参数：

| 参数 | 说明 |
| --- | --- |
| `source_vendor` | 限定来源，例如 `yushengtang` / `zhongke` |
| `visit_id` | 限定单个 visit UUID |
| `source_visit_id` | 限定来源 visit ID |
| `limit` | 限定最多处理 visit 数 |
| `only_missing` | 只解析尚未写入结构化结果的模态 |

响应中 `result.feature_wide_rows` 表示本次重建的 visit 宽表行数。

## `GET /api/demo/visits/{visit_id}`

visit 详情响应新增字段：

```json
{
  "feature_wide": {
    "feature_count": 120,
    "parser_version": "visit_feature_wide_v2",
    "updated_at": "2026-05-20T00:00:00",
    "features": {},
    "groups": {
      "base": {"label": "基础信息", "fields": {}},
      "ask": {"label": "问诊", "fields": {}},
      "pulse": {"label": "脉诊", "fields": {}}
    }
  }
}
```

- `features`：visit 级扁平变量字典，可作为二维宽表横轴。
- `groups`：同一批变量的模态分组形式，供前端折叠展示。

## 脉诊 records 结构

`POST /api/ingest/parse-structured-data` 会在解析脉诊模态时写入：

```json
{
  "modality": "pulse",
  "records": [
    {
      "parser_version": "pulse_record_v1",
      "source_vendor": "yushengtang",
      "source_format": "json",
      "side": "左",
      "pulse_type": "3",
      "pulse_rate": 80,
      "force": 4.0,
      "tension": 50.0,
      "fluency": 13.0,
      "amplitude": 0.07,
      "stability_score": 100.0,
      "waveform_summary": {},
      "waveform_preview": []
    }
  ]
}
```

`GET /api/demo/pulse/records` 返回上述 `records[]`，并补充：

| 字段 | 说明 |
| --- | --- |
| `visit_id` | visit UUID |
| `modality_record_id` | 脉诊模态记录 UUID |
| `user_id` / `user_name` | 用户信息 |
| `source_vendor` | 来源平台 |
| `visit_date` / `visit_time` | 采集日期和时间 |
| `slot` | 早/中/晚时段 |
| `quality_status` | visit 质量状态 |

玉生堂记录可包含 `waveform_preview`，该字段来自波形向量降采样，不是图片缓存。中科记录可包含 `measurements[]`，用于展示六部位测量明细。
