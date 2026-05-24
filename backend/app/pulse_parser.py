from __future__ import annotations

import json
import math
import re
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.models import FileAsset, Visit

PULSE_RECORD_VERSION = "pulse_record_v1"
WAVEFORM_KEYS = ("SinglePluse", "CunShang", "Cun", "GuanMai", "Chi", "ChiXia")
DISPLAY_WAVEFORM_KEYS = ("SinglePluse", "Cun", "GuanMai", "Chi")
YUSHENGTANG_DEFAULT_SAMPLING_RATE = 500.0


def to_number(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number.is_integer() else number


def number_or_zero(value: Any) -> float:
    number = to_number(value)
    return float(number) if number is not None else 0.0


def parse_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and value.get("_type") == "list":
        sample = value.get("sample")
        return sample if isinstance(sample, list) else []
    if not isinstance(value, str):
        return []
    text = value.strip()
    if not text or text[0] not in "[{":
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_fields(value: dict[str, Any] | None) -> dict[str, Any]:
    fields = value or {}
    result = {}
    for key, item in fields.items():
        if isinstance(item, str):
            stripped = item.strip()
            if stripped[:1] in {"[", "{"}:
                try:
                    result[key] = json.loads(stripped)
                    continue
                except json.JSONDecodeError:
                    pass
        result[key] = item
    return result


def waveform_stats(values: list[Any]) -> dict[str, Any]:
    numeric = [float(item) for item in (to_number(item) for item in values) if item is not None]
    summary: dict[str, Any] = {"count": len(values)}
    if numeric:
        summary.update(
            {
                "min": round(min(numeric), 6),
                "max": round(max(numeric), 6),
                "mean": round(sum(numeric) / len(numeric), 6),
            }
        )
    return summary


def downsample(values: list[Any], limit: int = 160) -> list[float]:
    numeric = [float(item) for item in (to_number(item) for item in values) if item is not None]
    if len(numeric) <= limit:
        return [round(item, 6) for item in numeric]
    step = len(numeric) / limit
    return [round(numeric[int(index * step)], 6) for index in range(limit)]


def percent_value(value: Any) -> float | None:
    number = to_number(value)
    if number is None:
        return None
    number = float(number)
    if 0 <= number <= 1.5:
        return round(number * 100, 2)
    return round(number, 2)


def average(values: list[Any]) -> float | None:
    numeric = [float(item) for item in (to_number(item) for item in values) if item is not None]
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 4)


def normalize_side(value: Any) -> str:
    text = str(value).strip()
    if text in {"0", "left", "Left", "\u5de6"}:
        return "\u5de6"
    if text in {"1", "right", "Right", "\u53f3"}:
        return "\u53f3"
    return text or "\u672a\u77e5"


def normalize_included(status: str | None, stability_score: float | int | None) -> bool:
    if status == "suspicious":
        return False
    if stability_score is None:
        return True
    return float(stability_score) >= 50


def source_review_status(status: str | None, flags: list[str] | None = None) -> str:
    reasons = flags or []
    if status == "suspicious" or any("重复病例目录" in reason for reason in reasons):
        return "suspected_duplicate"
    if status == "incomplete":
        return "incomplete_source"
    return "normal"


def research_inclusion_policy(record: dict[str, Any], visit: Visit) -> dict[str, Any]:
    flags = (visit.cheat_types or {}).get("flags") or []
    platform_included = normalize_included(visit.quality_status, record.get("stability_score"))
    review_status = source_review_status(visit.quality_status, flags)
    has_pulse_data = bool(record.get("waveform_preview") or record.get("measurements"))
    if not has_pulse_data:
        research_status = "insufficient_pulse_data"
    elif review_status == "suspected_duplicate":
        research_status = "dedup_review_required"
    else:
        research_status = "eligible"
    return {
        "included": platform_included,
        "platform_included": platform_included,
        "source_review_status": review_status,
        "source_review_reasons": flags,
        "research_included": has_pulse_data,
        "research_inclusion_status": research_status,
    }


