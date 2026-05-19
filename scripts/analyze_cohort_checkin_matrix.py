from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from io import BytesIO
from pathlib import Path

import matplotlib.pyplot as plt
import openpyxl
import pandas as pd
import xlsxwriter
import xlrd
from matplotlib.colors import BoundaryNorm, ListedColormap


def u(text: str) -> str:
    return text.encode("ascii").decode("unicode_escape")


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KNOWN_ROOTS = {"datasets", "docs", "frontend", "scripts", "__pycache__"}
DATA_ROOT = next(path for path in PROJECT_ROOT.iterdir() if path.is_dir() and path.name not in KNOWN_ROOTS)
OUTPUT_DIR = PROJECT_ROOT / "datasets" / "organized_checkin_matrix"
WORKBOOK_OUTPUT = OUTPUT_DIR / "cohort_checkin_matrix_20251108.xlsx"
PLOT_OUTPUT = OUTPUT_DIR / "cohort_checkin_heatmap_20251108.png"
START_DATE = pd.Timestamp("2025-11-08")
REFERENCE_DIR = DATA_ROOT / u("\\u4e2d\\u79d1\\u56db\\u8bca\\u4eea") / "2025.11.09-2025.12.10"
NAME_ALIAS_CONFIG = PROJECT_ROOT / "config" / "name_alias_rules_v1.json"
RULE_VERSION = "cohort_rule_v1_20260422"

SESSION_MERGE_MINUTES = 10
MIN_SLOT_GAP_MINUTES = 30
REQUIRED_MODALITY_THRESHOLD = 0.5
SLOT_LABELS = [u("\\u65e9"), u("\\u4e2d"), u("\\u665a")]
ZHONGKE_MODALITIES = ["ask", "pulse", "tongue", "face"]
YUSHENGTANG_MODALITIES = ["ask", "pulse", "tongue", "voice"]
LEADING_TS_RE = re.compile(r"^(\d{14})")

SHEET_PULSE = u("\\u8109\\u8bca\\u6570\\u636e")
SHEET_TONGUE = u("\\u820c\\u8bca\\u6570\\u636e")
SHEET_FACE = u("\\u9762\\u8bca\\u6570\\u636e")
SHEET_ASK = u("\\u95ee\\u8bca\\u6c47\\u603b")

COL_NAME = u("\\u59d3\\u540d")
COL_DATE = u("\\u65e5\\u671f")
COL_TIME = u("\\u5177\\u4f53\\u65f6\\u95f4")
COL_SLOT = u("\\u65f6\\u6bb5")
COL_STATUS = u("\\u72b6\\u6001")
COL_REMARK = u("\\u5907\\u6ce8")
COL_FOLDER_NAMES = u("\\u6587\\u4ef6\\u5939\\u59d3\\u540d")
COL_TABLE_NAMES = u("\\u8868\\u683c\\u59d3\\u540d")
COL_DUPLICATE = u("\\u7591\\u4f3c\\u91cd\\u590d\\u6570\\u503c")
COL_NAME_MISMATCH = u("\\u59d3\\u540d\\u4e0d\\u4e00\\u81f4")
COL_ZK_ASK = u("\\u4e2d\\u79d1_\\u95ee\\u8bca")
COL_ZK_PULSE = u("\\u4e2d\\u79d1_\\u8109\\u8bca\\u6ce2\\u5f62")
COL_ZK_TONGUE = u("\\u4e2d\\u79d1_\\u820c\\u8bca\\u56fe\\u7247")
COL_ZK_FACE = u("\\u4e2d\\u79d1_\\u9762\\u8bca\\u56fe\\u7247")
COL_YST_ASK = u("\\u7389\\u751f\\u5802_\\u95ee\\u8bca")
COL_YST_PULSE = u("\\u7389\\u751f\\u5802_\\u8109\\u8bca\\u6ce2\\u5f62")
COL_YST_TONGUE = u("\\u7389\\u751f\\u5802_\\u820c\\u8bca\\u56fe\\u7247")
COL_YST_VOICE = u("\\u7389\\u751f\\u5802_wav")
COL_ZK_ASK_PATH = u("\\u4e2d\\u79d1_\\u95ee\\u8bca\\u8def\\u5f84")
COL_ZK_PULSE_PATH = u("\\u4e2d\\u79d1_\\u8109\\u8bca\\u8def\\u5f84")
COL_ZK_TONGUE_PATH = u("\\u4e2d\\u79d1_\\u820c\\u8bca\\u8def\\u5f84")
COL_ZK_FACE_PATH = u("\\u4e2d\\u79d1_\\u9762\\u8bca\\u8def\\u5f84")
COL_YST_ASK_PATH = u("\\u7389\\u751f\\u5802_\\u95ee\\u8bca\\u8def\\u5f84")
COL_YST_PULSE_PATH = u("\\u7389\\u751f\\u5802_\\u8109\\u8bca\\u8def\\u5f84")
COL_YST_TONGUE_PATH = u("\\u7389\\u751f\\u5802_\\u820c\\u8bca\\u8def\\u5f84")
COL_YST_VOICE_PATH = u("\\u7389\\u751f\\u5802_wav\\u8def\\u5f84")
COL_DEVICE_COUNT = u("\\u8bbe\\u5907\\u6570")
COL_ZK_VISIT_IDS = u("\\u4e2d\\u79d1_\\u75c5\\u4f8b\\u53f7")
COL_YST_VISIT_IDS = u("\\u7389\\u751f\\u5802_TreatNumber")
SHEET_MATRIX = u("\\u6253\\u5361\\u77e9\\u9635")
SHEET_DETAIL = u("\\u8be6\\u7ec6\\u8bb0\\u5f55")
SHEET_RULES = u("\\u89c4\\u5219\\u8bf4\\u660e")
MODALITY_LABELS = {
    "ask": u("\\u95ee\\u8bca"),
    "pulse": u("\\u8109\\u8bca\\u6ce2\\u5f62"),
    "tongue": u("\\u820c\\u8bca\\u56fe\\u7247"),
    "face": u("\\u9762\\u8bca\\u56fe\\u7247"),
    "voice": "wav",
}

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def ensure_output_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_name_alias_config() -> dict[str, str]:
    if not NAME_ALIAS_CONFIG.exists():
        return {}
    payload = json.loads(NAME_ALIAS_CONFIG.read_text(encoding="utf-8"))
    return {normalize_name(key): str(value).strip() for key, value in payload.get("aliases", {}).items()}


def canonicalize_name(value: object, alias_map: dict[str, str]) -> str:
    raw = str(value or "").replace("\n", "").replace("\r", "").strip()
    if not raw:
        return ""
    return alias_map.get(normalize_name(raw), raw)


