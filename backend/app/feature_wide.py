from __future__ import annotations

import json
import re
from collections import OrderedDict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.models import ModalityRecord, User, Visit, VisitFeatureWide

PARSER_VERSION = "visit_feature_wide_v2"
MAX_TEXT_VALUE_LEN = 240
WAVEFORM_KEYS = {
    "CunShang",
    "Cun",
    "GuanMai",
    "Chi",
    "ChiXia",
    "SinglePluse",
    "maibo_CunShang",
    "maibo_Cun",
    "maibo_Guan",
    "maibo_Chi",
    "maibo_ChiXia",
}
ARRAY_SUMMARY_KEYS = {
    "ShowCs",
    "ShowCun",
    "ShowGuan",
    "ShowCx",
    "ShowChi",
    "IsValidPulse",
    "PerVue",
    "PulseLocation",
}
MODALITY_LABELS = {
    "ask": "问诊",
    "pulse": "脉诊",
    "tongue": "舌诊",
    "face": "面诊",
    "voice": "声诊",
    "report": "报告",
}


def snake_case(value: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value))
    text = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "_", text)
    return text.strip("_").lower()


def try_number(value: Any) -> Any:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except ValueError:
            return value
    if re.fullmatch(r"-?\d+\.\d+", text):
        try:
            return float(text)
        except ValueError:
            return value
    return value


def parse_json_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def add_feature(group: OrderedDict[str, Any], key: str, value: Any) -> None:
    value = try_number(value)
    if value is None:
        return
    if isinstance(value, str) and len(value) > MAX_TEXT_VALUE_LEN:
        return
    if is_scalar(value):
        group[key] = value


def summarize_array(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict) and value.get("_type") == "list":
        return {
            "count": value.get("count") or 0,
        }
    parsed = parse_json_string(value)
    if not isinstance(parsed, list):
        return None
    numeric_values = [try_number(item) for item in parsed]
    numeric_only = [item for item in numeric_values if isinstance(item, (int, float)) and not isinstance(item, bool)]
    summary: dict[str, Any] = {"count": len(parsed)}
    if numeric_only:
        summary.update(
            {
                "min": min(numeric_only),
                "max": max(numeric_only),
                "mean": round(sum(numeric_only) / len(numeric_only), 6),
            }
        )
    return summary


def asset_structured(asset: dict[str, Any]) -> dict[str, Any] | None:
    if asset.get("parse_status") != "ok":
        return None
    structured = asset.get("structured")
    return structured if isinstance(structured, dict) else None


def json_fields(structured: dict[str, Any]) -> dict[str, Any] | None:
    fields = structured.get("fields")
    return fields if isinstance(fields, dict) else None


def json_rows(structured: dict[str, Any]) -> list[dict[str, Any]]:
    rows = structured.get("rows")
    if isinstance(rows, dict) and isinstance(rows.get("sample"), list):
        return [row for row in rows["sample"] if isinstance(row, dict)]
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def extract_ask_features(modality_payload: dict[str, Any]) -> OrderedDict[str, Any]:
    group: OrderedDict[str, Any] = OrderedDict()
    for asset in modality_payload.get("assets") or []:
        structured = asset_structured(asset)
        if not structured:
            continue
        rows = json_rows(structured)
        if rows:
            add_feature(group, "ask_question_count", structured.get("row_count") or len(rows))
            for row in rows:
                question_id = row.get("QuestionId")
                if question_id is None:
                    continue
                prefix = f"ask_q_{question_id}"
                add_feature(group, f"{prefix}_answer", row.get("Answer"))
                add_feature(group, f"{prefix}_question", row.get("Question"))
        fields = json_fields(structured)
        if fields:
            for key, value in fields.items():
                add_feature(group, f"ask_{snake_case(key)}", value)
    return group


