from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from backend.app.config import STORAGE_ROOT, STORAGE_URI_PREFIX
from backend.app.models import FileAsset, Visit
from backend.app.pulse_parser import build_pulse_records, parse_zhongke_pulse_excel, yushengtang_record

MAX_LIST_ITEMS = 6
MAX_DICT_KEYS = 40
MAX_TEXT_LEN = 240


def resolve_shared_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.exists():
        return path
    text = str(value)
    windows_match = re.match(r"^([A-Za-z]):[\\/](.*)$", text)
    if windows_match:
        drive = windows_match.group(1).lower()
        rest = windows_match.group(2).replace("\\", "/")
        candidate = Path(f"/mnt/{drive}/{rest}")
        if candidate.exists():
            return candidate
    wsl_match = re.match(r"^/mnt/([A-Za-z])/(.*)$", text)
    if wsl_match:
        drive = wsl_match.group(1).upper()
        rest = wsl_match.group(2).replace("/", "\\")
        candidate = Path(f"{drive}:\\{rest}")
        if candidate.exists():
            return candidate
    return None


def local_storage_path(storage_uri: str | None) -> Path | None:
    if not storage_uri or not storage_uri.startswith(f"{STORAGE_URI_PREFIX}/"):
        return None
    relative = storage_uri.removeprefix(f"{STORAGE_URI_PREFIX}/")
    path = (STORAGE_ROOT / relative).resolve()
    try:
        path.relative_to(STORAGE_ROOT)
    except ValueError:
        return None
    return path if path.exists() else None


def asset_path(asset: FileAsset) -> Path | None:
    return local_storage_path(asset.storage_uri) or resolve_shared_path(asset.file_path)


