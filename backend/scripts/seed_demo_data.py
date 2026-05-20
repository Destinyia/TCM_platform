from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from backend.app.config import RULE_VERSION
from backend.app.database import SessionLocal, get_engine
from backend.app.models import (
    Device,
    DatasetVersion,
    FeatureVariable,
    FileAsset,
    ModalityRecord,
    PulseMeasurement,
    PulsePositionFeature,
    PulseWaveformAsset,
    QualityEvent,
    User,
    UserDayPanel,
    UserIdentityMap,
    Visit,
)

DEMO_RULE_VERSION = f"{RULE_VERSION}_static_demo"


def demo_uuid(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"tcm-platform-demo:{name}")


USERS = [
    {"user_id": "U001", "display_id": "DEID-001", "name": "爱丽娜", "sex": "女", "age": 36, "phone": "13900000001", "cohort": "2026Q1 随访"},
    {"user_id": "U002", "display_id": "DEID-002", "name": "张雨楠", "sex": "女", "age": 29, "phone": "13900000002", "cohort": "2026Q1 随访"},
    {"user_id": "U003", "display_id": "DEID-003", "name": "李昱霖", "sex": "男", "age": 42, "phone": "13900000003", "cohort": "2026Q1 随访"},
    {"user_id": "U004", "display_id": "DEID-004", "name": "蒋广祥", "sex": "男", "age": 51, "phone": "13900000004", "cohort": "2026Q1 随访"},
]

VISITS = [
    {
        "visit_id": "V001",
        "user_id": "U001",
        "source_vendor": "zhongke",
        "source_visit_id": "ZK-20260415001",
        "source_record_group_id": "zhongke-ZK-20260415001-U001-0802",
        "visit_time": "2026-04-15 08:02",
        "slot": "早",
        "sequence": 1,
        "quality_status": "valid",
        "modalities": ["ask", "pulse", "tongue", "face", "report"],
        "missing": [],
        "quality_flags": ["source_caseid_time_cluster_5m"],
    },
    {
        "visit_id": "V002",
        "user_id": "U001",
        "source_vendor": "yushengtang",
        "source_visit_id": "2026041514221800101",
        "source_record_group_id": "yst-2026041514221800101",
        "visit_time": "2026-04-15 14:22",
        "slot": "中",
        "sequence": 2,
        "quality_status": "valid",
        "modalities": ["ask", "pulse", "tongue", "voice", "report"],
        "missing": ["face"],
        "quality_flags": [],
    },
    {
        "visit_id": "V003",
        "user_id": "U001",
        "source_vendor": "zhongke",
        "source_visit_id": "ZK-20260415103",
        "source_record_group_id": "zhongke-ZK-20260415103-U001-1951",
        "visit_time": "2026-04-15 19:51",
        "slot": "晚",
        "sequence": 3,
        "quality_status": "valid",
        "modalities": ["ask", "pulse", "tongue", "face"],
        "missing": ["report"],
        "quality_flags": [],
    },
    {
        "visit_id": "V004",
        "user_id": "U002",
        "source_vendor": "yushengtang",
        "source_visit_id": "2026041508274600201",
        "source_record_group_id": "yst-2026041508274600201",
        "visit_time": "2026-04-15 08:27",
        "slot": "早",
        "sequence": 1,
        "quality_status": "suspicious",
        "modalities": ["ask", "pulse", "tongue", "voice", "report"],
        "missing": [],
        "quality_flags": ["duplicate_numeric_similar", "triplicate_within_10m"],
    },
    {
        "visit_id": "V005",
        "user_id": "U002",
        "source_vendor": "zhongke",
        "source_visit_id": "ZK-20260415115",
        "source_record_group_id": "zhongke-ZK-20260415115-U002-1431",
        "visit_time": "2026-04-15 14:31",
        "slot": "中",
        "sequence": 2,
        "quality_status": "valid",
        "modalities": ["ask", "pulse", "tongue", "face"],
        "missing": ["report"],
        "quality_flags": ["name_alias_mapped"],
    },
    {
        "visit_id": "V006",
        "user_id": "U003",
        "source_vendor": "yushengtang",
        "source_visit_id": "2026041419010500301",
        "source_record_group_id": "yst-2026041419010500301",
        "visit_time": "2026-04-14 19:01",
        "slot": "晚",
        "sequence": 2,
        "quality_status": "incomplete",
        "modalities": ["pulse", "tongue", "report"],
        "missing": ["ask", "voice", "face"],
        "quality_flags": ["missing_modality"],
    },
    {
        "visit_id": "V007",
        "user_id": "U004",
        "source_vendor": "zhongke",
        "source_visit_id": "ZK-20260413018",
        "source_record_group_id": "zhongke-ZK-20260413018-U004-0818",
        "visit_time": "2026-04-13 08:18",
        "slot": "早",
        "sequence": 1,
        "quality_status": "valid",
        "modalities": ["ask", "pulse", "tongue", "face"],
        "missing": ["report"],
        "quality_flags": [],
    },
    {
        "visit_id": "V008",
        "user_id": "U004",
        "source_vendor": "zhongke",
        "source_visit_id": "ZK-20260413088",
        "source_record_group_id": "zhongke-ZK-20260413088-U004-1508",
        "visit_time": "2026-04-13 15:08",
        "slot": "中",
        "sequence": 2,
        "quality_status": "valid",
        "modalities": ["ask", "pulse", "tongue", "face", "report"],
        "missing": [],
        "quality_flags": [],
    },
]