def yushengtang_record(asset: dict[str, Any], fields: dict[str, Any], visit: Visit) -> dict[str, Any]:
    parsed_fields = parse_fields(fields)
    waveform_summary = OrderedDict()
    waveform_preview = []
    waveform_sample_counts = []
    for key in WAVEFORM_KEYS:
        values = parse_list(parsed_fields.get(key))
        if not values:
            continue
        waveform_summary[key] = waveform_stats(values)
        waveform_summary[key]["sampling_rate"] = YUSHENGTANG_DEFAULT_SAMPLING_RATE
        waveform_summary[key]["duration_seconds"] = round(waveform_summary[key]["count"] / YUSHENGTANG_DEFAULT_SAMPLING_RATE, 3)
        waveform_sample_counts.append(waveform_summary[key]["count"])
        if key in DISPLAY_WAVEFORM_KEYS:
            waveform_preview.append({"name": key, "points": downsample(values)})

    duration_seconds = None
    if waveform_sample_counts:
        duration_seconds = round(max(waveform_sample_counts) / YUSHENGTANG_DEFAULT_SAMPLING_RATE, 3)

    valid_flags = parse_list(parsed_fields.get("IsValidPulse"))
    valid_count = sum(1 for item in valid_flags if bool(item))
    stability_score = round(valid_count / len(valid_flags) * 100, 2) if valid_flags else None
    percentages = [
        percent_value(parsed_fields.get(key))
        for key in ("YiMai_Percent", "JuMai_Percent", "WenMai_DX_Percent", "WenMai_QR_Percent", "WenMai_KM_Percent", "RenMai_Percent")
    ]
    valid_percentages = [item for item in percentages if item is not None]

    record = {
        "parser_version": PULSE_RECORD_VERSION,
        "source_asset_id": asset.get("asset_id"),
        "source_vendor": "yushengtang",
        "source_format": "json",
        "sampling_rate": YUSHENGTANG_DEFAULT_SAMPLING_RATE,
        "sampling_rate_source": "vendor_default_yushengtang_500hz",
        "duration_seconds": duration_seconds,
        "duration_source": "waveform_sample_count/sampling_rate",
        "side": normalize_side(parsed_fields.get("LeftOrRight")),
        "position": "\u5173",
        "pulse_type": parsed_fields.get("PulseTypeName") or str(parsed_fields.get("PulseType") or ""),
        "pulse_type_code": parsed_fields.get("PulseType"),
        "pulse_rate": to_number(parsed_fields.get("PulseNumbers")),
        "force": percent_value(parsed_fields.get("Strength")),
        "tension": percent_value(parsed_fields.get("WenMai_QR_Percent")),
        "fluency": percent_value(parsed_fields.get("JuMai_Percent")),
        "amplitude": to_number(parsed_fields.get("Amplitude")),
        "speed": to_number(parsed_fields.get("Speed")),
        "strength": to_number(parsed_fields.get("Strength")),
        "stability_score": stability_score,
        "valid_segment_count": valid_count if valid_flags else None,
        "segment_count": len(valid_flags) if valid_flags else None,
        "pulse_percent_mean": round(sum(valid_percentages) / len(valid_percentages), 2) if valid_percentages else None,
        "waveform_summary": waveform_summary,
        "waveform_preview": waveform_preview,
        "measurements": [],
        "detail": {
            "TreatNumber": parsed_fields.get("TreatNumber"),
            "PulseLevel": parsed_fields.get("PulseLevel"),
            "PulsePress": parsed_fields.get("PulsePress"),
            "AmplitudeRate": parsed_fields.get("AmplitudeRate"),
            "SpeedRate": parsed_fields.get("SpeedRate"),
            "StrengthRate": parsed_fields.get("StrengthRate"),
            "PeakTimeSwell": parsed_fields.get("PeakTimeSwell"),
            "PeakTimeSag": parsed_fields.get("PeakTimeSag"),
            "PeakAngle": parsed_fields.get("PeakAngle"),
        },
    }
    record.update(research_inclusion_policy(record, visit))
    return record


def clean_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def row_matches_visit(values: list[Any], visit: Visit) -> bool:
    needles = [str(visit.source_visit_id or "")]
    if visit.cheat_types:
        needles.append(str(visit.cheat_types.get("raw_source_visit_id") or ""))
    text = " ".join(str(value) for value in values if value is not None)
    return any(needle and needle in text for needle in needles)


def collect_zhongke_block(frame: pd.DataFrame, start_index: int) -> list[list[Any]]:
    block = []
    for index in range(start_index, len(frame)):
        row = [clean_cell(value) for value in frame.iloc[index].tolist()]
        if index > start_index and row[0] is not None:
            break
        if any(value is not None for value in row):
            block.append(row)
    return block