def normalize_name(value: object) -> str:
    return re.sub(r"[\s·•\.\-—_・]+", "", str(value or "").strip()).casefold()


def coerce_id(value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
        if abs(value) >= 1e12:
            return format(value, ".0f")
        return str(value)
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def parse_datetime_value(value: object) -> pd.Timestamp | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isnan(numeric):
            return None
        if 20000 <= numeric <= 80000:
            try:
                return pd.Timestamp(pd.to_datetime(numeric, unit="D", origin="1899-12-30"))
            except Exception:
                pass
        if 1e9 <= numeric <= 2e10:
            try:
                return pd.Timestamp(pd.to_datetime(numeric, unit="s"))
            except Exception:
                pass
        if 1e12 <= numeric <= 2e13:
            try:
                return pd.Timestamp(pd.to_datetime(numeric, unit="ms"))
            except Exception:
                pass
    try:
        ts = pd.to_datetime(value)
    except Exception:
        return None
    if pd.isna(ts):
        return None
    return pd.Timestamp(ts)


def parse_internal_datetime(value: object) -> pd.Timestamp | None:
    raw = str(value or "").strip()
    if not raw or raw.startswith("0001-01-01"):
        return None
    try:
        ts = pd.to_datetime(raw, utc=True)
    except Exception:
        try:
            ts = pd.to_datetime(raw)
        except Exception:
            return None
    if pd.isna(ts):
        return None
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.tz_convert("Asia/Shanghai").tz_localize(None)
    return pd.Timestamp(ts)


def parse_leading_timestamp(name: str) -> pd.Timestamp | None:
    match = LEADING_TS_RE.match(name)
    if not match:
        return None
    try:
        return pd.to_datetime(match.group(1), format="%Y%m%d%H%M%S")
    except Exception:
        return None


def read_text_relaxed(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def load_json_relaxed(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(read_text_relaxed(path))
    except Exception:
        return None


def json_file_has_payload(path: Path) -> bool:
    if not path.exists():
        return False
    text = read_text_relaxed(path).strip()
    return bool(text and text not in {"[]", "{}"})


def discover_roots() -> tuple[Path | None, Path | None]:
    zhongke_root = None
    yst_root = None
    for child in DATA_ROOT.iterdir():
        if not child.is_dir():
            continue
        if u("\\u4e2d\\u79d1") in child.name and zhongke_root is None:
            zhongke_root = child
        if u("\\u7389\\u751f\\u5802") in child.name and yst_root is None:
            yst_root = child
    return zhongke_root, yst_root


def classify_zhongke_modality(sheet_name: str) -> str | None:
    mapping = {
        SHEET_PULSE: "pulse",
        SHEET_TONGUE: "tongue",
        SHEET_FACE: "face",
        SHEET_ASK: "ask",
    }
    return mapping.get(sheet_name)


def infer_user_folder(file_path: Path, root: Path) -> str:
    try:
        relative = file_path.relative_to(root)
    except Exception:
        return ""
    for part in relative.parts:
        if "." in part and part.lower().endswith((".xls", ".xlsx", ".csv", ".json", ".pdf", ".wav", ".png", ".jpg", ".jpeg")):
            break
        if part and not re.fullmatch(r"\d{4}\.\d{2}(?:\.\d{2})?(?:-\d{4}\.\d{2}(?:\.\d{2})?)?", part):
            return part
    return ""


def first_non_empty(series: pd.Series) -> str:
    for value in series.astype(str):
        if value and value != "nan":
            return value
    return ""


def parse_zhongke_visits(root: Path) -> pd.DataFrame:
    modality_rows: list[dict[str, object]] = []
    excel_paths = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".xls", ".xlsx"})
    for path in excel_paths:
        raw = path.read_bytes()
        head = raw[:8]
        folder_name = infer_user_folder(path, root)
        try:
            if head.startswith(b"PK"):
                workbook = openpyxl.load_workbook(BytesIO(raw), read_only=True, data_only=True)
                try:
                    for worksheet in workbook.worksheets:
                        modality = classify_zhongke_modality(worksheet.title)
                        if modality is None:
                            continue
                        seen_keys: set[tuple[str, str, str, pd.Timestamp]] = set()
                        start_row = 4 if modality in {"pulse", "tongue", "face"} else 2
                        for row in worksheet.iter_rows(min_row=start_row, values_only=True):
                            values = list(row)
                            if len(values) < 8:
                                continue
                            user_name = str(values[2] or "").strip()
                            collected_at = parse_datetime_value(values[6])
                            case_id = coerce_id(values[7])
                            if not user_name or not case_id or collected_at is None:
                                continue
                            key = (user_name, case_id, modality, collected_at)
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)
                            modality_rows.append(
                                {
                                    "source_vendor": "zhongke",
                                    "user_name": user_name,
                                    "folder_name": folder_name,
                                    "source_visit_id": case_id,
                                    "collected_at": collected_at,
                                    "modality": modality,
                                    "source_file_path": str(path),
                                }
                            )
                finally:
                    workbook.close()
            elif head == bytes.fromhex("D0CF11E0A1B11AE1"):
                workbook = xlrd.open_workbook(file_contents=raw, on_demand=True)
                try:
                    for sheet_name in workbook.sheet_names():
                        modality = classify_zhongke_modality(sheet_name)
                        if modality is None:
                            continue
                        sheet = workbook.sheet_by_name(sheet_name)
                        seen_keys: set[tuple[str, str, str, pd.Timestamp]] = set()
                        start_row = 3 if modality in {"pulse", "tongue", "face"} else 1
                        for row_idx in range(start_row, sheet.nrows):
                            values = sheet.row_values(row_idx)
                            if len(values) < 8:
                                continue
                            user_name = str(values[2] or "").strip()
                            collected_at = parse_datetime_value(values[6])
                            case_id = coerce_id(values[7])
                            if not user_name or not case_id or collected_at is None:
                                continue
                            key = (user_name, case_id, modality, collected_at)
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)
                            modality_rows.append(
                                {
                                    "source_vendor": "zhongke",
                                    "user_name": user_name,
                                    "folder_name": folder_name,
                                    "source_visit_id": case_id,
                                    "collected_at": collected_at,
                                    "modality": modality,
                                    "source_file_path": str(path),
                                }
                            )
                finally:
                    workbook.release_resources()
        except Exception:
            continue

    if not modality_rows:
        return pd.DataFrame()

    modality_df = pd.DataFrame(modality_rows).drop_duplicates(subset=["source_vendor", "user_name", "folder_name", "source_visit_id", "collected_at", "modality"])
    visits = modality_df.assign(flag=True).pivot_table(
        index=["source_vendor", "user_name", "folder_name", "source_visit_id", "collected_at"],
        columns="modality",
        values="flag",
        aggfunc="max",
        fill_value=False,
    ).reset_index()
    visits.columns.name = None
    path_df = modality_df.sort_values("source_file_path").pivot_table(
        index=["source_vendor", "user_name", "folder_name", "source_visit_id", "collected_at"],
        columns="modality",
        values="source_file_path",
        aggfunc="first",
    ).reset_index()
    path_df.columns = [f"path_{column}" if column in ZHONGKE_MODALITIES else column for column in path_df.columns]
    visits = visits.merge(path_df, on=["source_vendor", "user_name", "folder_name", "source_visit_id", "collected_at"], how="left")
    for modality in ZHONGKE_MODALITIES:
        if modality not in visits.columns:
            visits[modality] = False
        path_col = f"path_{modality}"
        if path_col not in visits.columns:
            visits[path_col] = ""
        visits[path_col] = visits[path_col].fillna("").astype(str)
    return visits


