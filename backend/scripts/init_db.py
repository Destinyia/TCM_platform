from __future__ import annotations

import json
import uuid
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert

from backend.app.config import RULE_VERSION
from backend.app.database import SessionLocal, get_engine
from backend.app.models import NameAliasRule

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = PROJECT_ROOT / "sql"
ALIAS_CONFIG = PROJECT_ROOT / "config" / "name_alias_rules_v1.json"


def split_sql_statements(sql_text: str) -> list[str]:
    return [stmt.strip().lstrip("\ufeff") for stmt in sql_text.split(";") if stmt.strip().lstrip("\ufeff")]


def run_sql_files() -> None:
    sql_files = [
        SQL_DIR / "001_initial_multimodal_schema.sql",
        SQL_DIR / "002_name_alias_rule.sql",
        SQL_DIR / "003_demo_support.sql",
        SQL_DIR / "004_visit_feature_wide.sql",
        SQL_DIR / "005_pulse_analysis_phase1.sql",
    ]
    with get_engine().begin() as conn:
        for path in sql_files:
            for stmt in split_sql_statements(path.read_text(encoding="utf-8")):
                conn.exec_driver_sql(stmt)


def seed_alias_rules() -> None:
    payload = json.loads(ALIAS_CONFIG.read_text(encoding="utf-8"))
    rule_version = payload.get("rule_version") or RULE_VERSION
    aliases = payload.get("aliases", {})
    with SessionLocal() as session:
        for raw_name, canonical_name in aliases.items():
            stmt = insert(NameAliasRule).values(
                alias_rule_id=uuid.uuid5(uuid.NAMESPACE_DNS, f"{rule_version}:{raw_name}"),
                rule_version=rule_version,
                source_vendor="zhongke",
                raw_name=raw_name,
                canonical_name=canonical_name,
                is_active=True,
                note="seeded from config/name_alias_rules_v1.json",
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["rule_version", "raw_name"],
                set_={
                    "canonical_name": canonical_name,
                    "is_active": True,
                    "note": "seeded from config/name_alias_rules_v1.json",
                },
            )
            session.execute(stmt)
        session.commit()


def main() -> None:
    run_sql_files()
    seed_alias_rules()
    print("Database schema initialized.")
    print(f"Seeded alias rules for {RULE_VERSION}.")


if __name__ == "__main__":
    main()
