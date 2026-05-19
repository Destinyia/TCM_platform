from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import shutil
import sys
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - optional runtime dependency
    tqdm = None

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


STORAGE_ROOT = PROJECT_ROOT / "storage"
STORAGE_URI_PREFIX = "local://tcm-platform"
RUN_VERSION = datetime.now().strftime("%Y%m%d_%H%M%S")
DEFAULT_SCOPE = "april_checkin"
DEFAULT_INGEST_API = "http://localhost:5000/api/ingest/standard-storage"
DEFAULT_PARSE_API = "http://localhost:5000/api/ingest/parse-structured-data"
PARSER_NAME = "generate_april_checkin_matrix"
PARSER_RULE_VERSION = "unknown"
april = None
rv = None
MODALITY_COLUMNS = {}
ASSET_TYPE_BY_MODALITY = {
    "ask": "source_json",
    "pulse": "pulse_json",
    "tongue": "tongue_json",
    "voice": "voice_json",
    "face": "face_source",
    "report": "report_pdf",
}
ASSET_ROLE_BY_MODALITY = {
    "ask": "standard",
    "pulse": "standard",
    "tongue": "standard",
    "voice": "standard",
    "face": "standard",
    "report": "raw",
}
TRAINING_ELIGIBLE = {"pulse", "tongue", "voice", "face"}
HASH_CACHE: dict[Path, tuple[str, str]] = {}
SMOKE_RECORDS_PER_VENDOR = 8


def load_parser_modules() -> None:
    global PARSER_RULE_VERSION, MODALITY_COLUMNS, april, rv
    if april is not None and rv is not None:
        return
    import generate_april_checkin_matrix as april_module
    import run_cohort_validation_v1 as rv_module

    april = april_module
    rv = rv_module
    PARSER_RULE_VERSION = getattr(rv, "RULE_VERSION", "unknown")
    MODALITY_COLUMNS = {
        "ask": (april.COL_ASK, april.COL_ASK_PATH),
        "pulse": (april.COL_PULSE, april.COL_PULSE_PATH),
        "tongue": (april.COL_TONGUE, april.COL_TONGUE_PATH),
        "voice": (april.COL_VOICE, april.COL_VOICE_PATH),
        "face": (april.COL_FACE, april.COL_FACE_PATH),
        "report": (april.COL_PDF, april.COL_PDF_PATH),
    }


def storage_uri(path: Path, storage_root: Path) -> str:
    return f"{STORAGE_URI_PREFIX}/{path.relative_to(storage_root).as_posix()}"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def clean_part(value: object, fallback: str = "unknown") -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return fallback
    keep = []
    for char in text:
        if char.isalnum() or char in {"-", "_", "."}:
            keep.append(char)
        else:
            keep.append("_")
    cleaned = "".join(keep).strip("._")
    return cleaned or fallback


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix in {".xls", ".xlsx"}:
        return "application/vnd.ms-excel"
    return "application/octet-stream"


def deterministic_uuid(namespace: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, namespace))


def progress(iterable, *, total: int | None = None, desc: str = "", unit: str = "it"):
    if tqdm is not None:
        return tqdm(iterable, total=total, desc=desc, unit=unit)
    return iterable


def file_hashes(path: Path) -> tuple[str, str]:
    resolved = path.resolve()
    if resolved not in HASH_CACHE:
        HASH_CACHE[resolved] = (sha256_file(path), md5_file(path))
    return HASH_CACHE[resolved]


def safe_copy_file(source: Path, destination: Path, *, dry_run: bool, overwrite: bool) -> bool:
    if not source.exists() or not source.is_file():
        return False
    if destination.exists() and not overwrite:
        return False
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return True


def safe_copy_tree(source: Path, destination: Path, *, dry_run: bool, overwrite: bool) -> int:
    if not source.exists():
        return 0
    copied = 0
    files = [file_path for file_path in source.rglob("*") if file_path.is_file()]
    for file_path in progress(files, total=len(files), desc=f"Copy {source.name}", unit="file"):
        if not file_path.is_file():
            continue
        try:
            relative = file_path.relative_to(source)
        except ValueError:
            continue
        copied += int(safe_copy_file(file_path, destination / relative, dry_run=dry_run, overwrite=overwrite))
    return copied


