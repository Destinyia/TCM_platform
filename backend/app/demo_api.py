from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from flask import Blueprint, abort, jsonify, request, send_file
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from backend.app.config import STORAGE_ROOT, STORAGE_URI_PREFIX
from backend.app.database import SessionLocal, get_engine
from backend.app.models import DatasetVersion, FileAsset, ModalityRecord, QualityEvent, User, UserDayPanel, Visit, VisitFeatureWide

demo_api = Blueprint("demo_api", __name__)

MODALITIES = ["ask", "pulse", "tongue", "face", "voice", "report"]


def pagination_args() -> tuple[int | None, int | None]:
    page = request.args.get("page", type=int)
    page_size = request.args.get("page_size", type=int)
    if not page or not page_size:
        return None, None
    return max(1, page), min(max(1, page_size), 200)


def paged(items: list[dict], page: int | None, page_size: int | None) -> dict | list[dict]:
    if not page or not page_size:
        return items
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": total, "page": page, "page_size": page_size}


def local_storage_path(storage_uri: str | None) -> Path | None:
    if not storage_uri or not storage_uri.startswith(f"{STORAGE_URI_PREFIX}/"):
        return None
    relative = storage_uri.removeprefix(f"{STORAGE_URI_PREFIX}/")
    path = (STORAGE_ROOT / relative).resolve()
    try:
        path.relative_to(STORAGE_ROOT)
    except ValueError:
        return None
    return path


