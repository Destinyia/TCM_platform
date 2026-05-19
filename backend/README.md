# TCM Platform Backend

This is the first database layer for the multimodal TCM research platform.

## Quick Start

1. Start PostgreSQL:

```powershell
docker compose up -d postgres
```

2. Install Python dependencies:

```powershell
pip install -r requirements.txt
```

3. Copy environment config:

```powershell
Copy-Item .env.example .env
```

4. Initialize schema and seed alias rules:

```powershell
python -m backend.scripts.init_db
```

5. Seed the phase-1 static demo database:

```powershell
python -m backend.scripts.seed_demo_data
```

6. Run the Flask demo API:

```powershell
python -m backend.run
```

The phase-1 frontend reads dynamic data from `http://localhost:5000/api/demo/*`.
When running the frontend in WSL:

```bash
cd /mnt/e/workspace/TCM_platform/frontend
npm install
VITE_API_BASE=http://localhost:5000 npm run dev -- --host 0.0.0.0
```

7. Import the current 20-person validation workbook when moving beyond the static demo:

```powershell
python -m backend.etl.import_cohort_validation
```

## Current Rule Version

`cohort_rule_v1_20260422`

The first import path uses `datasets/organized_checkin_matrix/cohort_checkin_matrix_20251108.xlsx`.