def existing_path(value: object) -> Path | None:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return None
    path = Path(text)
    return path if path.exists() else None


def infer_asset_type(modality: str, path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".xls", ".xlsx"}:
        return "source_excel"
    if suffix == ".csv":
        return "source_csv"
    if suffix == ".pdf":
        return "report_pdf"
    if suffix in {".jpg", ".jpeg", ".png", ".bmp"}:
        name = path.name.lower()
        if modality == "pulse":
            return "pulse_image"
        if modality == "tongue":
            if "origin" in name:
                return "tongue_origin"
            if "cut" in name:
                return "tongue_cut"
            if "rectangle" in name:
                return "tongue_region"
            return "tongue_image"
        if modality == "face":
            return "face_origin"
        return "preview_image"
    if suffix == ".wav":
        return "voice_wav"
    return ASSET_TYPE_BY_MODALITY.get(modality, "unknown_type")


def should_keep_standard_asset(modality: str, path: Path, asset_type: str) -> bool:
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
        return True
    name = path.stem.lower()
    if "分割" in name or "分区" in name:
        return False
    if "cut" in name or "rectangle" in name or "seg" in name or "region" in name:
        return False
    if "原图" in name or "origin" in name:
        return True
    return modality not in {"tongue", "face"} or asset_type in {"tongue_origin", "face_origin", "pulse_image"}


def row_timestamp(row: pd.Series) -> pd.Timestamp | None:
    date_value = pd.to_datetime(row.get(april.COL_DATE), errors="coerce")
    if pd.isna(date_value):
        return None
    time_text = str(row.get(april.COL_TIME) or "").strip()
    merged = pd.to_datetime(f"{pd.Timestamp(date_value).strftime('%Y-%m-%d')} {time_text}", errors="coerce")
    if pd.isna(merged):
        return pd.Timestamp(date_value)
    return pd.Timestamp(merged)


def source_vendor_key(row: pd.Series) -> str:
    key = str(row.get("_vendor_key") or "").strip()
    if key:
        return "yushengtang" if key == "yst" else key
    vendor = str(row.get(april.COL_VENDOR) or "").strip()
    if vendor == "玉生堂":
        return "yushengtang"
    if vendor == "中科":
        return "zhongke"
    return clean_part(vendor, "unknown")


def source_record_group_id(row: pd.Series) -> str:
    vendor = source_vendor_key(row)
    case_id = clean_part(row.get(april.COL_CASE_ID), "no_case")
    ts = row_timestamp(row)
    time_key = ts.strftime("%Y%m%d%H%M%S") if ts is not None else "no_time"
    name_key = hashlib.sha1(str(row.get(april.COL_NAME) or "").encode("utf-8")).hexdigest()[:10]
    if vendor == "yushengtang":
        return f"yushengtang_{case_id}"
    return f"zhongke_{case_id}_{name_key}_{time_key}"


def source_batch_id(vendor: str, scope: str) -> str:
    return f"{vendor}_{scope}_{RUN_VERSION}"


def build_april_detail() -> tuple[pd.DataFrame, list[str]]:
    load_parser_modules()
    rv.ensure_output_dirs()
    cohort_names, caid_to_name, phone_to_name = april.load_cohort_identity_map()
    if not cohort_names:
        cohort_names = sorted(path.name for path in rv.REFERENCE_DIR.iterdir() if path.is_dir())
    alias_map = rv.load_name_alias_config()
    alias_map.update({rv.normalize_name(name): name for name in cohort_names})

    yst_detail = april.build_raw_detail(cohort_names, caid_to_name, phone_to_name, alias_map)
    yst_detail = yst_detail.loc[
        (yst_detail[april.COL_DUP].astype(str).ne(""))
        | (
            (pd.to_datetime(yst_detail[april.COL_DATE], errors="coerce") >= april.APRIL_START)
            & (pd.to_datetime(yst_detail[april.COL_DATE], errors="coerce") < april.APRIL_END)
        )
        | (yst_detail[april.COL_DATE].astype(str).eq(""))
    ].copy()
    zhongke_detail = april.build_zhongke_detail(cohort_names, alias_map)
    detail = pd.concat([yst_detail, zhongke_detail], ignore_index=True, sort=False).fillna("")
    detail = april.assign_slots(detail, cohort_names)
    return detail, cohort_names