PULSE_RECORDS = [
    {"record_id": "P001", "visit_id": "V001", "side": "left", "pulse_type": "弦细", "pulse_rate": 72, "force": 62, "tension": 68, "fluency": 74, "amplitude": 0.82, "h1": 0.74, "h3": 0.41, "w": 0.36, "as": 0.57, "ad": 0.43, "stability_score": 88, "included": True},
    {"record_id": "P002", "visit_id": "V001", "side": "right", "pulse_type": "弦细", "pulse_rate": 73, "force": 64, "tension": 69, "fluency": 73, "amplitude": 0.84, "h1": 0.75, "h3": 0.42, "w": 0.35, "as": 0.58, "ad": 0.44, "stability_score": 87, "included": True},
    {"record_id": "P003", "visit_id": "V002", "side": "left", "pulse_type": "滑", "pulse_rate": 78, "force": 70, "tension": 63, "fluency": 81, "amplitude": 0.91, "h1": 0.81, "h3": 0.48, "w": 0.39, "as": 0.63, "ad": 0.49, "stability_score": 82, "included": True},
    {"record_id": "P004", "visit_id": "V003", "side": "left", "pulse_type": "沉弦", "pulse_rate": 69, "force": 58, "tension": 72, "fluency": 66, "amplitude": 0.76, "h1": 0.69, "h3": 0.39, "w": 0.34, "as": 0.51, "ad": 0.39, "stability_score": 79, "included": True},
    {"record_id": "P005", "visit_id": "V004", "side": "left", "pulse_type": "滑数", "pulse_rate": 86, "force": 76, "tension": 61, "fluency": 84, "amplitude": 1.02, "h1": 0.88, "h3": 0.54, "w": 0.43, "as": 0.68, "ad": 0.53, "stability_score": 62, "included": False},
    {"record_id": "P006", "visit_id": "V004", "side": "right", "pulse_type": "滑数", "pulse_rate": 87, "force": 75, "tension": 62, "fluency": 83, "amplitude": 1.01, "h1": 0.87, "h3": 0.53, "w": 0.43, "as": 0.67, "ad": 0.52, "stability_score": 61, "included": False},
    {"record_id": "P007", "visit_id": "V005", "side": "left", "pulse_type": "弦", "pulse_rate": 80, "force": 68, "tension": 74, "fluency": 70, "amplitude": 0.89, "h1": 0.78, "h3": 0.47, "w": 0.38, "as": 0.61, "ad": 0.46, "stability_score": 77, "included": True},
    {"record_id": "P008", "visit_id": "V006", "side": "left", "pulse_type": "沉细", "pulse_rate": 64, "force": 52, "tension": 70, "fluency": 61, "amplitude": 0.68, "h1": 0.61, "h3": 0.34, "w": 0.31, "as": 0.47, "ad": 0.35, "stability_score": 73, "included": True},
    {"record_id": "P009", "visit_id": "V007", "side": "left", "pulse_type": "沉", "pulse_rate": 66, "force": 57, "tension": 65, "fluency": 64, "amplitude": 0.72, "h1": 0.64, "h3": 0.36, "w": 0.33, "as": 0.49, "ad": 0.37, "stability_score": 81, "included": True},
    {"record_id": "P010", "visit_id": "V008", "side": "left", "pulse_type": "弦", "pulse_rate": 71, "force": 63, "tension": 70, "fluency": 68, "amplitude": 0.78, "h1": 0.71, "h3": 0.41, "w": 0.35, "as": 0.54, "ad": 0.42, "stability_score": 84, "included": True},
]