def extract_pulse_features(modality_payload: dict[str, Any]) -> OrderedDict[str, Any]:
    group: OrderedDict[str, Any] = OrderedDict()
    records = [item for item in modality_payload.get("records") or [] if isinstance(item, dict)]
    if records:
        add_feature(group, "pulse_record_count", len(records))
        first = records[0]
        for key in (
            "source_format",
            "side",
            "position",
            "pulse_type",
            "pulse_rate",
            "force",
            "tension",
            "fluency",
            "amplitude",
            "speed",
            "strength",
            "stability_score",
            "valid_segment_count",
            "segment_count",
        ):
            add_feature(group, f"pulse_{snake_case(key)}", first.get(key))
        waveform_summary = first.get("waveform_summary") or {}
        if isinstance(waveform_summary, dict):
            for waveform_key, summary in waveform_summary.items():
                if not isinstance(summary, dict):
                    continue
                add_feature(group, f"pulse_waveform_{snake_case(waveform_key)}_sample_count", summary.get("count"))
                add_feature(group, f"pulse_waveform_{snake_case(waveform_key)}_mean", summary.get("mean"))
        measurements = first.get("measurements") or []
        if isinstance(measurements, list):
            add_feature(group, "pulse_measurement_count", len(measurements))
    for asset in modality_payload.get("assets") or []:
        structured = asset_structured(asset)
        if not structured:
            continue
        fields = json_fields(structured)
        if not fields:
            continue
        for key, value in fields.items():
            if key in WAVEFORM_KEYS:
                summary = summarize_array(value)
                if summary:
                    add_feature(group, f"pulse_{snake_case(key)}_sample_count", summary.get("count"))
                    add_feature(group, f"pulse_{snake_case(key)}_mean", summary.get("mean"))
                continue
            if key in ARRAY_SUMMARY_KEYS:
                summary = summarize_array(value)
                if summary:
                    add_feature(group, f"pulse_{snake_case(key)}_count", summary.get("count"))
                continue
            if key == "PulseOther" and isinstance(value, dict):
                for inner_key, inner_value in value.items():
                    add_feature(group, f"pulse_other_{snake_case(inner_key)}", inner_value)
                continue
            if key == "PulseImg":
                continue
            add_feature(group, f"pulse_{snake_case(key)}", value)
    return group


def extract_tongue_features(modality_payload: dict[str, Any]) -> OrderedDict[str, Any]:
    group: OrderedDict[str, Any] = OrderedDict()
    skip_keys = {"OriginPic", "CloudOriginPic", "CutPic", "CloudCutPic", "RectanglePic", "CloudRectanglePic"}
    for asset in modality_payload.get("assets") or []:
        structured = asset_structured(asset)
        if not structured:
            continue
        fields = json_fields(structured)
        if not fields:
            continue
        for key, value in fields.items():
            if key in skip_keys:
                continue
            add_feature(group, f"tongue_{snake_case(key)}", value)
    return group


def extract_voice_features(modality_payload: dict[str, Any]) -> OrderedDict[str, Any]:
    group: OrderedDict[str, Any] = OrderedDict()
    for asset in modality_payload.get("assets") or []:
        structured = asset_structured(asset)
        if not structured:
            continue
        fields = json_fields(structured)
        if not fields:
            continue
        for key, value in fields.items():
            if key == "VoiceFiles":
                continue
            if key == "AnalysisResults":
                parsed = parse_json_string(value)
                if isinstance(parsed, dict) and parsed.get("_type") == "list":
                    add_feature(group, "voice_analysis_result_count", parsed.get("count"))
                    parsed = parsed.get("sample") or []
                if isinstance(parsed, list):
                    add_feature(group, "voice_analysis_result_count", len(parsed))
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        voice_name = snake_case(item.get("VoiceName") or item.get("Name") or "")
                        if not voice_name:
                            continue
                        for feature_key in ("Percentage", "StandardValue", "Energy", "Rms", "Zcr", "Entrogy", "Pitch"):
                            if feature_key in item:
                                add_feature(group, f"voice_item_{voice_name}_{snake_case(feature_key)}", item.get(feature_key))
                continue
            add_feature(group, f"voice_{snake_case(key)}", value)
    return group