def zhongke_measurement(row: list[Any]) -> dict[str, Any] | None:
    position = row[24] if len(row) > 24 else None
    if not position:
        return None
    metric_keys = [
        ("position_value", 25),
        ("pulse_rate_value", 26),
        ("rhythm_value", 27),
        ("force_value", 28),
        ("tension_value", 29),
        ("fluency_value", 30),
        ("h1", 31),
        ("h2", 32),
        ("h3", 33),
        ("h4", 34),
        ("h5", 35),
        ("t", 36),
        ("t1", 37),
        ("t4", 38),
        ("t5", 39),
        ("w", 40),
        ("as", 41),
        ("ad", 42),
        ("h1_t1", 43),
        ("h3_h1", 44),
        ("h4_h1", 45),
        ("h5_h1", 46),
        ("w_t", 47),
        ("t4_t5", 48),
    ]
    item: dict[str, Any] = {
        "location": row[17] if len(row) > 17 else None,
        "pulse_position": row[18] if len(row) > 18 else None,
        "pulse_rate_label": row[19] if len(row) > 19 else None,
        "rhythm_label": row[20] if len(row) > 20 else None,
        "force_label": row[21] if len(row) > 21 else None,
        "tension_label": row[22] if len(row) > 22 else None,
        "fluency_label": row[23] if len(row) > 23 else None,
        "type": position,
    }
    for key, column in metric_keys:
        if len(row) > column:
            item[key] = to_number(row[column])
    return item


def parse_zhongke_pulse_excel(path: Path, visit: Visit) -> dict[str, Any] | None:
    excel = pd.ExcelFile(path)
    matched_sheet = None
    matched_block: list[list[Any]] = []
    for sheet_name in excel.sheet_names:
        frame = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=object)
        for row_index in range(len(frame)):
            values = [clean_cell(value) for value in frame.iloc[row_index].tolist()]
            if row_matches_visit(values, visit):
                matched_sheet = sheet_name
                matched_block = collect_zhongke_block(frame, row_index)
                break
        if matched_block:
            break

    if not matched_block:
        return None

    first = matched_block[0]
    measurements = [item for item in (zhongke_measurement(row) for row in matched_block) if item]
    rate_values = [item.get("pulse_rate_value") for item in measurements if item.get("pulse_rate_value")]
    force_values = [item.get("force_value") for item in measurements if item.get("force_value")]
    tension_values = [item.get("tension_value") for item in measurements if item.get("tension_value")]
    fluency_values = [item.get("fluency_value") for item in measurements if item.get("fluency_value")]
    h1_values = [item.get("h1") for item in measurements if item.get("h1")]

    sides = sorted({str(item.get("type"))[0] for item in measurements if item.get("type") and str(item.get("type"))[0] in {"\u5de6", "\u53f3"}})
    side = "\u53cc\u4fa7" if len(sides) > 1 else (sides[0] if sides else "\u672a\u77e5")
    valid_segment_count = len([item for item in measurements if number_or_zero(item.get("pulse_rate_value")) > 0])
    stability_score = round(valid_segment_count / len(measurements) * 100, 2) if measurements else None

    pulse_record = {
        "parser_version": PULSE_RECORD_VERSION,
        "source_vendor": "zhongke",
        "source_format": "excel",
        "matched_sheet": matched_sheet,
        "side": side,
        "position": "\u516d\u90e8",
        "pulse_type": first[16] if len(first) > 16 else None,
        "pulse_rate": average(rate_values),
        "force": average(force_values),
        "tension": percent_value(average(tension_values)),
        "fluency": percent_value(average(fluency_values)),
        "amplitude": average(h1_values),
        "stability_score": stability_score,
        "valid_segment_count": valid_segment_count,
        "segment_count": len(measurements),
        "measurements": measurements,
        "waveform_summary": {},
        "waveform_preview": [],
        "detail": {
            "report_type": first[1] if len(first) > 1 else None,
            "case_number": first[7] if len(first) > 7 else None,
            "organization": first[8] if len(first) > 8 else None,
            "doctor": first[9] if len(first) > 9 else None,
        },
    }
    pulse_record.update(research_inclusion_policy(pulse_record, visit))
    return pulse_record


def pulse_record_from_structured(asset_payload: dict[str, Any], visit: Visit) -> dict[str, Any] | None:
    structured = asset_payload.get("structured")
    if not isinstance(structured, dict):
        return None
    if isinstance(structured.get("pulse_record"), dict):
        record = dict(structured["pulse_record"])
        record.setdefault("source_asset_id", asset_payload.get("asset_id"))
        record.setdefault("source_vendor", visit.source_vendor)
        return record
    fields = structured.get("fields")
    if isinstance(fields, dict) and asset_payload.get("asset_type") == "pulse_json":
        return yushengtang_record(asset_payload, fields, visit)
    return None


def build_pulse_records(visit: Visit, parsed_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for asset in parsed_assets:
        if asset.get("parse_status") != "ok":
            continue
        record = pulse_record_from_structured(asset, visit)
        if not record:
            continue
        record.setdefault("parser_version", PULSE_RECORD_VERSION)
        record.setdefault("source_asset_id", asset.get("asset_id"))
        record.setdefault("asset_file_name", asset.get("file_name"))
        records.append(record)
    return records