def parse_yushengtang_visits(root: Path) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for case_dir in sorted(path for path in root.rglob("*") if path.is_dir() and re.fullmatch(r"\d{13,}", path.name)):
        pulse_path = case_dir / "pulse" / "dataPulse.json"
        pulse_payload = load_json_relaxed(pulse_path)
        internal_ts = None
        if isinstance(pulse_payload, dict):
            internal_ts = parse_internal_datetime(pulse_payload.get("StartTime"))
        collected_at = internal_ts or parse_leading_timestamp(case_dir.name)
        if collected_at is None:
            continue
        user_name = case_dir.parent.name
        rows.append(
            {
                "source_vendor": "yushengtang",
                "user_name": user_name,
                "folder_name": user_name,
                "source_visit_id": case_dir.name,
                "collected_at": collected_at,
                "ask": json_file_has_payload(case_dir / "dataAsk.json"),
                "pulse": json_file_has_payload(case_dir / "pulse" / "dataPulse.json"),
                "tongue": json_file_has_payload(case_dir / "tongue" / "dataTongue.json"),
                "voice": json_file_has_payload(case_dir / "voice" / "dataVoice.json"),
                "path_ask": str(case_dir / "dataAsk.json") if (case_dir / "dataAsk.json").exists() else "",
                "path_pulse": str(case_dir / "pulse" / "dataPulse.json") if (case_dir / "pulse" / "dataPulse.json").exists() else "",
                "path_tongue": str(case_dir / "tongue" / "dataTongue.json") if (case_dir / "tongue" / "dataTongue.json").exists() else "",
                "path_voice": str(case_dir / "voice" / "dataVoice.json") if (case_dir / "voice" / "dataVoice.json").exists() else "",
            }
        )
    if not rows:
        return pd.DataFrame()
    visits = pd.DataFrame(rows).drop_duplicates(subset=["source_vendor", "user_name", "folder_name", "source_visit_id"])
    for modality in YUSHENGTANG_MODALITIES:
        if modality not in visits.columns:
            visits[modality] = False
        path_col = f"path_{modality}"
        if path_col not in visits.columns:
            visits[path_col] = ""
        visits[path_col] = visits[path_col].fillna("").astype(str)
    return visits


