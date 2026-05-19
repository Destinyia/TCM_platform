from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from backend.app.config import RULE_VERSION
from backend.app.database import SessionLocal, get_engine
from backend.app.models import FileAsset, ModalityRecord, User, UserDayPanel, UserIdentityMap, Visit

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKBOOK = PROJECT_ROOT / "datasets" / "organized_checkin_matrix" / "cohort_checkin_matrix_20251108.xlsx"
ID_MAPPING = PROJECT_ROOT / "datasets" / "id_mapping" / "cohort_20_name_to_ids.csv"

SOURCE_COLUMNS = {
    "zhongke": {
        "visit_ids": "中科_病例号",
        "modalities": {
            "ask": ("中科_问诊", "中科_问诊路径"),
            "pulse": ("中科_脉诊波形", "中科_脉诊路径"),
            "tongue": ("中科_舌诊图片", "中科_舌诊路径"),
            "face": ("中科_面诊图片", "中科_面诊路径"),
        },
    },
    "yushengtang": {
        "visit_ids": "玉生堂_TreatNumber",
        "modalities": {
            "ask": ("玉生堂_问诊", "玉生堂_问诊路径"),
            "pulse": ("玉生堂_脉诊波形", "玉生堂_脉诊路径"),
            "tongue": ("玉生堂_舌诊图片", "玉生堂_舌诊路径"),
            "voice": ("玉生堂_wav", "玉生堂_wav路径"),
        },
    },
}


@dataclass(frozen=True)
class SourceIdentity:
    phone: str | None
    source_user_key: str | None


def clean_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def split_ids(value: object) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,|]", text) if part.strip()]


def load_identity_lookup() -> dict[tuple[str, str], SourceIdentity]:
    if not ID_MAPPING.exists():
        return {}
    frame = pd.read_csv(ID_MAPPING, dtype=str).fillna("")
    lookup: dict[tuple[str, str], SourceIdentity] = {}
    for _, row in frame.iterrows():
        name = clean_text(row.get("roster_name"))
        for vendor, phone_col in (("zhongke", "zhongke_phone"), ("yushengtang", "yst_phone")):
            phones = split_ids(row.get(phone_col))
            primary_phone = next((phone for phone in phones if len(phone) == 11), phones[0] if phones else "")
            if primary_phone:
                lookup[(vendor, name)] = SourceIdentity(
                    phone=primary_phone,
                    source_user_key=f"{name}+{primary_phone}",
                )
    return lookup


def upsert_user(session, name: str, identity: SourceIdentity | None) -> User:
    phone = identity.phone if identity else None
    existing = session.execute(
        select(User).where(User.canonical_name == name, User.primary_phone == phone)
    ).scalar_one_or_none()
    if existing:
        return existing
    user = User(canonical_name=name, primary_phone=phone, cohort_id="cohort_2025_11_20", status="active")
    session.add(user)
    session.flush()
    return user


def upsert_identity(session, user: User, vendor: str, name: str, identity: SourceIdentity | None) -> None:
    source_user_key = identity.source_user_key if identity and identity.source_user_key else f"{name}+unknown"
    stmt = insert(UserIdentityMap).values(
        user_id=user.user_id,
        source_vendor=vendor,
        raw_name=name,
        canonical_name=name,
        phone=identity.phone if identity else None,
        source_user_key=source_user_key,
        confidence=1.0 if identity and identity.phone else 0.5,
        is_manual_verified=False,
        rule_version=RULE_VERSION,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_vendor", "source_user_key"],
        set_={
            "user_id": user.user_id,
            "canonical_name": name,
            "phone": identity.phone if identity else None,
            "rule_version": RULE_VERSION,
        },
    )
    session.execute(stmt)


def quality_flags(row: pd.Series) -> list[str]:
    flags: list[str] = []
    status = clean_text(row.get("状态"))
    remark = clean_text(row.get("备注"))
    if status == "incomplete":
        flags.append("missing_modality")
    if status == "suspicious":
        flags.append("suspicious")
    if clean_text(row.get("疑似重复数值")):
        flags.append("duplicate_numeric")
    if clean_text(row.get("姓名不一致")):
        flags.append("name_mismatch")
    if "姓名别名已归一" in remark:
        flags.append("name_alias_mapped")
    return flags


