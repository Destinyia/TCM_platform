# TCM Platform

多模态中医数据治理与展示平台原型。项目采用 Flask 后端、PostgreSQL 数据库和 Vue/Vite 前端，用于整合四诊仪等来源数据，构建标准化本地存储、入库、结构化解析、患者管理、检查记录、打卡矩阵和脉诊分析等功能。

## Project Layout

- `backend/`: Flask API、数据库模型、入库与结构化解析服务。
- `frontend/`: Vue/Vite/Element Plus 前端。
- `scripts/`: 离线数据整理、质量分析和报告生成脚本。
- `sql/`: PostgreSQL 初始化 schema。
- `docs/`: 数据结构、存储结构、平台设计和开发计划文档。
- `config/`: 可追踪的配置样例和规则文件。

## Local Development

```bash
docker compose up -d postgres
pip install -r requirements.txt
python -m backend.scripts.init_db
python -m backend.run
```

Frontend:

```bash
cd frontend
npm install
VITE_API_BASE=http://localhost:5000 npm run dev -- --host 0.0.0.0
```

离线整理并入库：

```bash
python scripts/organize_offline_storage.py
```

仅触发数据库同步和结构化解析：

```bash
python scripts/organize_offline_storage.py --db-sync-only
python scripts/organize_offline_storage.py --parse-only
```

## Data Policy

本仓库只追踪源码、配置样例、SQL 和设计文档。原始数据、标准化存储产物、数据库卷、虚拟环境和前端构建依赖均通过 `.gitignore` 排除。
