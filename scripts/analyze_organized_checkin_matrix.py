from __future__ import annotations

import math
import re
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
WORKBOOK_OUTPUT = OUTPUT_DIR / "organized_checkin_matrix.xlsx"
PLOT_OUTPUT = OUTPUT_DIR / "organized_checkin_heatmap.png"

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
COL_ZK_ASK = u("\\u4e2d\\u79d1_\\u95ee\\u8bca")
COL_ZK_PULSE = u("\\u4e2d\\u79d1_\\u8109\\u8bca\\u6ce2\\u5f62")
COL_ZK_TONGUE = u("\\u4e2d\\u79d1_\\u820c\\u8bca\\u56fe\\u7247")
COL_ZK_FACE = u("\\u4e2d\\u79d1_\\u9762\\u8bca\\u56fe\\u7247")
COL_YST_ASK = u("\\u7389\\u751f\\u5802_\\u95ee\\u8bca")
COL_YST_PULSE = u("\\u7389\\u751f\\u5802_\\u8109\\u8bca\\u6ce2\\u5f62")
COL_YST_TONGUE = u("\\u7389\\u751f\\u5802_\\u820c\\u8bca\\u56fe\\u7247")
COL_YST_VOICE = u("\\u7389\\u751f\\u5802_wav")
SHEET_MATRIX = u("\\u6253\\u5361\\u77e9\\u9635")
SHEET_DETAIL = u("\\u8be6\\u7ec6\\u8bb0\\u5f55")

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def ensure_output_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def load_json_relaxed(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return pd.io.json.loads(read_text_relaxed(path))
    except Exception:
        try:
            import json

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


def parse_zhongke_visits(root: Path) -> pd.DataFrame:
    modality_rows: list[dict[str, object]] = []
    excel_paths = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".xls", ".xlsx"})
    for path in excel_paths:
        raw = path.read_bytes()
        head = raw[:8]
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
                                    "source_visit_id": case_id,
                                    "collected_at": collected_at,
                                    "modality": modality,
                                }
                            )
                finally:
                    workbook.close()
            elif head == bytes.fromhex("D0CF11E0A1B11AE1"):
                workbook = xlrd.open_workbook(file_contents=raw, on_demand=True)
                try:
                    if SHEET_ASK in workbook.sheet_names():
                        sheet = workbook.sheet_by_name(SHEET_ASK)
                        seen_keys: set[tuple[str, str, str, pd.Timestamp]] = set()
                        for row_idx in range(1, sheet.nrows):
                            values = sheet.row_values(row_idx)
                            if len(values) < 8:
                                continue
                            user_name = str(values[2] or "").strip()
                            collected_at = parse_datetime_value(values[6])
                            case_id = coerce_id(values[7])
                            if not user_name or not case_id or collected_at is None:
                                continue
                            key = (user_name, case_id, "ask", collected_at)
                            if key in seen_keys:
                                continue
                            seen_keys.add(key)
                            modality_rows.append(
                                {
                                    "source_vendor": "zhongke",
                                    "user_name": user_name,
                                    "source_visit_id": case_id,
                                    "collected_at": collected_at,
                                    "modality": "ask",
                                }
                            )
                finally:
                    workbook.release_resources()
        except Exception:
            continue

    if not modality_rows:
        return pd.DataFrame()

    modality_df = pd.DataFrame(modality_rows).drop_duplicates(
        subset=["source_vendor", "user_name", "source_visit_id", "collected_at", "modality"]
    )
    visits = (
        modality_df.assign(flag=True)
        .pivot_table(
            index=["source_vendor", "user_name", "source_visit_id", "collected_at"],
            columns="modality",
            values="flag",
            aggfunc="max",
            fill_value=False,
        )
        .reset_index()
    )
    visits.columns.name = None
    for modality in ZHONGKE_MODALITIES:
        if modality not in visits.columns:
            visits[modality] = False
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
                "source_visit_id": case_dir.name,
                "collected_at": collected_at,
                "ask": json_file_has_payload(case_dir / "dataAsk.json"),
                "pulse": json_file_has_payload(case_dir / "pulse" / "dataPulse.json"),
                "tongue": json_file_has_payload(case_dir / "tongue" / "dataTongue.json"),
                "voice": json_file_has_payload(case_dir / "voice" / "dataVoice.json"),
            }
        )
    if not rows:
        return pd.DataFrame()
    visits = pd.DataFrame(rows).drop_duplicates(subset=["source_vendor", "user_name", "source_visit_id"])
    for modality in YUSHENGTANG_MODALITIES:
        if modality not in visits.columns:
            visits[modality] = False
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


def cluster_sessions(visits: pd.DataFrame) -> pd.DataFrame:
    session_rows: list[dict[str, object]] = []
    grouped = visits.sort_values(["user_name", "collected_at", "source_vendor"]).groupby(["user_name", "date"], sort=True)
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
                }
            )
    return pd.DataFrame(slot_rows)