ASSETS = [
    {"asset_id": "A001", "visit_id": "V001", "asset_type": "tongue_origin", "modality": "tongue", "file_name": "tongue_origin.jpg", "training": True, "parse_status": "ok"},
    {"asset_id": "A002", "visit_id": "V001", "asset_type": "pulse_raw_left", "modality": "pulse", "file_name": "left", "training": True, "parse_status": "ok"},
    {"asset_id": "A003", "visit_id": "V002", "asset_type": "voice_wav", "modality": "voice", "file_name": "a.wav", "training": True, "parse_status": "ok"},
    {"asset_id": "A004", "visit_id": "V006", "asset_type": "report_pdf", "modality": "report", "file_name": "2026041419010500301.pdf", "training": False, "parse_status": "partial"},
    {"asset_id": "A005", "visit_id": "V001", "asset_type": "recommendation_material", "modality": "prescription", "file_name": "nei_guan.jpg", "training": False, "parse_status": "ok"},
]

QUALITY_EVENTS = [
    {"id": "Q001", "entity": "visit", "target": "V004", "flag": "triplicate_within_10m", "severity": "warning", "status": "open", "evidence": "同一用户 10 分钟内出现多次相似脉诊数值"},
    {"id": "Q002", "entity": "visit", "target": "V006", "flag": "missing_modality", "severity": "warning", "status": "open", "evidence": "缺失问诊、声诊、面诊"},
    {"id": "Q003", "entity": "visit", "target": "V001", "flag": "source_caseid_time_cluster_5m", "severity": "info", "status": "resolved", "evidence": "中科同病例号 5 分钟内合并多模态采集"},
    {"id": "Q004", "entity": "asset", "target": "A005", "flag": "training_excluded", "severity": "info", "status": "resolved", "evidence": "穴位建议图，不进入图像训练集"},
]

DATASET_VERSIONS = [
    {"dataset_id": "DS-PULSE-001", "version": "v2026.05.demo.001", "task_type": "pulse_feature_analysis", "status": "ready", "samples": 8, "users": 4, "split_strategy": "by_user", "modalities": ["pulse"], "quality_policy": "exclude suspicious pulse duplicates"},
    {"dataset_id": "DS-MM-001", "version": "v2026.05.demo.002", "task_type": "multimodal_constitution", "status": "draft", "samples": 6, "users": 3, "split_strategy": "by_user", "modalities": ["ask", "pulse", "tongue", "face"], "quality_policy": "valid + incomplete with explicit missing flags"},
]

DEVICES = [
    {"source_vendor": "zhongke", "source_device_id": "zhongke-demo-device", "device_model": "中科四诊仪 Demo", "sensor_type": "pulse_pressure", "sampling_rate": 100},
    {"source_vendor": "yushengtang", "source_device_id": "yst-demo-device", "device_model": "玉生堂四诊仪 Demo", "sensor_type": "pulse_pressure", "sampling_rate": 100},
]