def as_json(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def source_record_group_id(visit: Visit) -> str:
    flags = visit.cheat_types or {}
    return flags.get("source_record_group_id") or f"{visit.source_vendor}-{visit.source_visit_id}"


def quality_flags(visit: Visit) -> list[str]:
    flags = visit.cheat_types or {}
    return flags.get("flags") or []


def missing_modalities(visit: Visit) -> list[str]:
    payload = visit.missing_modalities or {}
    return payload.get("modalities") or []


def source_name(value: str) -> str:
    return {"zhongke": "中科", "yushengtang": "玉生堂"}.get(value, value)


def user_display_id(index: int) -> str:
    return f"DEID-{index:03d}"


def user_age(user: User) -> int | None:
    if not user.birth_date:
        return None
    return date.today().year - user.birth_date.year


def visit_payload(visit: Visit, user: User | None = None, modalities: list[str] | None = None) -> dict:
    return {
        "visit_id": str(visit.visit_id),
        "user_id": str(visit.user_id),
        "user_name": user.canonical_name if user else None,
        "source_vendor": visit.source_vendor,
        "source_vendor_name": source_name(visit.source_vendor),
        "source_visit_id": visit.source_visit_id,
        "source_record_group_id": source_record_group_id(visit),
        "visit_time": visit.visit_time.strftime("%Y-%m-%d %H:%M") if visit.visit_time else None,
        "visit_date": visit.visit_date.isoformat() if visit.visit_date else None,
        "time_window_slot": visit.visit_slot,
        "sequence_slot": f"第{visit.visit_sequence_in_day}次" if visit.visit_sequence_in_day else None,
        "quality_status": visit.quality_status,
        "modalities": modalities or [],
        "missing_modalities": missing_modalities(visit),
        "quality_flags": quality_flags(visit),
    }


def load_visit_modalities(session, visit_ids: list[UUID]) -> dict[UUID, list[str]]:
    if not visit_ids:
        return {}
    rows = session.execute(
        select(ModalityRecord.visit_id, ModalityRecord.modality_type)
        .where(ModalityRecord.visit_id.in_(visit_ids), ModalityRecord.exists_flag.is_(True))
    ).all()
    grouped: dict[UUID, list[str]] = defaultdict(list)
    for visit_id, modality in rows:
        grouped[visit_id].append(modality)
    return {key: sorted(value, key=lambda item: MODALITIES.index(item) if item in MODALITIES else 99) for key, value in grouped.items()}


def flatten_pulse_records(session) -> list[dict]:
    rows = session.execute(
        select(ModalityRecord, Visit, User)
        .join(Visit, Visit.visit_id == ModalityRecord.visit_id)
        .join(User, User.user_id == Visit.user_id)
        .where(ModalityRecord.modality_type == "pulse", ModalityRecord.exists_flag.is_(True))
        .order_by(Visit.visit_time)
    ).all()
    records: list[dict] = []
    for modality, visit, user in rows:
        payload = modality.parsed_structured_data_json or {}
        for record in payload.get("records") or []:
            records.append(
                {
                    **record,
                    "visit_id": str(visit.visit_id),
                    "modality_record_id": str(modality.modality_record_id),
                    "user_id": str(user.user_id),
                    "user_name": user.canonical_name,
                    "source_vendor": visit.source_vendor,
                    "visit_date": visit.visit_date.isoformat() if visit.visit_date else None,
                    "visit_time": visit.visit_time.strftime("%H:%M") if visit.visit_time else None,
                    "slot": visit.visit_slot,
                    "quality_status": visit.quality_status,
                }
            )
    return records


@demo_api.route("/summary", methods=["GET"])
def summary():
    get_engine()
    with SessionLocal() as session:
        user_count = session.scalar(select(func.count()).select_from(User)) or 0
        visit_count = session.scalar(select(func.count()).select_from(Visit)) or 0
        asset_count = session.scalar(select(func.count()).select_from(FileAsset)) or 0
        quality_count = session.scalar(select(func.count()).select_from(QualityEvent)) or 0
        modality_rows = session.execute(
            select(ModalityRecord.modality_type, func.count())
            .where(ModalityRecord.exists_flag.is_(True))
            .group_by(ModalityRecord.modality_type)
        ).all()
        quality_rows = session.execute(
            select(QualityEvent.quality_flag, func.count())
            .group_by(QualityEvent.quality_flag)
        ).all()
        recent_visits = visits_response_data(session, limit=6)
    return jsonify(
        {
            "stats": {
                "user_count": user_count,
                "visit_count": visit_count,
                "asset_count": asset_count,
                "quality_event_count": quality_count,
            },
            "modality_coverage": [{"modality": key, "count": count} for key, count in modality_rows],
            "quality_distribution": [{"flag": key, "count": count} for key, count in quality_rows],
            "recent_visits": recent_visits,
        }
    )


def visits_response_data(session, limit: int | None = None) -> list[dict]:
    stmt = (
        select(Visit, User)
        .join(User, User.user_id == Visit.user_id)
        .order_by(Visit.visit_time.desc())
    )
    if limit:
        stmt = stmt.limit(limit)
    rows = session.execute(stmt).all()
    modality_map = load_visit_modalities(session, [visit.visit_id for visit, _ in rows])
    return [visit_payload(visit, user, modality_map.get(visit.visit_id, [])) for visit, user in rows]


@demo_api.route("/checkin-matrix", methods=["GET"])
def checkin_matrix():
    get_engine()
    with SessionLocal() as session:
        rows = session.execute(
            select(Visit, User)
            .join(User, User.user_id == Visit.user_id)
            .order_by(User.canonical_name, Visit.visit_date, Visit.visit_slot, Visit.visit_time)
        ).all()
        modality_map = load_visit_modalities(session, [visit.visit_id for visit, _ in rows])

    all_months = sorted({visit.visit_date.strftime("%Y-%m") for visit, _ in rows if visit.visit_date})
    month = request.args.get("month")
    if month:
        rows = [(visit, user) for visit, user in rows if visit.visit_date and visit.visit_date.isoformat().startswith(month)]

    slots = ["早", "中", "晚"]
    dates = sorted({visit.visit_date.isoformat() for visit, _ in rows if visit.visit_date})
    users_by_id: dict[str, dict] = {}
    user_order: list[str] = []
    slot_order = {slot: index for index, slot in enumerate(slots)}

    for visit, user in rows:
        user_id = str(user.user_id)
        if user_id not in users_by_id:
            user_order.append(user_id)
            users_by_id[user_id] = {
                "user_id": user_id,
                "display_id": user_display_id(len(user_order)),
                "user_name": user.canonical_name,
                "total_count": 0,
                "valid_count": 0,
                "cells": defaultdict(dict),
            }

        date_key = visit.visit_date.isoformat() if visit.visit_date else "unknown"
        slot_key = visit.visit_slot or "unknown"
        cell = users_by_id[user_id]["cells"][date_key].setdefault(
            slot_key,
            {
                "count": 0,
                "valid_count": 0,
                "sources": [],
                "quality_statuses": [],
                "modalities": [],
                "visit_ids": [],
                "visit_times": [],
            },
        )
        modalities = modality_map.get(visit.visit_id, [])
        cell["count"] += 1
        cell["valid_count"] += 1 if visit.quality_status == "valid" else 0
        cell["visit_ids"].append(str(visit.visit_id))
        cell["visit_times"].append(visit.visit_time.strftime("%H:%M") if visit.visit_time else None)
        if visit.source_vendor not in cell["sources"]:
            cell["sources"].append(visit.source_vendor)
        if visit.quality_status not in cell["quality_statuses"]:
            cell["quality_statuses"].append(visit.quality_status)
        for modality in modalities:
            if modality not in cell["modalities"]:
                cell["modalities"].append(modality)

        users_by_id[user_id]["total_count"] += 1
        users_by_id[user_id]["valid_count"] += 1 if visit.quality_status == "valid" else 0

    rows_payload = []
    for user_id in user_order:
        item = users_by_id[user_id]
        cells = {}
        for date_key, slot_cells in item["cells"].items():
            cells[date_key] = {
                slot: {
                    **cell,
                    "sources": sorted(cell["sources"]),
                    "quality_statuses": sorted(cell["quality_statuses"]),
                    "modalities": sorted(cell["modalities"], key=lambda value: MODALITIES.index(value) if value in MODALITIES else 99),
                    "status": "valid"
                    if cell["count"] == cell["valid_count"]
                    else "mixed"
                    if cell["valid_count"] > 0
                    else "invalid",
                }
                for slot, cell in sorted(slot_cells.items(), key=lambda pair: slot_order.get(pair[0], 99))
            }
        rows_payload.append({**item, "cells": cells})

    return jsonify(
        {
            "dates": dates,
            "slots": slots,
            "months": all_months,
            "rows": rows_payload,
            "summary": {
                "user_count": len(rows_payload),
                "date_count": len(dates),
                "visit_count": len(rows),
                "valid_visit_count": sum(item["valid_count"] for item in rows_payload),
            },
        }
    )


@demo_api.route("/users", methods=["GET"])
def users():
    get_engine()
    with SessionLocal() as session:
        rows = session.execute(select(User).order_by(User.canonical_name)).scalars().all()
        result = []
        for index, user in enumerate(rows, start=1):
            visit_rows = session.execute(select(Visit).where(Visit.user_id == user.user_id)).scalars().all()
            visit_ids = [visit.visit_id for visit in visit_rows]
            modality_map = load_visit_modalities(session, visit_ids)
            present = sum(len(modality_map.get(visit_id, [])) for visit_id in visit_ids)
            possible = max(1, len(visit_ids) * len(MODALITIES))
            last_visit = max((visit.visit_date for visit in visit_rows if visit.visit_date), default=None)
            quality = "valid"
            if any(visit.quality_status == "suspicious" for visit in visit_rows):
                quality = "suspicious"
            elif any(visit.quality_status == "incomplete" for visit in visit_rows):
                quality = "incomplete"
            result.append(
                {
                    "user_id": str(user.user_id),
                    "display_id": user_display_id(index),
                    "name": user.canonical_name,
                    "sex": user.sex,
                    "age": user_age(user),
                    "cohort": user.cohort_id,
                    "visit_count": len(visit_rows),
                    "last_visit": last_visit.isoformat() if last_visit else None,
                    "quality_status": quality,
                    "modality_coverage": round(present / possible, 2),
                }
            )
    keyword = request.args.get("keyword", "").strip().lower()
    if keyword:
        result = [
            item for item in result
            if keyword in item["name"].lower() or keyword in item["display_id"].lower()
        ]
    page, page_size = pagination_args()
    return jsonify(paged(result, page, page_size))


@demo_api.route("/users/<user_id>/timeline", methods=["GET"])
def user_timeline(user_id: str):
    get_engine()
    with SessionLocal() as session:
        user = session.get(User, UUID(user_id))
        if not user:
            return jsonify({"message": "user not found"}), 404
        visits = session.execute(
            select(Visit).where(Visit.user_id == user.user_id).order_by(Visit.visit_time.desc())
        ).scalars().all()
        modality_map = load_visit_modalities(session, [visit.visit_id for visit in visits])
    return jsonify(
        {
            "user": {
                "user_id": str(user.user_id),
                "display_id": "DEID",
                "name": user.canonical_name,
                "sex": user.sex,
                "age": user_age(user),
                "cohort": user.cohort_id,
            },
            "visits": [visit_payload(visit, user, modality_map.get(visit.visit_id, [])) for visit in visits],
        }
    )


@demo_api.route("/visits", methods=["GET"])
def visits():
    get_engine()
    with SessionLocal() as session:
        data = visits_response_data(session)
    source = request.args.get("source")
    quality = request.args.get("quality")
    modality = request.args.get("modality")
    keyword = request.args.get("keyword", "").strip().lower()
    if source:
        data = [item for item in data if item["source_vendor"] == source]
    if quality:
        data = [item for item in data if item["quality_status"] == quality]
    if modality:
        data = [item for item in data if modality in item["modalities"]]
    if keyword:
        data = [
            item for item in data
            if any(keyword in str(value).lower() for value in [
                item.get("user_name"),
                item.get("source_visit_id"),
                item.get("source_record_group_id"),
                *(item.get("quality_flags") or []),
            ])
        ]
    page, page_size = pagination_args()
    return jsonify(paged(data, page, page_size))


@demo_api.route("/visits/<visit_id>", methods=["GET"])
def visit_detail(visit_id: str):
    get_engine()
    with SessionLocal() as session:
        visit = session.get(Visit, UUID(visit_id))
        if not visit:
            return jsonify({"message": "visit not found"}), 404
        user = session.get(User, visit.user_id)
        modalities = session.execute(
            select(ModalityRecord).where(ModalityRecord.visit_id == visit.visit_id).order_by(ModalityRecord.modality_type)
        ).scalars().all()
        assets = session.execute(
            select(FileAsset).where(FileAsset.visit_id == visit.visit_id).order_by(FileAsset.asset_type)
        ).scalars().all()
        try:
            feature_wide = session.get(VisitFeatureWide, visit.visit_id)
        except SQLAlchemyError:
            session.rollback()
            feature_wide = None

        response_payload = {
            **visit_payload(visit, user, [item.modality_type for item in modalities if item.exists_flag]),
            "feature_wide": {
                "feature_count": feature_wide.feature_count,
                "parser_version": feature_wide.parser_version,
                "updated_at": feature_wide.updated_at.isoformat() if feature_wide.updated_at else None,
                "features": feature_wide.feature_json,
                "groups": feature_wide.feature_groups_json,
            }
            if feature_wide
            else None,
            "modality_records": [
                {
                    "modality_record_id": str(item.modality_record_id),
                    "modality_type": item.modality_type,
                    "exists_flag": item.exists_flag,
                    "completion_status": item.completion_status,
                    "parsed_structured_data_json": item.parsed_structured_data_json,
                    "structured_data_json": item.parsed_structured_data_json,
                    "feature_summary_json": item.feature_summary_json,
                    "quality_flags_json": item.quality_flags_json,
                }
                for item in modalities
            ],
            "assets": [
                {
                    "asset_id": str(asset.asset_id),
                    "asset_type": asset.asset_type,
                    "asset_role": asset.asset_role,
                    "file_name": asset.file_name,
                    "storage_uri": asset.storage_uri,
                    "file_hash": asset.file_hash,
                    "file_size": asset.file_size,
                    "mime_type": asset.mime_type,
                    "parsed_success_flag": asset.parsed_success_flag,
                    "preview_url": f"/api/demo/assets/{asset.asset_id}/file" if (asset.mime_type or "").startswith("image/") else None,
                }
                for asset in assets
            ],
        }
    return jsonify(response_payload)


@demo_api.route("/assets/<asset_id>/file", methods=["GET"])
def asset_file(asset_id: str):
    get_engine()
    with SessionLocal() as session:
        asset = session.get(FileAsset, UUID(asset_id))
        if not asset:
            abort(404)
        path = local_storage_path(asset.storage_uri)
    if not path or not path.exists() or not path.is_file():
        abort(404)
    return send_file(path, mimetype=asset.mime_type or None, as_attachment=False, download_name=asset.file_name)


@demo_api.route("/assets", methods=["GET"])
def assets():
    get_engine()
    with SessionLocal() as session:
        rows = session.execute(select(FileAsset, Visit).join(Visit, Visit.visit_id == FileAsset.visit_id)).all()
    return jsonify(
        [
            {
                "asset_id": str(asset.asset_id),
                "visit_id": str(asset.visit_id),
                "asset_type": asset.asset_type,
                "asset_role": asset.asset_role,
                "file_name": asset.file_name,
                "storage_uri": asset.storage_uri,
                "parsed_success_flag": asset.parsed_success_flag,
                "source_vendor": visit.source_vendor,
            }
            for asset, visit in rows
        ]
    )


@demo_api.route("/quality-events", methods=["GET"])
def quality_events():
    get_engine()
    with SessionLocal() as session:
        rows = session.execute(select(QualityEvent).order_by(QualityEvent.created_at.desc())).scalars().all()
    return jsonify(
        [
            {
                "quality_event_id": str(item.quality_event_id),
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "quality_flag": item.quality_flag,
                "severity": item.severity,
                "status": item.status,
                "evidence_json": item.evidence_json,
            }
            for item in rows
        ]
    )


@demo_api.route("/dataset-versions", methods=["GET"])
def dataset_versions():
    get_engine()
    with SessionLocal() as session:
        rows = session.execute(select(DatasetVersion).order_by(DatasetVersion.created_at.desc())).scalars().all()
    return jsonify(
        [
            {
                "dataset_version_id": str(item.dataset_version_id),
                "dataset_id": item.dataset_id,
                "version": item.version_name,
                "task_type": item.task_type,
                "status": item.status,
                "modalities": (item.modality_filter_json or {}).get("modalities", []),
                "quality_policy": (item.quality_filter_json or {}).get("policy"),
                "split_strategy": item.split_strategy,
                "samples": (item.summary_json or {}).get("samples", 0),
                "users": (item.summary_json or {}).get("users", 0),
            }
            for item in rows
        ]
    )


@demo_api.route("/pulse/records", methods=["GET"])
def pulse_records():
    get_engine()
    include_suspicious = request.args.get("include_suspicious", "false").lower() == "true"
    user_id = request.args.get("user_id")
    source = request.args.get("source")
    slot = request.args.get("slot")
    with SessionLocal() as session:
        records = flatten_pulse_records(session)
    if user_id:
        records = [item for item in records if item["user_id"] == user_id]
    if source and source != "all":
        records = [item for item in records if item["source_vendor"] == source]
    if slot:
        records = [item for item in records if item["slot"] == slot]
    if not include_suspicious:
        records = [item for item in records if item.get("included", True)]
    return jsonify(records)


def average(records: list[dict], key: str) -> float:
    values = [float(item[key]) for item in records if item.get(key) is not None]
    return sum(values) / len(values) if values else 0


@demo_api.route("/pulse/user-trend", methods=["GET"])
def pulse_user_trend():
    user_id = request.args.get("user_id")
    with SessionLocal() as session:
        records = flatten_pulse_records(session)
    if user_id:
        records = [item for item in records if item["user_id"] == user_id]
    records = [item for item in records if item.get("included", True)]
    records.sort(key=lambda item: f"{item['visit_date']} {item['visit_time']}")
    return jsonify(records)


@demo_api.route("/pulse/slot-stability", methods=["GET"])
def pulse_slot_stability():
    user_id = request.args.get("user_id")
    slot = request.args.get("slot")
    with SessionLocal() as session:
        records = flatten_pulse_records(session)
    records = [item for item in records if item.get("included", True)]
    if user_id:
        records = [item for item in records if item["user_id"] == user_id]
    if slot:
        records = [item for item in records if item["slot"] == slot]
    return jsonify(
        {
            "records": records,
            "summary": {
                "avg_pulse_rate": average(records, "pulse_rate"),
                "avg_force": average(records, "force"),
                "avg_stability_score": average(records, "stability_score"),
                "count": len(records),
            },
        }
    )


@demo_api.route("/pulse/cross-user", methods=["GET"])
def pulse_cross_user():
    with SessionLocal() as session:
        records = [item for item in flatten_pulse_records(session) if item.get("included", True)]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["user_name"]].append(record)
    return jsonify(
        [
            {
                "user_name": name,
                "pulse_rate": average(items, "pulse_rate"),
                "force": average(items, "force"),
                "tension": average(items, "tension"),
                "fluency": average(items, "fluency"),
                "amplitude": average(items, "amplitude") * 100,
            }
            for name, items in grouped.items()
        ]
    )


@demo_api.route("/pulse/feature-drift", methods=["GET"])
def pulse_feature_drift():
    user_id = request.args.get("user_id")
    with SessionLocal() as session:
        records = [item for item in flatten_pulse_records(session) if item.get("included", True)]
    if user_id:
        records = [item for item in records if item["user_id"] == user_id]
    grouped: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        grouped[record["slot"]].append(record)
    return jsonify(
        [
            {
                "slot": slot,
                "pulse_rate": average(items, "pulse_rate"),
                "force": average(items, "force"),
                "tension": average(items, "tension"),
                "fluency": average(items, "fluency"),
            }
            for slot, items in grouped.items()
        ]
    )