def import_workbook() -> None:
    get_engine()
    detail = pd.read_excel(WORKBOOK, sheet_name="详细记录", dtype=str).fillna("")
    identity_lookup = load_identity_lookup()
    with SessionLocal() as session:
        for _, row in detail.iterrows():
            name = clean_text(row["姓名"])
            visit_date = pd.to_datetime(row["日期"]).date()
            visit_time = pd.to_datetime(f"{visit_date} {clean_text(row['具体时间'])}")
            slot = clean_text(row["时段"])
            status = clean_text(row["状态"])
            flags = quality_flags(row)
            user = upsert_user(session, name, identity_lookup.get(("zhongke", name)) or identity_lookup.get(("yushengtang", name)))

            for vendor, spec in SOURCE_COLUMNS.items():
                source_visit_ids = split_ids(row.get(spec["visit_ids"]))
                if not source_visit_ids:
                    continue
                identity = identity_lookup.get((vendor, name))
                upsert_identity(session, user, vendor, name, identity)
                synthetic_source_visit_id = "+".join(source_visit_ids)
                stmt = insert(Visit).values(
                    user_id=user.user_id,
                    source_vendor=vendor,
                    source_visit_id=synthetic_source_visit_id,
                    source_user_key=identity.source_user_key if identity else f"{name}+unknown",
                    visit_time=visit_time.to_pydatetime(),
                    visit_date=visit_date,
                    visit_slot=slot,
                    visit_sequence_in_day={"早": 1, "中": 2, "晚": 3}.get(slot),
                    quality_status=status,
                    is_complete_visit=status == "complete",
                    missing_modalities={"remark": clean_text(row.get("备注"))},
                    is_suspected_cheat=status == "suspicious",
                    cheat_types={"flags": flags},
                    duplicate_numeric_flag="duplicate_numeric" in flags,
                    duplicate_numeric_type="validation_sheet",
                    rule_version=RULE_VERSION,
                    pipeline_version="cohort_validation_import_v1",
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["source_vendor", "source_visit_id"],
                    set_={
                        "user_id": user.user_id,
                        "visit_time": visit_time.to_pydatetime(),
                        "visit_date": visit_date,
                        "visit_slot": slot,
                        "quality_status": status,
                        "rule_version": RULE_VERSION,
                    },
                ).returning(Visit.visit_id)
                visit_id = session.execute(stmt).scalar_one()

                modality_payload: dict[str, bool] = {}
                for modality, (exists_col, path_col) in spec["modalities"].items():
                    exists = bool(clean_text(row.get(exists_col)))
                    modality_payload[modality] = exists
                    mod_stmt = insert(ModalityRecord).values(
                        visit_id=visit_id,
                        modality_type=modality,
                        source_vendor=vendor,
                        exists_flag=exists,
                        is_required=True,
                        is_complete=exists,
                        completion_status="present" if exists else "missing",
                        quality_flags_json={"flags": flags},
                    )
                    mod_stmt = mod_stmt.on_conflict_do_update(
                        index_elements=["visit_id", "modality_type", "source_vendor"],
                        set_={
                            "exists_flag": exists,
                            "is_complete": exists,
                            "completion_status": "present" if exists else "missing",
                            "quality_flags_json": {"flags": flags},
                        },
                    ).returning(ModalityRecord.modality_record_id)
                    modality_record_id = session.execute(mod_stmt).scalar_one()
                    file_path = clean_text(row.get(path_col))
                    if file_path:
                        path = Path(file_path)
                        session.add(
                            FileAsset(
                                visit_id=visit_id,
                                modality_record_id=modality_record_id,
                                asset_type=path.suffix.lower().lstrip(".") or None,
                                asset_role=f"{vendor}_{modality}",
                                file_name=path.name,
                                file_path=file_path,
                                parsed_success_flag=True,
                            )
                        )

                panel_stmt = insert(UserDayPanel).values(
                    user_id=user.user_id,
                    visit_date=visit_date,
                    visit_slot=slot,
                    primary_visit_id=visit_id,
                    device_count=int(clean_text(row.get("设备数")) or 1),
                    available_modalities=modality_payload,
                    quality_status=status,
                    is_complete_visit=status == "complete",
                    is_suspected_cheat=status == "suspicious",
                    duplicate_numeric_flag="duplicate_numeric" in flags,
                )
                panel_stmt = panel_stmt.on_conflict_do_update(
                    index_elements=["user_id", "visit_date", "visit_slot"],
                    set_={
                        "primary_visit_id": visit_id,
                        "device_count": int(clean_text(row.get("设备数")) or 1),
                        "available_modalities": modality_payload,
                        "quality_status": status,
                        "is_complete_visit": status == "complete",
                        "is_suspected_cheat": status == "suspicious",
                        "duplicate_numeric_flag": "duplicate_numeric" in flags,
                    },
                )
                session.execute(panel_stmt)
        session.commit()


def main() -> None:
    import_workbook()
    print(f"Imported cohort validation workbook: {WORKBOOK}")


if __name__ == "__main__":
    main()
