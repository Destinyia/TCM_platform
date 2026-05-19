from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.models import FileAsset, ModalityRecord, Visit
from backend.app.structured_parser import build_structured_modalities

MODALITIES = ["ask", "pulse", "tongue", "face", "voice", "report"]


def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _source_record_group_id(visit: Visit) -> str:
    if visit.cheat_types:
        return str(visit.cheat_types.get("source_record_group_id") or visit.source_visit_id or "")
    return str(visit.source_visit_id or "")


def _empty_payload(visit: Visit, modality: str) -> dict[str, Any]:
    return {
        "source_vendor": visit.source_vendor,
        "source_record_group_id": _source_record_group_id(visit),
        "modality": modality,
        "parser_stage": "db_parse",
        "asset_count": 0,
        "parsed_asset_count": 0,
        "assets": [],
    }


def _normalize_payload(visit: Visit, modality: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or _empty_payload(visit, modality))
    payload.setdefault("source_vendor", visit.source_vendor)
    payload.setdefault("source_record_group_id", _source_record_group_id(visit))
    payload.setdefault("modality", modality)
    payload["parser_stage"] = "db_parse"
    payload.setdefault("assets", [])
    payload["asset_count"] = len(payload["assets"])
    payload["parsed_asset_count"] = sum(1 for item in payload["assets"] if item.get("parse_status") == "ok")
    return payload


def _feature_summary(payload: dict[str, Any]) -> dict[str, Any]:
    statuses = Counter(str(item.get("parse_status") or "unknown") for item in payload.get("assets") or [])
    return {
        "asset_count": payload.get("asset_count", 0),
        "parsed_asset_count": payload.get("parsed_asset_count", 0),
        "parse_status_counts": dict(sorted(statuses.items())),
        "parser_stage": payload.get("parser_stage"),
    }


def _visit_query(payload: dict[str, Any]):
    stmt = select(Visit).order_by(Visit.visit_time.desc().nullslast(), Visit.created_at.desc())
    visit_id = payload.get("visit_id")
    if visit_id:
        stmt = stmt.where(Visit.visit_id == uuid.UUID(str(visit_id)))
    source_vendor = payload.get("source_vendor")
    if source_vendor:
        stmt = stmt.where(Visit.source_vendor == str(source_vendor))
    source_visit_id = payload.get("source_visit_id")
    if source_visit_id:
        stmt = stmt.where(Visit.source_visit_id == str(source_visit_id))
    limit = payload.get("limit")
    if limit:
        stmt = stmt.limit(max(1, int(limit)))
    return stmt


def parse_structured_data(session: Session, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    only_missing = _bool_value(payload.get("only_missing"), default=False)
    visits = session.scalars(_visit_query(payload)).all()

    result = {
        "visits_scanned": len(visits),
        "visits_parsed": 0,
        "modalities_updated": 0,
        "assets_seen": 0,
        "assets_ok": 0,
        "assets_metadata_only": 0,
        "assets_failed": 0,
        "assets_missing_file": 0,
    }

    for visit in visits:
        modality_records = session.scalars(
            select(ModalityRecord).where(ModalityRecord.visit_id == visit.visit_id)
        ).all()
        if only_missing:
            modality_records = [item for item in modality_records if not item.parsed_structured_data_json]
        if not modality_records:
            continue

        assets = session.scalars(select(FileAsset).where(FileAsset.visit_id == visit.visit_id)).all()
        modality_by_record_id = {
            item.modality_record_id: item.modality_type
            for item in modality_records
        }
        structured_by_modality = build_structured_modalities(visit, assets, modality_by_record_id)
        updated_this_visit = 0

        for modality_record in modality_records:
            modality = str(modality_record.modality_type or "")
            if modality not in MODALITIES:
                continue
            payload_for_modality = _normalize_payload(visit, modality, structured_by_modality.get(modality))
            status_counts = Counter(
                str(item.get("parse_status") or "unknown")
                for item in payload_for_modality.get("assets") or []
            )
            result["assets_seen"] += payload_for_modality["asset_count"]
            result["assets_ok"] += status_counts.get("ok", 0)
            result["assets_metadata_only"] += status_counts.get("metadata_only", 0)
            result["assets_failed"] += status_counts.get("failed", 0)
            result["assets_missing_file"] += status_counts.get("missing_file", 0)

            modality_record.parsed_structured_data_json = payload_for_modality
            modality_record.feature_summary_json = _feature_summary(payload_for_modality)
            updated_this_visit += 1

        if updated_this_visit:
            result["visits_parsed"] += 1
            result["modalities_updated"] += updated_this_visit

    return result