PULSE_FEATURE_VARIABLES = [
    {"feature_name": "pulse_rate", "display_name": "脉率", "unit": "bpm", "category": "time_domain", "is_ml_feature": True},
    {"feature_name": "force", "display_name": "脉力", "unit": None, "category": "pulse_observation", "is_ml_feature": True},
    {"feature_name": "tension", "display_name": "紧张度", "unit": None, "category": "pulse_observation", "is_ml_feature": True},
    {"feature_name": "fluency", "display_name": "流利度", "unit": None, "category": "pulse_observation", "is_ml_feature": True},
    {"feature_name": "amplitude", "display_name": "幅值", "unit": None, "category": "time_domain", "is_ml_feature": True},
    {"feature_name": "stability_score", "display_name": "稳定性评分", "unit": "score", "category": "quality", "is_ml_feature": True, "is_quality_feature": True},
    {"feature_name": "h1", "display_name": "主波幅 h1", "unit": None, "category": "morphology", "is_ml_feature": True},
    {"feature_name": "h3", "display_name": "重搏前波 h3", "unit": None, "category": "morphology", "is_ml_feature": True},
    {"feature_name": "w", "display_name": "脉宽 W", "unit": None, "category": "morphology", "is_ml_feature": True},
    {"feature_name": "as", "display_name": "收缩期面积 As", "unit": None, "category": "morphology", "is_ml_feature": True},
    {"feature_name": "ad", "display_name": "舒张期面积 Ad", "unit": None, "category": "morphology", "is_ml_feature": True},
]


def parse_visit_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def seed_users(session) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for item in USERS:
        user_uuid = demo_uuid(item["user_id"])
        stmt = insert(User).values(
            user_id=user_uuid,
            cohort_id=item["cohort"],
            canonical_name=item["name"],
            sex=item["sex"],
            primary_phone=item["phone"],
            status="active",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["canonical_name", "primary_phone"],
            set_={
                "cohort_id": item["cohort"],
                "sex": item["sex"],
                "status": "active",
            },
        )
        actual_user_id = session.execute(stmt.returning(User.user_id)).scalar_one()
        ids[item["user_id"]] = actual_user_id
        for vendor in ("zhongke", "yushengtang"):
            identity_stmt = insert(UserIdentityMap).values(
                identity_map_id=demo_uuid(f"identity:{vendor}:{item['user_id']}"),
                user_id=actual_user_id,
                source_vendor=vendor,
                raw_name=item["name"],
                canonical_name=item["name"],
                phone=item["phone"],
                source_user_key=f"{item['name']}+{item['phone']}",
                confidence=1.0,
                is_manual_verified=False,
                rule_version=DEMO_RULE_VERSION,
            )
            identity_stmt = identity_stmt.on_conflict_do_update(
                index_elements=["source_vendor", "source_user_key"],
                set_={"user_id": actual_user_id, "rule_version": DEMO_RULE_VERSION},
            )
            session.execute(identity_stmt)
    return ids


def seed_visits(session, user_ids: dict[str, uuid.UUID]) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for item in VISITS:
        visit_uuid = demo_uuid(item["visit_id"])
        visit_time = parse_visit_time(item["visit_time"])
        missing = item["missing"]
        flags = item["quality_flags"]
        stmt = insert(Visit).values(
            visit_id=visit_uuid,
            user_id=user_ids[item["user_id"]],
            source_vendor=item["source_vendor"],
            source_visit_id=item["source_visit_id"],
            source_user_key=f"{next(user['name'] for user in USERS if user['user_id'] == item['user_id'])}+{next(user['phone'] for user in USERS if user['user_id'] == item['user_id'])}",
            visit_time=visit_time,
            visit_date=visit_time.date(),
            visit_slot=item["slot"],
            visit_sequence_in_day=item["sequence"],
            quality_status=item["quality_status"],
            is_complete_visit=not missing,
            missing_modalities={"modalities": missing},
            is_suspected_cheat=item["quality_status"] == "suspicious",
            cheat_types={"flags": flags, "source_record_group_id": item["source_record_group_id"]},
            duplicate_numeric_flag="duplicate_numeric_similar" in flags,
            duplicate_numeric_type="demo_static" if "duplicate_numeric_similar" in flags else None,
            rule_version=DEMO_RULE_VERSION,
            pipeline_version="static_demo_seed_v1",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_vendor", "source_visit_id"],
            set_={
                "user_id": user_ids[item["user_id"]],
                "visit_time": visit_time,
                "visit_date": visit_time.date(),
                "visit_slot": item["slot"],
                "visit_sequence_in_day": item["sequence"],
                "quality_status": item["quality_status"],
                "is_complete_visit": not missing,
                "missing_modalities": {"modalities": missing},
                "cheat_types": {"flags": flags, "source_record_group_id": item["source_record_group_id"]},
                "rule_version": DEMO_RULE_VERSION,
                "pipeline_version": "static_demo_seed_v1",
            },
        )
        actual_visit_id = session.execute(stmt.returning(Visit.visit_id)).scalar_one()
        ids[item["visit_id"]] = actual_visit_id
    return ids