def summarize_detail(detail: pd.DataFrame) -> dict[str, int]:
    return {
        "total": int(len(detail)),
        "zhongke": int(detail[detail.apply(source_vendor_key, axis=1).eq("zhongke")].shape[0]),
        "yushengtang": int(detail[detail.apply(source_vendor_key, axis=1).eq("yushengtang")].shape[0]),
        "matrix_candidates": int(detail.get("_is_matrix_candidate", pd.Series(dtype=bool)).fillna(False).sum()),
    }


def smoke_sample(detail: pd.DataFrame, records_per_vendor: int) -> pd.DataFrame:
    samples = []
    for vendor in ("zhongke", "yushengtang"):
        vendor_rows = detail.loc[detail.apply(source_vendor_key, axis=1).eq(vendor)].copy()
        if vendor_rows.empty:
            continue
        candidate_rows = vendor_rows.loc[vendor_rows.get("_is_matrix_candidate", False).astype(bool)] if "_is_matrix_candidate" in vendor_rows else vendor_rows
        selected = candidate_rows.head(records_per_vendor)
        if len(selected) < records_per_vendor:
            selected = pd.concat([selected, vendor_rows.head(records_per_vendor - len(selected))], ignore_index=False)
        samples.append(selected.drop_duplicates())
    if not samples:
        return detail.head(records_per_vendor).copy()
    return pd.concat(samples, ignore_index=True, sort=False).fillna("")


def extra_yushengtang_assets(case_dir: Path) -> list[tuple[str, Path]]:
    candidates = [
        ("pulse_image", case_dir / "pulse" / "pulseImage.jpg"),
        ("tongue_origin", case_dir / "tongue" / "OriginPic.jpg"),
    ]
    return [(asset_type, path) for asset_type, path in candidates if path.exists()]


def modality_assets(row: pd.Series) -> list[dict]:
    assets = []
    for modality, (flag_col, path_col) in MODALITY_COLUMNS.items():
        path = existing_path(row.get(path_col))
        if not path:
            continue
        asset_type = infer_asset_type(modality, path)
        if not should_keep_standard_asset(modality, path, asset_type):
            continue
        assets.append(
            {
                "modality": modality,
                "asset_type": asset_type,
                "asset_role": ASSET_ROLE_BY_MODALITY[modality],
                "source_path": path,
                "is_training_eligible": modality in TRAINING_ELIGIBLE,
                "present_flag": bool(str(row.get(flag_col) or "").strip()),
            }
        )
    case_dir = existing_path(row.get(april.COL_CASE_DIR))
    if source_vendor_key(row) == "yushengtang" and case_dir and case_dir.is_dir():
        for asset_type, path in extra_yushengtang_assets(case_dir):
            modality = "pulse" if asset_type.startswith("pulse") else "tongue"
            assets.append(
                {
                    "modality": modality,
                    "asset_type": asset_type,
                    "asset_role": "standard",
                    "source_path": path,
                    "is_training_eligible": asset_type in {"tongue_origin", "tongue_cut"},
                    "present_flag": True,
                }
            )
    return assets


def relative_to_any(path: Path, roots: Iterable[Path]) -> str:
    for root in roots:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return path.name