def extract_generic_features(modality: str, modality_payload: dict[str, Any]) -> OrderedDict[str, Any]:
    group: OrderedDict[str, Any] = OrderedDict()
    for asset in modality_payload.get("assets") or []:
        structured = asset_structured(asset)
        if not structured:
            continue
        fields = json_fields(structured)
        if fields:
            for key, value in fields.items():
                add_feature(group, f"{modality}_{snake_case(key)}", value)
    return group


def extract_modality_features(modality: str, payload: dict[str, Any]) -> OrderedDict[str, Any]:
    if modality == "ask":
        return extract_ask_features(payload)
    if modality == "pulse":
        return extract_pulse_features(payload)
    if modality == "tongue":
        return extract_tongue_features(payload)
    if modality == "voice":
        return extract_voice_features(payload)
    return extract_generic_features(modality, payload)


def source_record_group_id(visit: Visit) -> str:
    flags = visit.cheat_types or {}
    return str(flags.get("source_record_group_id") or visit.source_visit_id or "")


def build_visit_feature_payload(visit: Visit, user: User | None, modalities: list[ModalityRecord]) -> dict[str, Any]:
    feature_json: OrderedDict[str, Any] = OrderedDict()
    feature_groups: OrderedDict[str, Any] = OrderedDict()
    present_modalities = []

    base_group: OrderedDict[str, Any] = OrderedDict()
    add_feature(base_group, "user_name", user.canonical_name if user else None)
    add_feature(base_group, "source_vendor", visit.source_vendor)
    add_feature(base_group, "source_visit_id", visit.source_visit_id)
    add_feature(base_group, "source_record_group_id", source_record_group_id(visit))
    add_feature(base_group, "visit_slot", visit.visit_slot)
    add_feature(base_group, "quality_status", visit.quality_status)
    feature_groups["base"] = {"label": "基础信息", "fields": dict(base_group)}
    feature_json.update(base_group)

    for modality_record in sorted(modalities, key=lambda item: item.modality_type or ""):
        modality = str(modality_record.modality_type or "")
        if modality_record.exists_flag:
            present_modalities.append(modality)
        payload = modality_record.parsed_structured_data_json or {}
        group = extract_modality_features(modality, payload)
        if group:
            feature_groups[modality] = {
                "label": MODALITY_LABELS.get(modality, modality),
                "fields": dict(group),
            }
            feature_json.update(group)

    return {
        "modalities": sorted(present_modalities),
        "feature_json": dict(feature_json),
        "feature_groups_json": feature_groups,
        "feature_count": len(feature_json),
    }


def upsert_visit_feature_wide(session: Session, visit: Visit, user: User | None, modalities: list[ModalityRecord]) -> None:
    payload = build_visit_feature_payload(visit, user, modalities)
    values = {
        "visit_id": visit.visit_id,
        "user_id": visit.user_id,
        "source_vendor": visit.source_vendor,
        "source_visit_id": visit.source_visit_id,
        "source_record_group_id": source_record_group_id(visit),
        "visit_time": visit.visit_time,
        "visit_date": visit.visit_date,
        "visit_slot": visit.visit_slot,
        "quality_status": visit.quality_status,
        "modalities": payload["modalities"],
        "feature_json": payload["feature_json"],
        "feature_groups_json": payload["feature_groups_json"],
        "feature_count": payload["feature_count"],
        "parser_version": PARSER_VERSION,
    }
    stmt = insert(VisitFeatureWide).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["visit_id"],
        set_={
            **{key: values[key] for key in values if key != "visit_id"},
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)


def rebuild_visit_feature_wide(session: Session, visits: list[Visit]) -> int:
    count = 0
    for visit in visits:
        user = session.get(User, visit.user_id)
        modalities = session.scalars(
            select(ModalityRecord).where(ModalityRecord.visit_id == visit.visit_id)
        ).all()
        upsert_visit_feature_wide(session, visit, user, modalities)
        count += 1
    return count