def seed_modalities(session, visit_ids: dict[str, uuid.UUID]) -> dict[tuple[str, str], uuid.UUID]:
    pulse_by_visit: dict[str, list[dict]] = defaultdict(list)
    visit_lookup = {item["visit_id"]: item for item in VISITS}
    for record in PULSE_RECORDS:
        visit = visit_lookup[record["visit_id"]]
        pulse_by_visit[record["visit_id"]].append({**record, "slot": visit["slot"], "visit_time": visit["visit_time"]})

    modality_ids: dict[tuple[str, str], uuid.UUID] = {}
    all_modalities = ["ask", "pulse", "tongue", "face", "voice", "report"]
    for visit in VISITS:
        for modality in all_modalities:
            exists = modality in visit["modalities"]
            if not exists and modality not in visit["missing"]:
                continue
            modality_uuid = demo_uuid(f"modality:{visit['visit_id']}:{modality}")
            feature_summary = {}
            parsed = {"demo": True, "source_record_group_id": visit["source_record_group_id"]}
            if modality == "pulse" and exists:
                records = pulse_by_visit.get(visit["visit_id"], [])
                parsed["records"] = records
                if records:
                    feature_summary = {
                        "avg_pulse_rate": sum(item["pulse_rate"] for item in records) / len(records),
                        "avg_force": sum(item["force"] for item in records) / len(records),
                        "avg_tension": sum(item["tension"] for item in records) / len(records),
                        "avg_stability_score": sum(item["stability_score"] for item in records) / len(records),
                    }
            stmt = insert(ModalityRecord).values(
                modality_record_id=modality_uuid,
                visit_id=visit_ids[visit["visit_id"]],
                modality_type=modality,
                source_vendor=visit["source_vendor"],
                exists_flag=exists,
                is_required=modality in ["ask", "pulse", "tongue", "face"],
                is_complete=exists,
                completion_status="present" if exists else "missing",
                parsed_structured_data_json=parsed,
                feature_summary_json=feature_summary,
                numeric_fingerprint=f"demo:{visit['visit_id']}:{modality}" if exists else None,
                quality_flags_json={"flags": visit["quality_flags"]},
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["visit_id", "modality_type", "source_vendor"],
                set_={
                    "exists_flag": exists,
                    "is_complete": exists,
                    "completion_status": "present" if exists else "missing",
                    "parsed_structured_data_json": parsed,
                    "feature_summary_json": feature_summary,
                    "quality_flags_json": {"flags": visit["quality_flags"]},
                },
            )
            actual_modality_id = session.execute(stmt.returning(ModalityRecord.modality_record_id)).scalar_one()
            modality_ids[(visit["visit_id"], modality)] = actual_modality_id
    return modality_ids


def seed_assets(session, visit_ids: dict[str, uuid.UUID], modality_ids: dict[tuple[str, str], uuid.UUID]) -> None:
    session.execute(text("delete from fact_file_asset where storage_uri like 'demo://%'"))
    for asset in ASSETS:
        stmt = insert(FileAsset).values(
            asset_id=demo_uuid(asset["asset_id"]),
            visit_id=visit_ids[asset["visit_id"]],
            modality_record_id=modality_ids.get((asset["visit_id"], asset["modality"])),
            asset_type=asset["asset_type"],
            asset_role=f"training={str(asset['training']).lower()};parse={asset['parse_status']}",
            file_name=asset["file_name"],
            file_path=f"demo/raw/{asset['file_name']}",
            storage_uri=f"demo://assets/{asset['asset_id']}/{asset['file_name']}",
            file_hash=f"demo_hash_{asset['asset_id']}",
            file_size=1024,
            mime_type="application/octet-stream",
            parsed_success_flag=asset["parse_status"] == "ok",
        )
        session.execute(stmt)