def copy_raw_source(
    row: pd.Series,
    storage_root: Path,
    batch_lookup: dict[str, str],
    *,
    dry_run: bool,
    overwrite: bool,
) -> list[dict]:
    vendor = source_vendor_key(row)
    batch_id = batch_lookup[vendor]
    copied_sources = []
    if vendor == "yushengtang":
        case_dir = existing_path(row.get(april.COL_CASE_DIR))
        if case_dir and case_dir.is_dir():
            destination = storage_root / "raw" / vendor / batch_id / "source" / clean_part(case_dir.parent.name) / clean_part(case_dir.name)
            copied_count = safe_copy_tree(case_dir, destination, dry_run=dry_run, overwrite=overwrite)
            copied_sources.append(
                {
                    "source_path": str(case_dir),
                    "raw_storage_path": str(destination),
                    "raw_storage_uri": storage_uri(destination, storage_root),
                    "copied_file_count": copied_count,
                    "copy_grain": "case_dir",
                }
            )
    else:
        seen = set()
        for asset in modality_assets(row):
            source_path: Path = asset["source_path"]
            if source_path in seen:
                continue
            seen.add(source_path)
            relative = relative_to_any(source_path, [april.ZHONGKE_APRIL_DIR, april.ZHONGKE_APRIL_DIR.parent])
            destination = storage_root / "raw" / vendor / batch_id / "source" / relative
            copied = safe_copy_file(source_path, destination, dry_run=dry_run, overwrite=overwrite)
            copied_sources.append(
                {
                    "source_path": str(source_path),
                    "raw_storage_path": str(destination),
                    "raw_storage_uri": storage_uri(destination, storage_root),
                    "copied_file_count": int(copied),
                    "copy_grain": "source_file",
                }
            )
    return copied_sources


def register_standard_asset(
    asset: dict,
    row: pd.Series,
    storage_root: Path,
    *,
    dry_run: bool,
    overwrite: bool,
) -> dict | None:
    source_path: Path = asset["source_path"]
    if not source_path.exists() or not source_path.is_file():
        return None
    if dry_run:
        sha256 = hashlib.sha256(str(source_path.resolve()).encode("utf-8")).hexdigest()
        md5 = ""
    else:
        sha256, md5 = file_hashes(source_path)
    asset_id = deterministic_uuid(f"{sha256}:{source_path.name}:{asset['asset_type']}")
    suffix = source_path.suffix.lower() or ".bin"
    destination = storage_root / "standard" / "assets" / asset["asset_type"] / sha256[:2] / f"{asset_id}{suffix}"
    safe_copy_file(source_path, destination, dry_run=dry_run, overwrite=overwrite)
    stat = source_path.stat()
    return {
        "asset_id": asset_id,
        "source_vendor": source_vendor_key(row),
        "source_visit_id": str(row.get(april.COL_CASE_ID) or ""),
        "source_record_group_id": source_record_group_id(row),
        "modality": asset["modality"],
        "asset_type": asset["asset_type"],
        "asset_role": asset["asset_role"],
        "file_name": source_path.name,
        "file_path": str(source_path),
        "source_relative_path": relative_to_any(source_path, [april.YST_APRIL_DIR, april.YST_APRIL_DIR.parent, april.ZHONGKE_APRIL_DIR, april.ZHONGKE_APRIL_DIR.parent]),
        "standard_path": str(destination),
        "storage_uri": storage_uri(destination, storage_root),
        "file_hash": f"sha256:{sha256}",
        "md5": md5,
        "file_size": stat.st_size,
        "mime_type": file_mime(source_path),
        "created_at_from_file": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "parsed_success_flag": asset["present_flag"],
        "is_training_eligible": asset["is_training_eligible"],
        "excluded_reason": "" if asset["is_training_eligible"] else "not_training_asset",
    }


