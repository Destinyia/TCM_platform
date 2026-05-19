from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://tcm:tcm_password@localhost:5432/tcm_platform",
)
RULE_VERSION = os.getenv("TCM_RULE_VERSION", "cohort_rule_v1_20260422")
STORAGE_ROOT = Path(os.getenv("TCM_STORAGE_ROOT", PROJECT_ROOT / "storage")).resolve()
STORAGE_URI_PREFIX = os.getenv("TCM_STORAGE_URI_PREFIX", "local://tcm-platform")