def seed_quality_events(session, visit_ids: dict[str, uuid.UUID]) -> None:
    session.execute(delete(QualityEvent).where(QualityEvent.rule_version == DEMO_RULE_VERSION))
    for event in QUALITY_EVENTS:
        stmt = insert(QualityEvent).values(
            quality_event_id=demo_uuid(event["id"]),
            entity_type=event["entity"],
            entity_id=str(visit_ids.get(event["target"], demo_uuid(event["target"]))) if event["target"].startswith(("V", "A")) else event["target"],
            quality_flag=event["flag"],
            severity=event["severity"],
            status=event["status"],
            rule_version=DEMO_RULE_VERSION,
            evidence_json={"text": event["evidence"], "demo_target": event["target"]},
        )
        session.execute(stmt)


def seed_dataset_versions(session) -> None:
    for item in DATASET_VERSIONS:
        stmt = insert(DatasetVersion).values(
            dataset_version_id=demo_uuid(f"dataset:{item['dataset_id']}:{item['version']}"),
            dataset_id=item["dataset_id"],
            version_name=item["version"],
            task_type=item["task_type"],
            status=item["status"],
            modality_filter_json={"modalities": item["modalities"]},
            quality_filter_json={"policy": item["quality_policy"]},
            split_strategy=item["split_strategy"],
            summary_json={"samples": item["samples"], "users": item["users"]},
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["dataset_id", "version_name"],
            set_={
                "task_type": item["task_type"],
                "status": item["status"],
                "modality_filter_json": {"modalities": item["modalities"]},
                "quality_filter_json": {"policy": item["quality_policy"]},
                "split_strategy": item["split_strategy"],
                "summary_json": {"samples": item["samples"], "users": item["users"]},
            },
        )
        session.execute(stmt)


def seed_devices(session) -> dict[str, uuid.UUID]:
    ids: dict[str, uuid.UUID] = {}
    for item in DEVICES:
        device_uuid = demo_uuid(f"device:{item['source_vendor']}:{item['source_device_id']}")
        stmt = insert(Device).values(
            device_id=device_uuid,
            source_vendor=item["source_vendor"],
            source_device_id=item["source_device_id"],
            device_model=item["device_model"],
            sensor_type=item["sensor_type"],
            sampling_rate=item["sampling_rate"],
            device_meta_json={"demo": True},
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_vendor", "source_device_id"],
            set_={
                "device_model": item["device_model"],
                "sensor_type": item["sensor_type"],
                "sampling_rate": item["sampling_rate"],
                "device_meta_json": {"demo": True},
            },
        )
        ids[item["source_vendor"]] = session.execute(stmt.returning(Device.device_id)).scalar_one()
    return ids


def seed_feature_variables(session) -> None:
    for item in PULSE_FEATURE_VARIABLES:
        stmt = insert(FeatureVariable).values(
            feature_name=item["feature_name"],
            display_name=item["display_name"],
            modality_type="pulse",
            feature_level="measurement",
            source_vendor="standard",
            data_type="numeric",
            unit=item.get("unit"),
            category=item.get("category"),
            is_ml_feature=item.get("is_ml_feature", False),
            is_quality_feature=item.get("is_quality_feature", False),
            valid_range_json=item.get("valid_range_json"),
            description="Seeded for pulse analysis phase 1 demo dataset.",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["feature_name"],
            set_={
                "display_name": item["display_name"],
                "modality_type": "pulse",
                "feature_level": "measurement",
                "source_vendor": "standard",
                "data_type": "numeric",
                "unit": item.get("unit"),
                "category": item.get("category"),
                "is_ml_feature": item.get("is_ml_feature", False),
                "is_quality_feature": item.get("is_quality_feature", False),
                "valid_range_json": item.get("valid_range_json"),
                "description": "Seeded for pulse analysis phase 1 demo dataset.",
            },
        )
        session.execute(stmt)


