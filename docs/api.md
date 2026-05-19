# 中医四诊数据平台 API 接口文档

## 基础信息

- Base URL: `/api/v1`
- 认证方式: JWT Token (Header: `Authorization: Bearer <token>`)
- 响应格式: JSON

## 通用响应结构

```json
{
  "code": 200,
  "message": "success",
  "data": {}
}
```

---

## 一、认证模块 `/auth`

### 1.1 用户登录
- **POST** `/auth/login`
- Request:
```json
{
  "username": "admin",
  "password": "123456"
}
```
- Response:
```json
{
  "code": 200,
  "data": {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "user": {
      "id": "u001",
      "username": "admin",
      "role": "admin"
    }
  }
}
```

### 1.2 获取当前用户信息
- **GET** `/auth/profile`

### 1.3 退出登录
- **POST** `/auth/logout`

---

## 二、患者管理 `/patients`

### 2.1 患者列表
- **GET** `/patients`
- Query: `page=1&size=20&keyword=张三`
- Response:
```json
{
  "code": 200,
  "data": {
    "total": 100,
    "items": [
      {
        "patient_id": "P20240001",
        "gender": "male",
        "age": 45,
        "exam_count": 3,
        "last_exam_date": "2024-01-15"
      }
    ]
  }
}
```

### 2.2 患者详情
- **GET** `/patients/{patient_id}`

### 2.3 创建患者
- **POST** `/patients`

### 2.4 更新患者
- **PUT** `/patients/{patient_id}`

---

## 三、检查记录 `/examinations`

### 3.1 检查记录列表
- **GET** `/examinations`
- Query: `patient_id=P001&page=1&size=20`

### 3.2 检查记录详情
- **GET** `/examinations/{exam_id}`
- Response:
```json
{
  "code": 200,
  "data": {
    "exam_id": "E20240001",
    "patient_id": "P20240001",
    "exam_date": "2024-01-15",
    "source": "yushengtang",
    "tongue": { "tongue_color": "淡红", "coating_color": "白" },
    "face": { "face_color": "正常" },
    "pulse": { "pulse_type": "弦脉", "rate": 72 },
    "tcm_phenotype": { "syndromes": ["气虚"], "constitution": "气虚质" },
    "biochemical": []
  }
}
```

---

## 四、数据导入 `/import`

### 4.1 获取支持的数据源
- **GET** `/import/sources`

### 4.2 上传数据文件
- **POST** `/import/upload`
- Content-Type: `multipart/form-data`

### 4.3 执行导入任务
- **POST** `/import/execute`

### 4.4 导入历史
- **GET** `/import/history`

---

## 五、数据导出 `/export`

### 5.1 创建导出任务
- **POST** `/export/create`

### 5.2 下载导出文件
- **GET** `/export/download/{task_id}`

### 5.3 导出历史
- **GET** `/export/history`

---

## 六、统计概览 `/dashboard`

### 6.1 获取统计数据
- **GET** `/dashboard/stats`