def write_json(path: Path, payload: object, *, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict], *, dry_run: bool) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict], *, dry_run: bool) -> None:
    if dry_run or not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def notify_backend_ingest(api_url: str, records_path: Path, assets_path: Path) -> bool:
    payload = json.dumps(
        {
            "records_path": str(records_path),
            "assets_path": str(assets_path),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Backend ingest notify failed: HTTP {exc.code} {exc.reason}: {body}")
        return False
    except urllib.error.URLError as exc:
        print(f"Backend ingest notify failed: {exc}")
        return False
    print(f"Backend ingest response: {body}")
    return True


def notify_backend_parse(
    api_url: str,
    *,
    source_vendor: str | None = None,
    visit_id: str | None = None,
    limit: int | None = None,
    only_missing: bool = False,
) -> bool:
    payload_dict = {
        "only_missing": only_missing,
    }
    if source_vendor:
        payload_dict["source_vendor"] = source_vendor
    if visit_id:
        payload_dict["visit_id"] = visit_id
    if limit:
        payload_dict["limit"] = limit
    payload = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Backend parse notify failed: HTTP {exc.code} {exc.reason}: {body}")
        return False
    except urllib.error.URLError as exc:
        print(f"Backend parse notify failed: {exc}")
        return False
    print(f"Backend parse response: {body}")
    return True


def latest_matching_file(directory: Path, pattern: str) -> Path:
    candidates = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No file matched: {directory / pattern}")
    return candidates[0]


def resolve_db_sync_paths(storage_root: Path, scope: str, records_path: Path | None, assets_path: Path | None) -> tuple[Path, Path]:
    records = records_path or latest_matching_file(storage_root / "standard" / "records", f"records_{scope}_*.jsonl")
    assets = assets_path or latest_matching_file(storage_root / "standard" / "assets", f"asset_inventory_{scope}_*.jsonl")
    return records.resolve(), assets.resolve()


def record_payload(row: pd.Series, assets: list[dict], raw_sources: list[dict]) -> dict:
    ts = row_timestamp(row)
    modalities = sorted({asset["modality"] for asset in assets})
    return {
        "source_vendor": source_vendor_key(row),
        "source_vendor_name": str(row.get(april.COL_VENDOR) or ""),
        "source_visit_id": str(row.get(april.COL_CASE_ID) or ""),
        "source_record_group_id": source_record_group_id(row),
        "canonical_name": str(row.get(april.COL_NAME) or ""),
        "collected_at": ts.isoformat() if ts is not None else None,
        "visit_date": ts.strftime("%Y-%m-%d") if ts is not None else "",
        "time_window_slot": str(row.get(april.COL_SLOT) or ""),
        "quality_status": str(row.get(april.COL_STATUS) or ""),
        "quality_flags": [part for part in str(row.get(april.COL_REMARK) or "").split("；") if part],
        "modalities": modalities,
        "source_evidence": raw_sources,
        "assets": assets,
        "parser": {
            "name": PARSER_NAME,
            "rule_version": PARSER_RULE_VERSION,
            "zhongke_source": str(april.ZHONGKE_APRIL_DIR),
            "yushengtang_source": str(april.YST_APRIL_DIR),
        },
        "generated_at": now_iso(),
    }


def modality_index_payload(record: dict) -> dict:
    grouped: dict[str, list[dict]] = {}
    for asset in record["assets"]:
        grouped.setdefault(asset["modality"], []).append(
            {
                "asset_id": asset["asset_id"],
                "asset_type": asset["asset_type"],
                "asset_role": asset["asset_role"],
                "storage_uri": asset["storage_uri"],
                "file_hash": asset["file_hash"],
                "is_training_eligible": asset["is_training_eligible"],
            }
        )
    return {
        "source_record_group_id": record["source_record_group_id"],
        "source_vendor": record["source_vendor"],
        "modalities": grouped,
        "generated_at": record["generated_at"],
    }


def write_raw_manifests(storage_root: Path, batch_lookup: dict[str, str], detail: pd.DataFrame, *, dry_run: bool) -> None:
    for vendor, batch_id in batch_lookup.items():
        vendor_rows = detail.loc[detail.apply(source_vendor_key, axis=1).eq(vendor)]
        manifest = {
            "batch_id": batch_id,
            "source_vendor": vendor,
            "source_batch_name": DEFAULT_SCOPE,
            "received_at": now_iso(),
            "operator": "offline_script",
            "root_policy": "immutable_after_registered",
            "record_count": int(len(vendor_rows)),
            "parser": {
                "name": PARSER_NAME,
                "rule_version": PARSER_RULE_VERSION,
                "zhongke_source": str(april.ZHONGKE_APRIL_DIR),
                "yushengtang_source": str(april.YST_APRIL_DIR),
            },
            "notes": "Generated by scripts/organize_offline_storage.py from April checkin detail.",
        }
        write_json(storage_root / "raw" / vendor / batch_id / "manifest.json", manifest, dry_run=dry_run)


def build_checkin_matrix(detail: pd.DataFrame, cohort_names: list[str]) -> pd.DataFrame:
    date_index = pd.date_range(april.APRIL_START, april.APRIL_END - pd.Timedelta(days=1), freq="D")
    return april.matrix_from_detail(detail, cohort_names, date_index)


def main() -> None:
    global DEFAULT_SCOPE

    parser = argparse.ArgumentParser(description="Copy offline source data into standardized local storage.")
    parser.add_argument("--storage-root", type=Path, default=STORAGE_ROOT)
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Run a small dry-run sample against both April vendors.")
    parser.add_argument("--smoke-records-per-vendor", type=int, default=SMOKE_RECORDS_PER_VENDOR)
    parser.add_argument("--ingest-api", default=DEFAULT_INGEST_API)
    parser.add_argument("--parse-api", default=DEFAULT_PARSE_API)
    parser.add_argument("--no-db-sync", action="store_true", help="Do not call backend ingest API after full offline organization.")
    parser.add_argument("--no-parse-sync", action="store_true", help="Do not call backend structured parse API after successful DB sync.")
    parser.add_argument("--db-sync-only", action="store_true", help="Skip offline organization and only notify backend ingest API with existing JSONL outputs.")
    parser.add_argument("--parse-only", action="store_true", help="Skip offline organization and only call backend structured parse API.")
    parser.add_argument("--records-path", type=Path, help="Existing records_*.jsonl path for --db-sync-only.")
    parser.add_argument("--assets-path", type=Path, help="Existing asset_inventory_*.jsonl path for --db-sync-only.")
    parser.add_argument("--parse-source-vendor", choices=["zhongke", "yushengtang"], help="Limit backend structured parse to one source vendor.")
    parser.add_argument("--parse-visit-id", help="Limit backend structured parse to one visit UUID.")
    parser.add_argument("--parse-limit", type=int, help="Limit backend structured parse visit count.")
    parser.add_argument("--parse-only-missing", action="store_true", help="Only parse modality records without stored structured data.")
    args = parser.parse_args()

    DEFAULT_SCOPE = clean_part(args.scope, DEFAULT_SCOPE)

    storage_root = args.storage_root.resolve()
    if args.parse_only:
        print(f"StorageRoot: {storage_root}")
        print("ParseOnly: True")
        notify_backend_parse(
            args.parse_api,
            source_vendor=args.parse_source_vendor,
            visit_id=args.parse_visit_id,
            limit=args.parse_limit,
            only_missing=args.parse_only_missing,
        )
        return

    if args.db_sync_only:
        records_path, assets_path = resolve_db_sync_paths(storage_root, DEFAULT_SCOPE, args.records_path, args.assets_path)
        print(f"StorageRoot: {storage_root}")
        print("DbSyncOnly: True")
        print(f"RecordsJsonl: {records_path}")
        print(f"AssetsJsonl: {assets_path}")
        if notify_backend_ingest(args.ingest_api, records_path, assets_path) and not args.no_parse_sync:
            notify_backend_parse(
                args.parse_api,
                source_vendor=args.parse_source_vendor,
                visit_id=args.parse_visit_id,
                limit=args.parse_limit,
                only_missing=args.parse_only_missing,
            )
        return

    detail, cohort_names = build_april_detail()
    full_summary = summarize_detail(detail)
    if args.smoke:
        args.dry_run = True
        detail = smoke_sample(detail, max(1, args.smoke_records_per_vendor))
    batch_lookup = {
        "zhongke": source_batch_id("zhongke", DEFAULT_SCOPE),
        "yushengtang": source_batch_id("yushengtang", DEFAULT_SCOPE),
    }
    write_raw_manifests(storage_root, batch_lookup, detail, dry_run=args.dry_run)

    inventory_rows: list[dict] = []
    asset_rows_by_key: dict[str, dict] = {}
    record_rows: list[dict] = []
    raw_copy_rows: list[dict] = []

    rows_iter = progress(detail.iterrows(), total=len(detail), desc="Organizing records", unit="record")
    for index, row in rows_iter:
        if tqdm is None and (index == 0 or (index + 1) % 100 == 0 or index + 1 == len(detail)):
            print(f"Organizing records: {index + 1}/{len(detail)}")
        record_id = source_record_group_id(row)
        raw_sources = copy_raw_source(row, storage_root, batch_lookup, dry_run=args.dry_run, overwrite=args.overwrite)
        raw_copy_rows.extend({**item, "source_record_group_id": record_id, "source_vendor": source_vendor_key(row)} for item in raw_sources)

        assets = []
        for asset in modality_assets(row):
            registered = register_standard_asset(asset, row, storage_root, dry_run=args.dry_run, overwrite=args.overwrite)
            if registered is None:
                continue
            asset_rows_by_key.setdefault(registered["asset_id"], registered)
            assets.append(registered)

        record = record_payload(row, assets, raw_sources)
        record_rows.append(record)
        record_dir = storage_root / "standard" / "records" / record["source_vendor"] / record_id
        write_json(record_dir / "record.json", record, dry_run=args.dry_run)
        write_json(record_dir / "modality_index.json", modality_index_payload(record), dry_run=args.dry_run)

    asset_rows = list(asset_rows_by_key.values())
    inventory_rows.extend(asset_rows)
    for vendor, batch_id in batch_lookup.items():
        vendor_inventory = [row for row in inventory_rows if row["source_vendor"] == vendor]
        inventory_dir = storage_root / "raw" / vendor / batch_id / "inventory"
        write_jsonl(inventory_dir / "file_inventory.jsonl", vendor_inventory, dry_run=args.dry_run)
        write_csv(inventory_dir / "file_inventory.csv", vendor_inventory, dry_run=args.dry_run)
        write_jsonl(inventory_dir / "raw_copy_log.jsonl", [row for row in raw_copy_rows if row["source_vendor"] == vendor], dry_run=args.dry_run)

    mart_dir = storage_root / "mart" / "user_day_panel"
    matrix = build_checkin_matrix(detail, cohort_names)
    if not args.dry_run:
        mart_dir.mkdir(parents=True, exist_ok=True)
        detail.drop(columns=[column for column in detail.columns if column.startswith("_sort")], errors="ignore").to_csv(
            mart_dir / f"april_checkin_detail_{RUN_VERSION}.csv",
            index=False,
            encoding="utf-8-sig",
        )
        matrix.to_csv(mart_dir / f"april_checkin_matrix_{RUN_VERSION}.csv", encoding="utf-8-sig")
    records_output = storage_root / "standard" / "records" / f"records_{DEFAULT_SCOPE}_{RUN_VERSION}.jsonl"
    assets_output = storage_root / "standard" / "assets" / f"asset_inventory_{DEFAULT_SCOPE}_{RUN_VERSION}.jsonl"
    write_jsonl(records_output, record_rows, dry_run=args.dry_run)
    write_jsonl(assets_output, asset_rows, dry_run=args.dry_run)
    if not args.dry_run and not args.no_db_sync:
        if notify_backend_ingest(args.ingest_api, records_output, assets_output) and not args.no_parse_sync:
            notify_backend_parse(
                args.parse_api,
                source_vendor=args.parse_source_vendor,
                visit_id=args.parse_visit_id,
                limit=args.parse_limit,
                only_missing=args.parse_only_missing,
            )

    print(f"StorageRoot: {storage_root}")
    print(f"Smoke: {args.smoke}")
    print(f"DryRun: {args.dry_run}")
    print(f"SourceSummary: {full_summary}")
    print(f"Records: {len(record_rows)}")
    print(f"UniqueAssets: {len(asset_rows)}")
    print(f"RawCopyEntries: {len(raw_copy_rows)}")
    print(f"Batches: {batch_lookup}")
    if not args.dry_run:
        print(f"MartDetail: {mart_dir / f'april_checkin_detail_{RUN_VERSION}.csv'}")
        print(f"MartMatrix: {mart_dir / f'april_checkin_matrix_{RUN_VERSION}.csv'}")
        print(f"RecordsJsonl: {records_output}")
        print(f"AssetsJsonl: {assets_output}")


if __name__ == "__main__":
    main()