def determine_required_modalities(visits: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    source_to_modalities = {"zhongke": ZHONGKE_MODALITIES, "yushengtang": YUSHENGTANG_MODALITIES}
    for source_vendor, modality_columns in source_to_modalities.items():
        subset = visits.loc[visits["source_vendor"] == source_vendor].copy()
        if subset.empty:
            continue
        for modality in modality_columns:
            presence_rate = float(subset[modality].fillna(False).astype(bool).mean())
            rows.append(
                {
                    "source_vendor": source_vendor,
                    "modality": modality,
                    "presence_rate": presence_rate,
                    "is_required": presence_rate >= REQUIRED_MODALITY_THRESHOLD,
                }
            )
    return pd.DataFrame(rows)


def apply_visit_quality_flags(visits: pd.DataFrame, modality_rules: pd.DataFrame) -> pd.DataFrame:
    visits = visits.copy()
    required_lookup: dict[str, list[str]] = {}
    for source_vendor, subset in modality_rules.groupby("source_vendor"):
        required_lookup[source_vendor] = subset.loc[subset["is_required"], "modality"].tolist()

    required_modalities_col: list[str] = []
    missing_required_col: list[str] = []
    is_complete_col: list[bool] = []
    for _, row in visits.iterrows():
        required = required_lookup.get(row["source_vendor"], [])
        missing = [modality for modality in required if not bool(row.get(modality, False))]
        required_modalities_col.append(",".join(required))
        missing_required_col.append(",".join(missing))
        is_complete_col.append(bool(required) and not missing)

    visits["required_modalities"] = required_modalities_col
    visits["missing_required_modalities"] = missing_required_col
    visits["is_complete_visit"] = is_complete_col
    visits["date"] = pd.to_datetime(visits["collected_at"]).dt.normalize()
    return visits


def try_parse_numeric_sequence(value: object) -> list[float]:
    if value is None:
        return []
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            values = parsed if isinstance(parsed, list) else re.split(r"[\s,;|]+", text)
        except Exception:
            values = re.split(r"[\s,;|]+", text)
    else:
        return []
    numeric: list[float] = []
    for item in values:
        try:
            numeric.append(float(item))
        except Exception:
            continue
    return numeric


def normalize_signal(values: list[float], sample_size: int = 128) -> list[float]:
    if len(values) < 32:
        return []
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum
    if span <= 0:
        return []
    normalized = [(value - minimum) / span for value in values]
    step = max(1, len(normalized) // sample_size)
    sampled = normalized[::step][:sample_size]
    return [round(value, 6) for value in sampled]


def stable_numeric_hash(values: list[float]) -> str:
    payload = ",".join(f"{value:.6f}" for value in values)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def mean_manhattan_distance(left: list[float], right: list[float]) -> float | None:
    if not left or not right:
        return None
    size = min(len(left), len(right))
    if size == 0:
        return None
    return sum(abs(left[idx] - right[idx]) for idx in range(size)) / size


def extract_yushengtang_pulse_feature(pulse_path: Path) -> dict[str, object] | None:
    payload = load_json_relaxed(pulse_path)
    if not isinstance(payload, dict):
        return None
    combined: list[float] = []
    for key in ["SinglePluse", "CunShang", "Cun", "GuanMai", "Chi", "ChiXia"]:
        combined.extend(try_parse_numeric_sequence(payload.get(key)))
    if len(combined) < 32:
        for value in payload.values():
            sequence = try_parse_numeric_sequence(value)
            if len(sequence) >= 32:
                combined.extend(sequence)
    sampled = normalize_signal(combined)
    if not sampled:
        return None
    return {"numeric_signal_hash": stable_numeric_hash(sampled), "numeric_signal_vector": sampled}


def read_csv_relaxed(path: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except Exception:
            continue
    return pd.DataFrame()


def extract_zhongke_pulse_feature_map(visit_ids: set[str], root: Path) -> dict[str, dict[str, object]]:
    feature_map: dict[str, dict[str, object]] = {}
    for path in sorted(root.rglob("*脉诊数据*.csv")):
        frame = read_csv_relaxed(path)
        if frame.empty:
            continue
        visit_id_col = next((column for column in frame.columns if str(column).strip() in {"CaseId", "病例号", "诊次号", "TreatNumber", "CaId"}), None)
        if visit_id_col is None:
            continue
        numeric_cols = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
        if not numeric_cols:
            continue
        signal_cols = [column for column in numeric_cols if str(column).strip() not in {"序号"}]
        for visit_id, subset in frame.groupby(visit_id_col):
            visit_id_text = coerce_id(visit_id)
            if visit_id_text not in visit_ids or visit_id_text in feature_map:
                continue
            vector: list[float] = []
            for column in signal_cols:
                vector.extend([float(value) for value in subset[column].dropna().tolist()])
            sampled = normalize_signal(vector)
            if not sampled:
                continue
            feature_map[visit_id_text] = {"numeric_signal_hash": stable_numeric_hash(sampled), "numeric_signal_vector": sampled}
    return feature_map


def detect_duplicate_numeric_visits(visits: pd.DataFrame, zhongke_root: Path | None) -> pd.DataFrame:
    visits = visits.copy()
    visits["duplicate_numeric_flag"] = False
    visits["duplicate_numeric_type"] = ""
    visits["duplicate_numeric_partner"] = ""
    visits["duplicate_numeric_distance"] = pd.NA
    feature_records: list[dict[str, object]] = []
    for _, row in visits.loc[(visits["source_vendor"] == "yushengtang") & visits["path_pulse"].astype(str).ne("")].iterrows():
        feature = extract_yushengtang_pulse_feature(Path(str(row["path_pulse"])))
        if feature is None:
            continue
        feature_records.append(
            {"source_vendor": row["source_vendor"], "user_name": row["user_name"], "source_visit_id": row["source_visit_id"], **feature}
        )
    if zhongke_root is not None:
        zhongke_ids = set(visits.loc[visits["source_vendor"] == "zhongke", "source_visit_id"].astype(str))
        feature_map = extract_zhongke_pulse_feature_map(zhongke_ids, zhongke_root)
        for _, row in visits.loc[visits["source_vendor"] == "zhongke"].iterrows():
            feature = feature_map.get(str(row["source_visit_id"]))
            if feature is None:
                continue
            feature_records.append(
                {"source_vendor": row["source_vendor"], "user_name": row["user_name"], "source_visit_id": row["source_visit_id"], **feature}
            )
    if not feature_records:
        return visits
    feature_df = pd.DataFrame(feature_records).drop_duplicates(subset=["source_vendor", "user_name", "source_visit_id"])
    updates: dict[tuple[str, str, str], dict[str, object]] = {}
    for (_, user_name, numeric_hash), subset in feature_df.groupby(["source_vendor", "user_name", "numeric_signal_hash"], sort=False):
        if not numeric_hash or len(subset) < 2:
            continue
        visit_ids = sorted(subset["source_visit_id"].astype(str).tolist())
        for visit_id in visit_ids:
            updates[(str(subset.iloc[0]["source_vendor"]), str(user_name), str(visit_id))] = {
                "duplicate_numeric_flag": True,
                "duplicate_numeric_type": "exact_hash",
                "duplicate_numeric_partner": ",".join(partner for partner in visit_ids if partner != visit_id),
                "duplicate_numeric_distance": 0.0,
            }
    near_threshold = 0.015
    for (source_vendor, user_name), subset in feature_df.groupby(["source_vendor", "user_name"], sort=False):
        rows = subset.to_dict("records")
        for left_idx in range(len(rows)):
            for right_idx in range(left_idx + 1, len(rows)):
                left = rows[left_idx]
                right = rows[right_idx]
                if left["numeric_signal_hash"] == right["numeric_signal_hash"]:
                    continue
                distance = mean_manhattan_distance(list(left["numeric_signal_vector"]), list(right["numeric_signal_vector"]))
                if distance is None or distance > near_threshold:
                    continue
                for current, partner in ((left, right), (right, left)):
                    key = (str(source_vendor), str(user_name), str(current["source_visit_id"]))
                    existing = updates.get(key)
                    if existing and existing.get("duplicate_numeric_type") == "exact_hash":
                        continue
                    updates[key] = {
                        "duplicate_numeric_flag": True,
                        "duplicate_numeric_type": "near_manhattan",
                        "duplicate_numeric_partner": str(partner["source_visit_id"]),
                        "duplicate_numeric_distance": round(distance, 6),
                    }
    for key, payload in updates.items():
        mask = (
            visits["source_vendor"].astype(str).eq(key[0])
            & visits["user_name"].astype(str).eq(key[1])
            & visits["source_visit_id"].astype(str).eq(key[2])
        )
        for column, value in payload.items():
            visits.loc[mask, column] = value
    visits["duplicate_numeric_flag"] = visits["duplicate_numeric_flag"].fillna(False).astype(bool)
    return visits


def cluster_sessions(visits: pd.DataFrame) -> pd.DataFrame:
    session_rows: list[dict[str, object]] = []
    grouped = visits.sort_values(["canonical_name", "collected_at", "source_vendor"]).groupby(["canonical_name", "date"], sort=True)
    for (user_name, date_value), day_visits in grouped:
        current_cluster: list[dict[str, object]] = []
        last_ts: pd.Timestamp | None = None

        def flush_cluster(cluster: list[dict[str, object]]) -> None:
            if not cluster:
                return
            cluster_df = pd.DataFrame(cluster)
            start_ts = cluster_df["collected_at"].min()
            end_ts = cluster_df["collected_at"].max()
            visit_count_by_source = cluster_df.groupby("source_vendor")["source_visit_id"].nunique().to_dict()
            complete_by_source = cluster_df.groupby("source_vendor")["is_complete_visit"].max().to_dict()
            raw_visit_count = int(cluster_df["source_visit_id"].nunique())
            complete_visit_count = int(cluster_df.loc[cluster_df["is_complete_visit"], "source_visit_id"].nunique())
            incomplete_visit_count = raw_visit_count - complete_visit_count
            all_complete_triplicate = raw_visit_count >= 3 and incomplete_visit_count == 0
            dual_device_triplicate = sum(count >= 3 for count in visit_count_by_source.values()) >= 2
            duplicate_numeric_flag = bool(cluster_df.get("duplicate_numeric_flag", pd.Series(dtype=bool)).fillna(False).any())
            duplicate_types = sorted({str(value) for value in cluster_df.get("duplicate_numeric_type", pd.Series(dtype=object)).fillna("") if str(value).strip()})
            duplicate_partners = sorted({str(value) for value in cluster_df.get("duplicate_numeric_partner", pd.Series(dtype=object)).fillna("") if str(value).strip()})
            cheat_triplicate_10m = bool(
                (end_ts - start_ts) <= pd.Timedelta(minutes=SESSION_MERGE_MINUTES)
                and (all_complete_triplicate or dual_device_triplicate)
            )
            cluster_id = f"{user_name}|{date_value.date()}|{start_ts.strftime('%H%M%S')}"
            session_rows.append(
                {
                    "user_name": user_name,
                    "date": date_value,
                    "cluster_id": cluster_id,
                    "cluster_start": start_ts,
                    "cluster_end": end_ts,
                    "visit_ids": ",".join(cluster_df["source_visit_id"].astype(str).tolist()),
                    "source_vendors": ",".join(sorted(cluster_df["source_vendor"].unique())),
                    "has_complete_visit": bool(cluster_df["is_complete_visit"].any()),
                    "all_visits_complete": bool(cluster_df["is_complete_visit"].all()),
                    "cheat_triplicate_10m": cheat_triplicate_10m,
                    "incomplete_visit_count": incomplete_visit_count,
                    "zhongke_complete": bool(complete_by_source.get("zhongke", False)),
                    "yushengtang_complete": bool(complete_by_source.get("yushengtang", False)),
                    "duplicate_numeric_flag": duplicate_numeric_flag,
                    "duplicate_numeric_type": ",".join(duplicate_types),
                    "duplicate_numeric_partner": ",".join(duplicate_partners),
                    "name_mismatch_flag": bool(cluster_df.get("name_mismatch_flag", pd.Series(dtype=bool)).fillna(False).any()),
                }
            )

        for row in day_visits.to_dict("records"):
            if last_ts is None or row["collected_at"] - last_ts <= pd.Timedelta(minutes=SESSION_MERGE_MINUTES):
                current_cluster.append(row)
            else:
                flush_cluster(current_cluster)
                current_cluster = [row]
            last_ts = row["collected_at"]
        flush_cluster(current_cluster)
    return pd.DataFrame(session_rows)


def assign_day_slots(sessions: pd.DataFrame) -> pd.DataFrame:
    slot_rows: list[dict[str, object]] = []
    gap_threshold = pd.Timedelta(minutes=MIN_SLOT_GAP_MINUTES)
    for (user_name, date_value), day_sessions in sessions.groupby(["user_name", "date"], sort=True):
        day_sessions = day_sessions.sort_values("cluster_start").reset_index(drop=True)
        accepted_slot_count = 0
        last_accepted_ts: pd.Timestamp | None = None
        for _, session in day_sessions.iterrows():
            slot_label = ""
            status = "missing"
            reason = ""
            if bool(session["cheat_triplicate_10m"]):
                status = "suspicious"
                reason = "triplicate_within_10m"
            elif bool(session.get("duplicate_numeric_flag", False)):
                status = "suspicious"
                reason = "duplicate_numeric"
            elif last_accepted_ts is not None and session["cluster_start"] - last_accepted_ts < gap_threshold:
                status = "invalid"
                reason = "gap_lt_30m"
            elif accepted_slot_count >= len(SLOT_LABELS):
                status = "invalid"
                reason = "overflow_gt_3"
            else:
                slot_label = SLOT_LABELS[accepted_slot_count]
                accepted_slot_count += 1
                last_accepted_ts = session["cluster_start"]
                status = "complete" if bool(session["has_complete_visit"]) else "incomplete"
                if status == "incomplete":
                    reason = "no_complete_visit_in_cluster"
            slot_rows.append(
                {
                    "user_name": user_name,
                    "date": date_value,
                    "cluster_id": session["cluster_id"],
                    "cluster_start": session["cluster_start"],
                    "slot_label": slot_label,
                    "slot_status": status,
                    "reason": reason,
                    "zhongke_complete": bool(session["zhongke_complete"]),
                    "yushengtang_complete": bool(session["yushengtang_complete"]),
                    "source_vendors": session["source_vendors"],
                    "duplicate_numeric_flag": bool(session.get("duplicate_numeric_flag", False)),
                    "name_mismatch_flag": bool(session.get("name_mismatch_flag", False)),
                }
            )
    return pd.DataFrame(slot_rows)


def source_has(cluster_visits: pd.DataFrame, source_vendor: str, modality: str) -> bool:
    subset = cluster_visits.loc[cluster_visits["source_vendor"] == source_vendor]
    return bool(not subset.empty and subset[modality].fillna(False).astype(bool).any())


def collect_missing_modalities(cluster_visits: pd.DataFrame) -> list[str]:
    missing_items: list[str] = []
    for _, visit in cluster_visits.iterrows():
        vendor_label = u("\\u4e2d\\u79d1") if visit["source_vendor"] == "zhongke" else u("\\u7389\\u751f\\u5802")
        for modality in str(visit.get("missing_required_modalities", "")).split(","):
            modality = modality.strip()
            if modality:
                missing_items.append(f"{vendor_label}{MODALITY_LABELS.get(modality, modality)}")
    return sorted(set(missing_items))


def build_detail_export(day_slots: pd.DataFrame, sessions: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    if day_slots.empty:
        return pd.DataFrame()
    sessions_lookup = sessions.set_index("cluster_id")
    rows: list[dict[str, object]] = []
    for _, slot_row in day_slots.iterrows():
        session_row = sessions_lookup.loc[slot_row["cluster_id"]]
        cluster_visits = visits.loc[
            (visits["canonical_name"] == slot_row["user_name"])
            & (visits["date"] == slot_row["date"])
            & (visits["collected_at"] >= session_row["cluster_start"])
            & (visits["collected_at"] <= session_row["cluster_end"])
        ].copy()
        missing_detail = collect_missing_modalities(cluster_visits)
        folder_names = sorted({str(value).strip() for value in cluster_visits.get("folder_name", pd.Series(dtype=object)) if str(value).strip()})
        table_names = sorted({str(value).strip() for value in cluster_visits.get("user_name", pd.Series(dtype=object)) if str(value).strip()})
        remark_parts: list[str] = []
        if bool(slot_row.get("name_mismatch_flag", False)):
            remark_parts.append(
                u("\\u59d3\\u540d\\u4e0d\\u4e00\\u81f4")
                + f"：{COL_FOLDER_NAMES}={','.join(folder_names)}；{COL_TABLE_NAMES}={','.join(table_names)}"
            )
        if slot_row["slot_status"] == "suspicious":
            if slot_row["reason"] == "triplicate_within_10m":
                remark_parts.append(u("\\u7591\\u4f3c\\u4f5c\\u5f0a\\uff1a10\\u5206\\u949f\\u5185\\u8fde\\u7eed\\u591a\\u6b21\\u6253\\u5361"))
            elif slot_row["reason"] == "duplicate_numeric":
                duplicate_label = u("\\u6570\\u503c\\u6307\\u7eb9\\u4e00\\u81f4") if "exact_hash" in str(session_row.get("duplicate_numeric_type", "")) else u("\\u6570\\u503c\\u9ad8\\u5ea6\\u76f8\\u4f3c")
                duplicate_note = u("\\u7591\\u4f3c\\u91cd\\u590d") + f"：{duplicate_label}"
                if str(session_row.get("duplicate_numeric_partner", "")).strip():
                    duplicate_note = duplicate_note + f"（{str(session_row.get('duplicate_numeric_partner', '')).strip()}）"
                remark_parts.append(duplicate_note)
        elif slot_row["slot_status"] == "invalid":
            if slot_row["reason"] == "gap_lt_30m":
                remark_parts.append(u("\\u65e0\\u6548\\uff1a\\u4e0e\\u4e0a\\u4e00\\u6709\\u6548\\u65f6\\u6bb5\\u95f4\\u9694\\u4e0d\\u8db3 30 \\u5206\\u949f"))
            elif slot_row["reason"] == "overflow_gt_3":
                remark_parts.append(u("\\u65e0\\u6548\\uff1a\\u8d85\\u51fa\\u65e9\\u4e2d\\u665a\\u4e09\\u6b21\\u4e0a\\u9650"))
        elif slot_row["slot_status"] == "incomplete":
            remark_parts.append(u("\\u4e0d\\u5b8c\\u6574"))
        if missing_detail:
            remark_parts.append(u("\\u7f3a\\u5c11\\u6a21\\u6001") + f"：{','.join(missing_detail)}")
        remark = u("\\uff1b").join(remark_parts)

        rows.append(
            {
                COL_NAME: slot_row["user_name"],
                COL_DATE: pd.Timestamp(slot_row["date"]).normalize(),
                COL_TIME: pd.Timestamp(slot_row["cluster_start"]).strftime("%H:%M:%S"),
                COL_SLOT: slot_row["slot_label"] or "",
                COL_STATUS: slot_row["slot_status"],
                COL_REMARK: remark,
                COL_FOLDER_NAMES: ",".join(folder_names),
                COL_TABLE_NAMES: ",".join(table_names),
                COL_DUPLICATE: "1" if bool(slot_row.get("duplicate_numeric_flag", False)) else "",
                COL_NAME_MISMATCH: "1" if bool(slot_row.get("name_mismatch_flag", False)) else "",
                COL_ZK_ASK: "1" if source_has(cluster_visits, "zhongke", "ask") else "",
                COL_ZK_PULSE: "1" if source_has(cluster_visits, "zhongke", "pulse") else "",
                COL_ZK_TONGUE: "1" if source_has(cluster_visits, "zhongke", "tongue") else "",
                COL_ZK_FACE: "1" if source_has(cluster_visits, "zhongke", "face") else "",
                COL_YST_ASK: "1" if source_has(cluster_visits, "yushengtang", "ask") else "",
                COL_YST_PULSE: "1" if source_has(cluster_visits, "yushengtang", "pulse") else "",
                COL_YST_TONGUE: "1" if source_has(cluster_visits, "yushengtang", "tongue") else "",
                COL_YST_VOICE: "1" if source_has(cluster_visits, "yushengtang", "voice") else "",
                COL_ZK_ASK_PATH: first_non_empty(cluster_visits.loc[(cluster_visits["source_vendor"] == "zhongke") & cluster_visits["ask"], "path_ask"]),
                COL_ZK_PULSE_PATH: first_non_empty(cluster_visits.loc[(cluster_visits["source_vendor"] == "zhongke") & cluster_visits["pulse"], "path_pulse"]),
                COL_ZK_TONGUE_PATH: first_non_empty(cluster_visits.loc[(cluster_visits["source_vendor"] == "zhongke") & cluster_visits["tongue"], "path_tongue"]),
                COL_ZK_FACE_PATH: first_non_empty(cluster_visits.loc[(cluster_visits["source_vendor"] == "zhongke") & cluster_visits["face"], "path_face"]),
                COL_YST_ASK_PATH: first_non_empty(cluster_visits.loc[(cluster_visits["source_vendor"] == "yushengtang") & cluster_visits["ask"], "path_ask"]),
                COL_YST_PULSE_PATH: first_non_empty(cluster_visits.loc[(cluster_visits["source_vendor"] == "yushengtang") & cluster_visits["pulse"], "path_pulse"]),
                COL_YST_TONGUE_PATH: first_non_empty(cluster_visits.loc[(cluster_visits["source_vendor"] == "yushengtang") & cluster_visits["tongue"], "path_tongue"]),
                COL_YST_VOICE_PATH: first_non_empty(cluster_visits.loc[(cluster_visits["source_vendor"] == "yushengtang") & cluster_visits["voice"], "path_voice"]),
                "device_count": int(cluster_visits["source_vendor"].nunique()),
                "detail_fill_red": bool(slot_row.get("duplicate_numeric_flag", False) or slot_row.get("name_mismatch_flag", False)),
                "cluster_id": slot_row["cluster_id"],
            }
        )
    return pd.DataFrame(rows).sort_values([COL_NAME, COL_DATE, COL_TIME, COL_SLOT]).reset_index(drop=True)


def build_date_index(visits: pd.DataFrame) -> pd.DatetimeIndex:
    end = pd.Timestamp(visits["date"].max()).normalize()
    return pd.date_range(START_DATE, end, freq="D")


def build_heatmap_matrix(slot_df: pd.DataFrame, user_names: list[str], date_index: pd.DatetimeIndex) -> pd.DataFrame:
    index_labels = [f"{name}-{slot}" for name in user_names for slot in SLOT_LABELS]
    matrix = pd.DataFrame(0, index=index_labels, columns=[day.strftime("%Y-%m-%d") for day in date_index], dtype=int)
    status_to_value = {"missing": 0, "incomplete": 1, "complete": 2, "suspicious": 3, "invalid": 1}
    for _, row in slot_df.iterrows():
        if row["slot_label"] not in SLOT_LABELS:
            continue
        label = f"{row['user_name']}-{row['slot_label']}"
        date_label = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
        matrix.loc[label, date_label] = max(matrix.loc[label, date_label], status_to_value[row["slot_status"]])
    return matrix


def write_matrix_workbook(user_names: list[str], date_index: pd.DatetimeIndex, detail_df: pd.DataFrame) -> None:
    with pd.ExcelWriter(WORKBOOK_OUTPUT, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        workbook: xlsxwriter.Workbook = writer.book
        matrix_sheet = workbook.add_worksheet(SHEET_MATRIX)
        detail_sheet = workbook.add_worksheet(SHEET_DETAIL)
        writer.sheets[SHEET_MATRIX] = matrix_sheet
        writer.sheets[SHEET_DETAIL] = detail_sheet

        header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1, "align": "center"})
        row_label_fmt = workbook.add_format({"bold": True, "border": 1, "align": "left"})
        blank_fmt = workbook.add_format({"border": 1, "align": "center"})
        green_link_fmt = workbook.add_format({"border": 1, "align": "center", "bg_color": "#C6EFCE", "font_color": "#0563C1", "underline": 1})
        yellow_link_fmt = workbook.add_format({"border": 1, "align": "center", "bg_color": "#FFEB9C", "font_color": "#0563C1", "underline": 1})
        orange_link_fmt = workbook.add_format({"border": 1, "align": "center", "bg_color": "#F4B183", "font_color": "#0563C1", "underline": 1})
        red_link_fmt = workbook.add_format({"border": 1, "align": "center", "bg_color": "#FFC7CE", "font_color": "#0563C1", "underline": 1})
        detail_text_fmt = workbook.add_format({"border": 1, "valign": "top"})
        detail_red_fmt = workbook.add_format({"border": 1, "valign": "top", "bg_color": "#FFC7CE"})
        detail_link_fmt = workbook.add_format({"border": 1, "valign": "top", "font_color": "#0563C1", "underline": 1})
        detail_red_link_fmt = workbook.add_format({"border": 1, "valign": "top", "bg_color": "#FFC7CE", "font_color": "#0563C1", "underline": 1})

        matrix_dates = [day.strftime("%Y-%m-%d") for day in date_index]
        matrix_sheet.write(0, 0, u("\\u7528\\u6237\\u65f6\\u6bb5"), header_fmt)
        for col_idx, date_label in enumerate(matrix_dates, start=1):
            matrix_sheet.write(0, col_idx, date_label, header_fmt)

        detail_columns = [column for column in detail_df.columns if column not in {"cluster_id", "device_count", "detail_fill_red"}]
        for col_idx, column in enumerate(detail_columns):
            detail_sheet.write(0, col_idx, column, header_fmt)
        for row_idx, row in detail_df.iterrows():
            excel_row = row_idx + 1
            base_fmt = detail_red_fmt if bool(row.get("detail_fill_red", False)) else detail_text_fmt
            link_fmt = detail_red_link_fmt if bool(row.get("detail_fill_red", False)) else detail_link_fmt
            for col_idx, column in enumerate(detail_columns):
                value = row[column]
                if column in {
                    COL_ZK_ASK_PATH,
                    COL_ZK_PULSE_PATH,
                    COL_ZK_TONGUE_PATH,
                    COL_ZK_FACE_PATH,
                    COL_YST_ASK_PATH,
                    COL_YST_PULSE_PATH,
                    COL_YST_TONGUE_PATH,
                    COL_YST_VOICE_PATH,
                } and str(value).strip():
                    if Path(str(value)).exists():
                        detail_sheet.write_url(excel_row, col_idx, f"external:{Path(str(value))}", link_fmt, string=str(value))
                    else:
                        detail_sheet.write(excel_row, col_idx, str(value), base_fmt)
                else:
                    detail_sheet.write(excel_row, col_idx, value, base_fmt)

        status_priority = {"suspicious": 4, "invalid": 3, "incomplete": 2, "complete": 1}
        key_to_status: dict[tuple[str, str, str], str] = {}
        key_to_detail_row: dict[tuple[str, str, str], int] = {}
        key_to_device_count: dict[tuple[str, str, str], int] = {}
        for row_idx, row in detail_df.iterrows():
            key = (str(row[COL_NAME]), str(row[COL_SLOT]), pd.Timestamp(row[COL_DATE]).strftime("%Y-%m-%d"))
            status = str(row[COL_STATUS])
            device_count = int(row.get("device_count", 0) or 0)
            if key not in key_to_detail_row:
                key_to_detail_row[key] = row_idx + 2
            if key not in key_to_status or status_priority.get(status, 0) > status_priority.get(key_to_status[key], 0):
                key_to_status[key] = status
            key_to_device_count[key] = min(2, max(key_to_device_count.get(key, 0), device_count))

        row_labels = [f"{name}-{slot}" for name in user_names for slot in SLOT_LABELS]
        for row_idx, row_label in enumerate(row_labels, start=1):
            matrix_sheet.write(row_idx, 0, row_label, row_label_fmt)
            user_name, slot_label = row_label.rsplit("-", 1)
            for col_idx, date_label in enumerate(matrix_dates, start=1):
                key = (user_name, slot_label, date_label)
                if key not in key_to_status:
                    matrix_sheet.write_blank(row_idx, col_idx, None, blank_fmt)
                    continue
                status = key_to_status[key]
                detail_row = key_to_detail_row[key]
                cell_format = {
                    "complete": green_link_fmt,
                    "incomplete": yellow_link_fmt,
                    "invalid": orange_link_fmt,
                    "suspicious": red_link_fmt,
                }.get(status, blank_fmt)
                matrix_sheet.write_url(
                    row_idx,
                    col_idx,
                    f"internal:'{SHEET_DETAIL}'!A{detail_row}",
                    cell_format,
                    string=str(key_to_device_count.get(key, 1)),
                )

        matrix_sheet.freeze_panes(1, 1)
        detail_sheet.freeze_panes(1, 0)
        matrix_sheet.set_column(0, 0, 18)
        matrix_sheet.set_column(1, len(matrix_dates), 4.2)
        detail_sheet.set_column(0, 0, 12)
        detail_sheet.set_column(1, 1, 12)
        detail_sheet.set_column(2, 2, 10)
        detail_sheet.set_column(3, 9, 16)
        detail_sheet.set_column(10, 17, 12)
        detail_sheet.set_column(18, len(detail_columns) - 1, 60)


def plot_heatmap(matrix: pd.DataFrame) -> None:
    cmap = ListedColormap(["#f5f5f5", "#f6c85f", "#2ca02c", "#d62728"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], cmap.N)
    width = min(42, max(24, len(matrix.columns) * 0.18))
    height = min(30, max(12, len(matrix.index) * 0.18))
    fig, ax = plt.subplots(figsize=(width, height))
    im = ax.imshow(matrix.values, aspect="auto", cmap=cmap, norm=norm)
    tick_step = max(1, math.ceil(len(matrix.columns) / 45))
    xtick_positions = list(range(0, len(matrix.columns), tick_step))
    ax.set_xticks(xtick_positions)
    ax.set_xticklabels([matrix.columns[idx] for idx in xtick_positions], rotation=90, fontsize=7)
    slots_per_user = len(SLOT_LABELS)
    user_names = [str(label).rsplit("-", 1)[0] for label in matrix.index[::slots_per_user]]
    ytick_positions = [idx * slots_per_user + (slots_per_user - 1) / 2 for idx in range(len(user_names))]
    ax.set_yticks(ytick_positions)
    ax.set_yticklabels(user_names, fontsize=10)
    ax.tick_params(axis="y", length=0, pad=6)
    for boundary in range(slots_per_user, len(matrix.index), slots_per_user):
        ax.axhline(boundary - 0.5, color="#d9d9d9", linewidth=0.6)
    ax.set_xlabel(u("\\u65e5\\u671f"))
    ax.set_ylabel(u("\\u7528\\u6237"))
    ax.set_title(u("\\u56db\\u8bca\\u4eea\\u6570\\u636e\\u6574\\u7406\\u5168\\u65f6\\u95f4\\u6253\\u5361\\u77e9\\u9635"))
    cbar = fig.colorbar(im, ax=ax, ticks=[0, 1, 2, 3], fraction=0.015, pad=0.01)
    cbar.ax.set_yticklabels(
        [
            u("\\u7f3a\\u5931"),
            u("\\u4e0d\\u5b8c\\u6574"),
            u("\\u6709\\u6548"),
            u("\\u5f02\\u5e38"),
        ]
    )
    fig.tight_layout()
    fig.subplots_adjust(left=0.16, bottom=0.2)
    fig.savefig(PLOT_OUTPUT, dpi=160)
    plt.close(fig)


def main() -> None:
    ensure_output_dirs()
    zhongke_root, yst_root = discover_roots()
    if not REFERENCE_DIR.exists():
        raise RuntimeError(f"Cohort reference directory not found: {REFERENCE_DIR}")
    cohort_reference = parse_zhongke_visits(REFERENCE_DIR)
    folder_names = sorted(path.name for path in REFERENCE_DIR.iterdir() if path.is_dir())
    folder_to_canonical: dict[str, str] = {}
    for folder_name in folder_names:
        subset = cohort_reference.loc[cohort_reference["folder_name"] == folder_name] if not cohort_reference.empty else pd.DataFrame()
        canonical_name = folder_name
        if not subset.empty:
            counts = Counter(str(value) for value in subset["user_name"] if str(value).strip())
            if counts:
                canonical_name = counts.most_common(1)[0][0]
        folder_to_canonical[folder_name] = canonical_name
    cohort_names = sorted(folder_to_canonical.values())
    visits_frames: list[pd.DataFrame] = []
    if zhongke_root is not None:
        zhongke_visits = parse_zhongke_visits(zhongke_root)
        if not zhongke_visits.empty:
            visits_frames.append(zhongke_visits)
    if yst_root is not None:
        yst_visits = parse_yushengtang_visits(yst_root)
        if not yst_visits.empty:
            visits_frames.append(yst_visits)
    if not visits_frames:
        raise RuntimeError("No visits found in organized data root.")

    visits = pd.concat(visits_frames, ignore_index=True, sort=False)
    for column in ["ask", "pulse", "tongue", "face", "voice"]:
        if column not in visits.columns:
            visits[column] = False
        visits[column] = visits[column].fillna(False).astype(bool)
        path_col = f"path_{column}"
        if path_col not in visits.columns:
            visits[path_col] = ""
        visits[path_col] = visits[path_col].fillna("").astype(str)
    visits["canonical_name"] = ""
    visits["name_mismatch_flag"] = False
    for idx, row in visits.iterrows():
        folder_name = str(row.get("folder_name", "")).strip()
        table_name = str(row.get("user_name", "")).strip()
        canonical_name = ""
        if folder_name in folder_to_canonical:
            canonical_name = folder_to_canonical[folder_name]
        elif table_name in cohort_names:
            canonical_name = table_name
        elif row["source_vendor"] == "yushengtang" and folder_name in cohort_names:
            canonical_name = folder_name
        visits.at[idx, "canonical_name"] = canonical_name
        visits.at[idx, "name_mismatch_flag"] = bool(folder_name and table_name and normalize_name(folder_name) != normalize_name(table_name))
    visits["collected_at"] = pd.to_datetime(visits["collected_at"])
    visits = visits.loc[visits["canonical_name"].astype(str).isin(cohort_names)].copy()
    visits = visits.loc[visits["collected_at"] >= START_DATE].copy()
    if visits.empty:
        raise RuntimeError("Filtered cohort visits are empty.")
    visits["user_name"] = visits["canonical_name"]
    visits = visits.sort_values(["user_name", "collected_at", "source_vendor"]).reset_index(drop=True)

    modality_rules = determine_required_modalities(visits)
    visits = apply_visit_quality_flags(visits, modality_rules)
    visits = detect_duplicate_numeric_visits(visits, zhongke_root)
    sessions = cluster_sessions(visits)
    day_slots = assign_day_slots(sessions)
    detail_df = build_detail_export(day_slots, sessions, visits)
    user_names = cohort_names
    date_index = build_date_index(visits)
    matrix = build_heatmap_matrix(day_slots, user_names, date_index)
    write_matrix_workbook(user_names, date_index, detail_df)
    plot_heatmap(matrix)

    print(f"Workbook: {WORKBOOK_OUTPUT}")
    print(f"Heatmap: {PLOT_OUTPUT}")
    print(f"Users: {len(user_names)}")
    print(f"Dates: {date_index.min().date()} -> {date_index.max().date()} ({len(date_index)} days)")


if __name__ == "__main__":
    main()