def seed_pulse_analysis_phase1(
    session,
    user_ids: dict[str, uuid.UUID],
    visit_ids: dict[str, uuid.UUID],
    modality_ids: dict[tuple[str, str], uuid.UUID],
    device_ids: dict[str, uuid.UUID],
) -> None:
    session.execute(delete(PulsePositionFeature))
    session.execute(delete(PulseWaveformAsset))

    visit_lookup = {item["visit_id"]: item for item in VISITS}
    asset_by_visit_side: dict[tuple[str, str], uuid.UUID] = {}
    asset_rows = session.execute(select(FileAsset.asset_id, FileAsset.visit_id, FileAsset.asset_type)).all()
    reverse_visit_ids = {value: key for key, value in visit_ids.items()}
    for asset_id, visit_uuid, asset_type in asset_rows:
        visit_key = reverse_visit_ids.get(visit_uuid)
        if visit_key and asset_type in {"pulse_raw_left", "pulse_raw_right"}:
            side = "right" if asset_type.endswith("right") else "left"
            asset_by_visit_side[(visit_key, side)] = asset_id

    for record in PULSE_RECORDS:
        visit = visit_lookup[record["visit_id"]]
        visit_time = parse_visit_time(visit["visit_time"])
        side = record.get("side") or "unknown"
        source_measurement_id = record["record_id"]
        features = {
            key: record[key]
            for key in ["pulse_rate", "force", "tension", "fluency", "amplitude", "h1", "h3", "w", "as", "ad", "stability_score"]
            if key in record
        }
        measurement_uuid = demo_uuid(f"pulse-measurement:{record['record_id']}")
        stmt = insert(PulseMeasurement).values(
            measurement_id=measurement_uuid,
            visit_id=visit_ids[record["visit_id"]],
            modality_record_id=modality_ids[(record["visit_id"], "pulse")],
            user_id=user_ids[visit["user_id"]],
            device_id=device_ids.get(visit["source_vendor"]),
            source_vendor=visit["source_vendor"],
            source_measurement_id=source_measurement_id,
            start_time=visit_time,
            duration_seconds=60,
            visit_slot=visit["slot"],
            collection_hour=visit_time.hour + visit_time.minute / 60,
            hand_side=side,
            pulse_position="overall",
            sampling_rate=100,
            quality_status=visit["quality_status"],
            source_meta_json={
                "demo_record_id": record["record_id"],
                "pulse_type": record.get("pulse_type"),
                "included": record.get("included", True),
            },
            feature_json=features,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["modality_record_id", "source_measurement_id"],
            set_={
                "visit_id": visit_ids[record["visit_id"]],
                "user_id": user_ids[visit["user_id"]],
                "device_id": device_ids.get(visit["source_vendor"]),
                "start_time": visit_time,
                "duration_seconds": 60,
                "visit_slot": visit["slot"],
                "collection_hour": visit_time.hour + visit_time.minute / 60,
                "hand_side": side,
                "pulse_position": "overall",
                "sampling_rate": 100,
                "quality_status": visit["quality_status"],
                "source_meta_json": {
                    "demo_record_id": record["record_id"],
                    "pulse_type": record.get("pulse_type"),
                    "included": record.get("included", True),
                },
                "feature_json": features,
            },
        )
        actual_measurement_id = session.execute(stmt.returning(PulseMeasurement.measurement_id)).scalar_one()

        asset_id = asset_by_visit_side.get((record["visit_id"], side))
        waveform_stmt = insert(PulseWaveformAsset).values(
            waveform_asset_id=demo_uuid(f"pulse-waveform:{record['record_id']}:overall"),
            measurement_id=actual_measurement_id,
            asset_id=asset_id,
            channel_name="demo_preview",
            hand_side=side,
            pulse_position="overall",
            sample_count=6000,
            sampling_rate=100,
            storage_uri=f"demo://pulse/waveforms/{record['record_id']}.npz",
            data_format="npz",
            file_hash=f"demo_waveform_hash_{record['record_id']}",
            preview_json=[
                {"x": 0, "y": record["amplitude"] * 0.2},
                {"x": 0.25, "y": record["amplitude"]},
                {"x": 0.5, "y": record["amplitude"] * 0.45},
                {"x": 0.75, "y": record["amplitude"] * 0.65},
                {"x": 1.0, "y": record["amplitude"] * 0.25},
            ],
            summary_json={"min": 0, "max": record["amplitude"], "mean": record["amplitude"] * 0.45},
        )
        session.execute(waveform_stmt)

        for feature_name in ["h1", "h3", "w", "as", "ad"]:
            position_stmt = insert(PulsePositionFeature).values(
                position_feature_id=demo_uuid(f"pulse-position:{record['record_id']}:overall:{feature_name}"),
                measurement_id=actual_measurement_id,
                hand_side=side,
                pulse_position="overall",
                feature_name=feature_name,
                feature_value=record.get(feature_name),
                feature_unit=None,
                source_field=feature_name,
                parser_version="demo_pulse_phase1_v1",
                quality_weight=record.get("stability_score", 0) / 100,
            )
            session.execute(position_stmt)