def build_detail_export(day_slots: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    if day_slots.empty:
        return pd.DataFrame()
    sessions_lookup = sessions.set_index("cluster_id")
    rows: list[dict[str, object]] = []
    for _, slot_row in day_slots.iterrows():
        session_row = sessions_lookup.loc[slot_row["cluster_id"]]
        remark = ""
        if slot_row["slot_status"] == "suspicious":
            remark = u("\\u7591\\u4f3c\\u4f5c\\u5f0a\\uff1a10\\u5206\\u949f\\u5185\\u8fde\\u7eed\\u591a\\u6b21\\u6253\\u5361")
        elif slot_row["slot_status"] == "invalid":
            if slot_row["reason"] == "gap_lt_30m":
                remark = u("\\u95f4\\u9694\\u8fc7\\u77ed\\uff1a\\u5c0f\\u4e8e 30 \\u5206\\u949f")
            elif slot_row["reason"] == "overflow_gt_3":
                remark = u("\\u8d85\\u51fa\\u5355\\u65e5\\u4e09\\u6b21\\u663e\\u793a\\u4e0a\\u9650")
        elif slot_row["slot_status"] == "incomplete":
            remark = u("\\u4e0d\\u5b8c\\u6574\\uff1a\\u5fc5\\u9700\\u6a21\\u6001\\u4e0d\\u5168")

        rows.append(
            {
                COL_NAME: slot_row["user_name"],
                COL_DATE: pd.Timestamp(slot_row["date"]).normalize(),
                COL_TIME: pd.Timestamp(slot_row["cluster_start"]).strftime("%H:%M:%S"),
                COL_SLOT: slot_row["slot_label"] or "",
                COL_STATUS: slot_row["slot_status"],
                COL_REMARK: remark,
                COL_ZK_ASK: "1" if "zhongke" in str(session_row["source_vendors"]) else "",
                COL_ZK_PULSE: "1" if bool(slot_row["zhongke_complete"]) else "",
                COL_ZK_TONGUE: "1" if bool(slot_row["zhongke_complete"]) else "",
                COL_ZK_FACE: "1" if bool(slot_row["zhongke_complete"]) else "",
                COL_YST_ASK: "1" if "yushengtang" in str(session_row["source_vendors"]) else "",
                COL_YST_PULSE: "1" if bool(slot_row["yushengtang_complete"]) else "",
                COL_YST_TONGUE: "1" if bool(slot_row["yushengtang_complete"]) else "",
                COL_YST_VOICE: "1" if bool(slot_row["yushengtang_complete"]) else "",
                "cluster_id": slot_row["cluster_id"],
            }
        )
    return pd.DataFrame(rows).sort_values([COL_NAME, COL_DATE, COL_TIME, COL_SLOT]).reset_index(drop=True)


def build_date_index(visits: pd.DataFrame) -> pd.DatetimeIndex:
    start = pd.Timestamp(visits["date"].min()).normalize()
    end = pd.Timestamp(visits["date"].max()).normalize()
    return pd.date_range(start, end, freq="D")


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

        matrix_dates = [day.strftime("%Y-%m-%d") for day in date_index]
        matrix_sheet.write(0, 0, u("\\u7528\\u6237\\u65f6\\u6bb5"), header_fmt)
        for col_idx, date_label in enumerate(matrix_dates, start=1):
            matrix_sheet.write(0, col_idx, date_label, header_fmt)

        detail_columns = [column for column in detail_df.columns if column != "cluster_id"]
        for col_idx, column in enumerate(detail_columns):
            detail_sheet.write(0, col_idx, column, header_fmt)
        for row_idx, row in detail_df.iterrows():
            excel_row = row_idx + 1
            for col_idx, column in enumerate(detail_columns):
                detail_sheet.write(excel_row, col_idx, row[column], blank_fmt)

        status_priority = {"suspicious": 4, "invalid": 3, "incomplete": 2, "complete": 1}
        key_to_status: dict[tuple[str, str, str], str] = {}
        key_to_detail_row: dict[tuple[str, str, str], int] = {}
        key_to_device_count: dict[tuple[str, str, str], int] = {}
        for row_idx, row in detail_df.iterrows():
            key = (str(row[COL_NAME]), str(row[COL_SLOT]), pd.Timestamp(row[COL_DATE]).strftime("%Y-%m-%d"))
            status = str(row[COL_STATUS])
            device_count = 0
            if any(str(row[col] or "").strip() for col in [COL_ZK_ASK, COL_ZK_PULSE, COL_ZK_TONGUE, COL_ZK_FACE]):
                device_count += 1
            if any(str(row[col] or "").strip() for col in [COL_YST_ASK, COL_YST_PULSE, COL_YST_TONGUE, COL_YST_VOICE]):
                device_count += 1
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
        detail_sheet.set_column(3, len(detail_columns) - 1, 16)


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
    visits["collected_at"] = pd.to_datetime(visits["collected_at"])
    visits = visits.sort_values(["user_name", "collected_at", "source_vendor"]).reset_index(drop=True)

    modality_rules = determine_required_modalities(visits)
    visits = apply_visit_quality_flags(visits, modality_rules)
    sessions = cluster_sessions(visits)
    day_slots = assign_day_slots(sessions)
    detail_df = build_detail_export(day_slots, sessions)
    user_names = sorted(visits["user_name"].dropna().astype(str).unique().tolist())
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