def json_safe(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    if not isinstance(value, (dict, list, tuple, str, bytes)):
        try:
            if pd.isna(value):
                return None
        except TypeError:
            pass
    return value


def compact_value(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= MAX_DICT_KEYS:
                result["_truncated_keys"] = len(value) - MAX_DICT_KEYS
                break
            result[str(key)] = compact_value(item)
        return result
    if isinstance(value, list):
        return {
            "_type": "list",
            "count": len(value),
            "sample": [compact_value(item) for item in value[:MAX_LIST_ITEMS]],
        }
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in {"[", "{"}:
            try:
                return compact_value(json.loads(stripped))
            except json.JSONDecodeError:
                pass
        return value if len(value) <= MAX_TEXT_LEN else value[:MAX_TEXT_LEN] + "..."
    return json_safe(value)


def read_text_relaxed(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def parse_json_asset(path: Path) -> dict[str, Any]:
    payload = json.loads(read_text_relaxed(path))
    summary = compact_value(payload)
    if isinstance(payload, dict):
        return {
            "parser": "json",
            "top_level_type": "object",
            "field_count": len(payload),
            "fields": summary,
        }
    if isinstance(payload, list):
        return {
            "parser": "json",
            "top_level_type": "array",
            "row_count": len(payload),
            "rows": summary,
        }
    return {"parser": "json", "value": summary}


def normalize_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def row_has_needles(row: list[Any], needles: list[str]) -> bool:
    text = " ".join(str(value) for value in row if value is not None)
    return any(needle and needle in text for needle in needles)


def parse_excel_asset(path: Path, visit: Visit) -> dict[str, Any]:
    raw_source_visit_id = ""
    if visit.cheat_types:
        raw_source_visit_id = str(visit.cheat_types.get("raw_source_visit_id") or "")
    needles = [raw_source_visit_id, str(visit.source_visit_id or "")]
    sheets = []
    excel = pd.ExcelFile(path)
    for sheet_name in excel.sheet_names:
        frame = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=object)
        rows = []
        matched_rows = []
        for row_index, (_, row) in enumerate(frame.iterrows(), start=1):
            values = [normalize_cell(value) for value in row.tolist()]
            if len(rows) < 8 and any(value is not None and str(value).strip() for value in values):
                rows.append({"row": row_index, "values": values[:16]})
            if row_has_needles(values, needles):
                matched_rows.append({"row": row_index, "values": values[:24]})
            if len(matched_rows) >= 12:
                break
        sheets.append(
            {
                "sheet_name": sheet_name,
                "rows": int(frame.shape[0]),
                "columns": int(frame.shape[1]),
                "matched_rows": matched_rows,
                "preview_rows": rows,
            }
        )
    return {"parser": "excel", "raw_source_visit_id": raw_source_visit_id, "sheets": sheets}


def parse_asset(asset: FileAsset, visit: Visit) -> dict[str, Any]:
    path = asset_path(asset)
    base = {
        "asset_id": str(asset.asset_id),
        "asset_type": asset.asset_type,
        "file_name": asset.file_name,
        "storage_uri": asset.storage_uri,
    }
    if not path:
        return {**base, "parse_status": "missing_file"}
    try:
        suffix = path.suffix.lower()
        if suffix == ".json":
            structured = parse_json_asset(path)
            if asset.asset_type == "pulse_json":
                raw_payload = json.loads(read_text_relaxed(path))
                if isinstance(raw_payload, dict):
                    structured["pulse_record"] = yushengtang_record(base, raw_payload, visit)
            return {**base, "parse_status": "ok", "structured": structured}
        if suffix in {".xls", ".xlsx"}:
            structured = parse_excel_asset(path, visit)
            if asset.asset_type == "source_excel" and "脉诊" in (asset.file_name or ""):
                pulse_record = parse_zhongke_pulse_excel(path, visit)
                structured["parser"] = "zhongke_pulse_excel" if pulse_record else structured.get("parser")
                if pulse_record:
                    structured["pulse_record"] = pulse_record
            return {**base, "parse_status": "ok", "structured": structured}
        return {
            **base,
            "parse_status": "metadata_only",
            "structured": {
                "parser": "asset_metadata",
                "mime_type": asset.mime_type,
                "file_size": asset.file_size,
            },
        }
    except Exception as exc:
        return {**base, "parse_status": "failed", "error": str(exc)}


def infer_modality(asset: FileAsset) -> str:
    if asset.asset_type in {"source_json"} and asset.file_name == "dataAsk.json":
        return "ask"
    if asset.asset_type == "source_excel":
        file_name = asset.file_name or ""
        if "问诊" in file_name:
            return "ask"
        if "脉诊" in file_name:
            return "pulse"
        if "舌诊" in file_name:
            return "tongue"
        if "面诊" in file_name:
            return "face"
    if asset.asset_type in {"pulse_json", "pulse_image"}:
        return "pulse"
    if asset.asset_type in {"tongue_json", "tongue_origin", "tongue_image"}:
        return "tongue"
    if asset.asset_type in {"voice_json", "voice_wav"}:
        return "voice"
    if asset.asset_type in {"face_source", "face_origin"}:
        return "face"
    if asset.asset_type == "report_pdf":
        return "report"
    return "source"


def build_structured_modalities(
    visit: Visit,
    assets: list[FileAsset],
    modality_by_record_id: dict[Any, str] | None = None,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[FileAsset]] = {}
    modality_by_record_id = modality_by_record_id or {}
    for asset in assets:
        modality = modality_by_record_id.get(asset.modality_record_id) if asset.modality_record_id else None
        if not modality:
            modality = infer_modality(asset)
        grouped.setdefault(modality, []).append(asset)

    result = {}
    for modality, modality_assets in grouped.items():
        parsed_assets = [parse_asset(asset, visit) for asset in modality_assets]
        modality_payload = {
            "source_vendor": visit.source_vendor,
            "asset_count": len(modality_assets),
            "assets": parsed_assets,
        }
        if modality == "pulse":
            modality_payload["records"] = build_pulse_records(visit, parsed_assets)
        result[modality] = modality_payload
    return result