def seed_panels(session, user_ids: dict[str, uuid.UUID], visit_ids: dict[str, uuid.UUID]) -> None:
    by_user_date_slot: dict[tuple[str, date, str], list[dict]] = defaultdict(list)
    for visit in VISITS:
        visit_time = parse_visit_time(visit["visit_time"])
        by_user_date_slot[(visit["user_id"], visit_time.date(), visit["slot"])].append(visit)
    for (user_key, visit_date, slot), group in by_user_date_slot.items():
        primary = sorted(group, key=lambda item: len(item["modalities"]), reverse=True)[0]
        available = sorted({modality for item in group for modality in item["modalities"]})
        flags = {flag for item in group for flag in item["quality_flags"]}
        stmt = insert(UserDayPanel).values(
            panel_id=demo_uuid(f"panel:{user_key}:{visit_date}:{slot}"),
            user_id=user_ids[user_key],
            visit_date=visit_date,
            visit_slot=slot,
            primary_visit_id=visit_ids[primary["visit_id"]],
            device_count=len({item["source_vendor"] for item in group}),
            available_modalities={modality: modality in available for modality in ["ask", "pulse", "tongue", "face", "voice", "report"]},
            quality_status=primary["quality_status"],
            is_complete_visit=not primary["missing"],
            is_suspected_cheat=any(item["quality_status"] == "suspicious" for item in group),
            duplicate_numeric_flag="duplicate_numeric_similar" in flags,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "visit_date", "visit_slot"],
            set_={
                "primary_visit_id": visit_ids[primary["visit_id"]],
                "device_count": len({item["source_vendor"] for item in group}),
                "available_modalities": {modality: modality in available for modality in ["ask", "pulse", "tongue", "face", "voice", "report"]},
                "quality_status": primary["quality_status"],
                "is_complete_visit": not primary["missing"],
                "is_suspected_cheat": any(item["quality_status"] == "suspicious" for item in group),
                "duplicate_numeric_flag": "duplicate_numeric_similar" in flags,
            },
        )
        session.execute(stmt)


def main() -> None:
    get_engine()
    with SessionLocal() as session:
        user_ids = seed_users(session)
        visit_ids = seed_visits(session, user_ids)
        modality_ids = seed_modalities(session, visit_ids)
        seed_assets(session, visit_ids, modality_ids)
        seed_quality_events(session, visit_ids)
        seed_dataset_versions(session)
        device_ids = seed_devices(session)
        seed_feature_variables(session)
        seed_pulse_analysis_phase1(session, user_ids, visit_ids, modality_ids, device_ids)
        seed_panels(session, user_ids, visit_ids)
        session.commit()
    print("Seeded static demo data into PostgreSQL.")
    print(f"Rule version: {DEMO_RULE_VERSION}")


if __name__ == "__main__":
    main()
