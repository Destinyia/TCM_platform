from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.models import FileAsset, ModalityRecord, QualityEvent, User, UserDayPanel, UserIdentityMap, Visit

DEFAULT_RULE_VERSION = "standard_storage_loader_v1"
DEFAULT_PIPELINE_VERSION = "offline_storage_v1"
MODALITIES = ["ask", "pulse", "tongue", "face", "voice", "report"]


def stable_uuid(value: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"tcm-platform:{value}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def visit_quality_status(value: str | None) -> str:
    mapping = {
        "complete": "valid",
        "incomplete": "incomplete",
        "duplicate": "suspicious",
        "suspicious": "suspicious",
        "valid": "valid",
    }
    return mapping.get(str(value or "").strip(), str(value or "valid"))


def source_user_key(record: dict[str, Any]) -> str:
    return f"{record.get('source_vendor')}:{record.get('canonical_name') or 'unknown'}"


def source_record_group_id(record: dict[str, Any]) -> str:
    return str(record.get("source_record_group_id") or f"{record.get('source_vendor')}:{record.get('source_visit_id')}")


def visit_source_id(record: dict[str, Any]) -> str:
    # fact_visit currently has a unique constraint on (source_vendor, source_visit_id).
    # Use source_record_group_id so Zhongke same-case multi-time clusters remain distinct.
    return source_record_group_id(record)


def upsert_user(session: Session, record: dict[str, Any]) -> uuid.UUID:
    name = str(record.get("canonical_name") or "").strip() or "未知用户"
    user_uuid = stable_uuid(f"user:{name}")
    stmt = insert(User).values(
        user_id=user_uuid,
        cohort_id="2026-04 离线整理",
        canonical_name=name,
        primary_phone="",
        status="active",
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["canonical_name", "primary_phone"],
        set_={"cohort_id": "2026-04 离线整理", "status": "active"},
    )
    user_id = session.execute(stmt.returning(User.user_id)).scalar_one()

    identity_stmt = insert(UserIdentityMap).values(
        identity_map_id=stable_uuid(f"identity:{record.get('source_vendor')}:{name}"),
        user_id=user_id,
        source_vendor=record.get("source_vendor"),
        raw_name=name,
        canonical_name=name,
        phone="",
        source_user_key=source_user_key(record),
        confidence=1.0,
        is_manual_verified=False,
        rule_version=parser_rule_version(record),
    )
    identity_stmt = identity_stmt.on_conflict_do_update(
        index_elements=["source_vendor", "source_user_key"],
        set_={"user_id": user_id, "canonical_name": name, "rule_version": parser_rule_version(record)},
    )
    session.execute(identity_stmt)
    return user_id


def parser_rule_version(record: dict[str, Any]) -> str:
    parser = record.get("parser") or {}
    return str(parser.get("rule_version") or DEFAULT_RULE_VERSION)


def upsert_visit(session: Session, record: dict[str, Any], user_id: uuid.UUID) -> uuid.UUID:
    visit_time = parse_dt(record.get("collected_at"))
    modalities = set(record.get("modalities") or [])
    missing = [modality for modality in MODALITIES if modality not in modalities]
    flags = record.get("quality_flags") or []
    quality_status = visit_quality_status(record.get("quality_status"))
    source_visit_id = visit_source_id(record)
    stmt = insert(Visit).values(
        visit_id=stable_uuid(f"visit:{record.get('source_vendor')}:{source_visit_id}"),
        user_id=user_id,
        source_vendor=record.get("source_vendor"),
        source_visit_id=source_visit_id,
        source_user_key=source_user_key(record),
        visit_time=visit_time,
        visit_date=visit_time.date() if visit_time else None,
        visit_slot=record.get("time_window_slot") or None,
        quality_status=quality_status,
        is_complete_visit=quality_status == "valid",
        missing_modalities={"modalities": missing},
        is_suspected_cheat=quality_status in {"suspicious", "duplicate"},
        cheat_types={
            "flags": flags,
            "source_record_group_id": source_record_group_id(record),
            "raw_source_visit_id": record.get("source_visit_id"),
        },
        duplicate_numeric_flag=quality_status in {"suspicious", "duplicate"},
        duplicate_numeric_type="offline_rule" if quality_status in {"suspicious", "duplicate"} else None,
        rule_version=parser_rule_version(record),
        pipeline_version=DEFAULT_PIPELINE_VERSION,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_vendor", "source_visit_id"],
        set_={
            "user_id": user_id,
            "visit_time": visit_time,
            "visit_date": visit_time.date() if visit_time else None,
            "visit_slot": record.get("time_window_slot") or None,
            "quality_status": quality_status,
            "is_complete_visit": quality_status == "valid",
            "missing_modalities": {"modalities": missing},
            "cheat_types": {
                "flags": flags,
                "source_record_group_id": source_record_group_id(record),
                "raw_source_visit_id": record.get("source_visit_id"),
            },
            "rule_version": parser_rule_version(record),
            "pipeline_version": DEFAULT_PIPELINE_VERSION,
        },
    )
    return session.execute(stmt.returning(Visit.visit_id)).scalar_one()


def upsert_modalities(session: Session, record: dict[str, Any], visit_id: uuid.UUID) -> dict[str, uuid.UUID]:
    present = set(record.get("modalities") or [])
    ids = {}
    for modality in sorted(present | set(MODALITIES)):
        if modality not in MODALITIES:
            continue
        exists = modality in present
        modality_uuid = stable_uuid(f"modality:{visit_id}:{modality}")
        stmt = insert(ModalityRecord).values(
            modality_record_id=modality_uuid,
            visit_id=visit_id,
            modality_type=modality,
            source_vendor=record.get("source_vendor"),
            exists_flag=exists,
            is_required=modality in {"ask", "pulse", "tongue", "face"},
            is_complete=exists,
            completion_status="present" if exists else "missing",
            quality_flags_json={"flags": record.get("quality_flags") or []},
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["visit_id", "modality_type", "source_vendor"],
            set_={
                "exists_flag": exists,
                "is_complete": exists,
                "completion_status": "present" if exists else "missing",
                "quality_flags_json": {"flags": record.get("quality_flags") or []},
            },
        )
        ids[modality] = session.execute(stmt.returning(ModalityRecord.modality_record_id)).scalar_one()
    return ids


def upsert_assets(session: Session, assets: list[dict[str, Any]], visit_ids: dict[str, uuid.UUID], modality_ids: dict[str, dict[str, uuid.UUID]]) -> int:
    count = 0
    for asset in assets:
        record_id = str(asset.get("source_record_group_id") or "")
        visit_id = visit_ids.get(record_id)
        if not visit_id:
            continue
        modality = str(asset.get("modality") or "")
        asset_uuid = uuid.UUID(str(asset["asset_id"]))
        session.execute(delete(FileAsset).where(FileAsset.asset_id == asset_uuid))
        session.execute(
            insert(FileAsset).values(
                asset_id=asset_uuid,
                visit_id=visit_id,
                modality_record_id=modality_ids.get(record_id, {}).get(modality),
                asset_type=asset.get("asset_type"),
                asset_role=asset.get("asset_role"),
                file_name=asset.get("file_name"),
                file_path=asset.get("file_path"),
                storage_uri=asset.get("storage_uri"),
                file_hash=asset.get("file_hash"),
                file_size=asset.get("file_size"),
                mime_type=asset.get("mime_type"),
                created_at_from_file=parse_dt(asset.get("created_at_from_file")),
                parsed_success_flag=asset.get("parsed_success_flag"),
            )
        )
        count += 1
    return count


def replace_quality_events(session: Session, records: list[dict[str, Any]], visit_ids: dict[str, uuid.UUID]) -> int:
    rule_versions = {parser_rule_version(record) for record in records}
    for rule_version in rule_versions:
        session.execute(delete(QualityEvent).where(QualityEvent.rule_version == rule_version))
    count = 0
    seen_event_ids: set[uuid.UUID] = set()
    for record in records:
        visit_id = visit_ids[source_record_group_id(record)]
        for flag in record.get("quality_flags") or []:
            flag = str(flag).strip()
            if not flag:
                continue
            event_id = stable_uuid(f"quality:{visit_id}:{flag}")
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            session.execute(
                insert(QualityEvent)
                .values(
                    quality_event_id=event_id,
                    entity_type="visit",
                    entity_id=str(visit_id),
                    quality_flag=flag[:200],
                    severity="warning" if visit_quality_status(record.get("quality_status")) != "valid" else "info",
                    status="open",
                    rule_version=parser_rule_version(record),
                    evidence_json={"source_record_group_id": source_record_group_id(record), "text": flag},
                )
                .on_conflict_do_update(
                    index_elements=["quality_event_id"],
                    set_={
                        "entity_type": "visit",
                        "entity_id": str(visit_id),
                        "quality_flag": flag[:200],
                        "severity": "warning" if visit_quality_status(record.get("quality_status")) != "valid" else "info",
                        "status": "open",
                        "rule_version": parser_rule_version(record),
                        "evidence_json": {"source_record_group_id": source_record_group_id(record), "text": flag},
                    },
                )
            )
            count += 1
    return count


def rebuild_panels(session: Session, records: list[dict[str, Any]], users: dict[str, uuid.UUID], visit_ids: dict[str, uuid.UUID]) -> int:
    for user_id in set(users.values()):
        session.execute(delete(UserDayPanel).where(UserDayPanel.user_id == user_id))
    grouped: dict[tuple[uuid.UUID, Any, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        visit_time = parse_dt(record.get("collected_at"))
        slot = str(record.get("time_window_slot") or "").strip()
        if not visit_time or not slot:
            continue
        grouped[(users[source_record_group_id(record)], visit_time.date(), slot)].append(record)
    count = 0
    for (user_id, visit_date, slot), group in grouped.items():
        primary = sorted(group, key=lambda item: len(item.get("modalities") or []), reverse=True)[0]
        statuses = {visit_quality_status(item.get("quality_status")) for item in group}
        available = sorted({modality for item in group for modality in item.get("modalities") or []})
        session.execute(
            insert(UserDayPanel).values(
                panel_id=stable_uuid(f"panel:{user_id}:{visit_date}:{slot}"),
                user_id=user_id,
                visit_date=visit_date,
                visit_slot=slot,
                primary_visit_id=visit_ids[source_record_group_id(primary)],
                device_count=len({item.get("source_vendor") for item in group}),
                available_modalities={modality: modality in available for modality in MODALITIES},
                quality_status="suspicious" if "suspicious" in statuses else "incomplete" if "incomplete" in statuses else "valid",
                is_complete_visit=all(modality in available for modality in ["ask", "pulse", "tongue"]),
                is_suspected_cheat="suspicious" in statuses,
                duplicate_numeric_flag="suspicious" in statuses,
            )
        )
        count += 1
    return count


def load_standard_storage(session: Session, records_path: Path, assets_path: Path | None = None) -> dict[str, int | str]:
    records = read_jsonl(records_path)
    assets = read_jsonl(assets_path) if assets_path and assets_path.exists() else []
    users: dict[str, uuid.UUID] = {}
    visit_ids: dict[str, uuid.UUID] = {}
    modality_ids: dict[str, dict[str, uuid.UUID]] = {}
    for record in records:
        record_id = source_record_group_id(record)
        user_id = upsert_user(session, record)
        visit_id = upsert_visit(session, record, user_id)
        users[record_id] = user_id
        visit_ids[record_id] = visit_id
        modality_ids[record_id] = upsert_modalities(session, record, visit_id)
    asset_count = upsert_assets(session, assets, visit_ids, modality_ids)
    quality_count = replace_quality_events(session, records, visit_ids)
    panel_count = rebuild_panels(session, records, users, visit_ids)
    return {
        "records_path": str(records_path),
        "assets_path": str(assets_path) if assets_path else "",
        "users": len(set(users.values())),
        "visits": len(visit_ids),
        "modalities": sum(len(value) for value in modality_ids.values()),
        "assets": asset_count,
        "quality_events": quality_count,
        "panels": panel_count,
    }
