from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
import xlsxwriter

import run_cohort_validation_v1 as rv
from analyze_cohort_checkin_matrix import SLOT_LABELS, coerce_id, load_json_relaxed, parse_datetime_value, parse_zhongke_visits
from pdf_report_parser import parse_pdf_report


APRIL_START = pd.Timestamp("2026-04-01")
APRIL_END = pd.Timestamp("2026-05-01")
ID_MAPPING = rv.PROJECT_ROOT / "datasets" / "id_mapping" / "cohort_20_name_to_ids.csv"
OUTPUT = rv.OUTPUT_DIR / "cohort_checkin_matrix_202604_timewindow.xlsx"
YST_APRIL_DIR = rv.DATA_ROOT / "玉生堂四诊仪" / "2026.04.01-2026.04.31"
ZHONGKE_APRIL_DIR = rv.DATA_ROOT / "中科四诊仪" / "2026.04"

COL_NAME = "姓名"
COL_CASE_ID = "病例号"
COL_DATE = "日期"
COL_TIME = "具体时间"
COL_SLOT = "时段"
COL_STATUS = "状态"
COL_REMARK = "备注"
COL_VENDOR = "四诊仪"
COL_CAID = "CaId"
COL_ID_SOURCE = "身份来源"
COL_PDF_NAME = "PDF姓名"
COL_PDF_TIME = "PDF评估时间"
COL_FOLDER_NAME = "文件夹姓名"
COL_CASE_DIR = "原始目录"
COL_DUP = "是否重复"
COL_ASK = "问诊"
COL_PULSE = "脉诊"
COL_TONGUE = "舌诊"
COL_VOICE = "声诊"
COL_FACE = "面诊"
COL_PDF = "PDF报告"
COL_ASK_PATH = "问诊路径"
COL_PULSE_PATH = "脉诊路径"
COL_TONGUE_PATH = "舌诊路径"
COL_VOICE_PATH = "声诊路径"
COL_FACE_PATH = "面诊路径"
COL_PDF_PATH = "PDF路径"


def split_ids(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return []
    return [part.strip() for part in text.split("|") if part.strip()]


def load_cohort_identity_map() -> tuple[list[str], dict[str, str], dict[str, str]]:
    if not ID_MAPPING.exists():
        return [], {}, {}
    frame = pd.read_csv(ID_MAPPING, dtype=str).fillna("")
    cohort_names = [str(value).strip() for value in frame["roster_name"] if str(value).strip()]
    caid_to_name: dict[str, str] = {}
    phone_to_name: dict[str, str] = {}
    for _, row in frame.iterrows():
        name = str(row.get("roster_name", "")).strip()
        for caid in split_ids(row.get("yst_caid")):
            caid_to_name[caid] = name
        for phone in split_ids(row.get("yst_phone")):
            phone_to_name[phone] = name
    return cohort_names, caid_to_name, phone_to_name


def read_json(path: Path) -> object | None:
    return load_json_relaxed(path) if path.exists() else None


def json_has_payload(path: Path) -> bool:
    payload = read_json(path)
    if isinstance(payload, list):
        return len(payload) > 0
    if isinstance(payload, dict):
        return bool(payload)
    return False


def first_caid_from_case(case_dir: Path) -> str:
    candidates = [
        case_dir / "dataAsk.json",
        case_dir / "pulse" / "dataPulse.json",
        case_dir / "tongue" / "dataTongue.json",
        case_dir / "voice" / "dataVoice.json",
        case_dir / "customerArchive.json",
    ]
    for path in candidates:
        payload = read_json(path)
        if isinstance(payload, dict):
            caid = str(payload.get("CaId", "")).strip()
            if caid and caid != "0":
                return caid
        elif isinstance(payload, list):
            counts = Counter(
                str(item.get("CaId", "")).strip()
                for item in payload
                if isinstance(item, dict) and str(item.get("CaId", "")).strip()
            )
            caid = next((value for value, _ in counts.most_common() if value != "0"), "")
            if caid:
                return caid
    return ""


def start_time_from_json(case_dir: Path) -> pd.Timestamp | None:
    pulse_payload = read_json(case_dir / "pulse" / "dataPulse.json")
    if isinstance(pulse_payload, dict):
        raw = pulse_payload.get("StartTime")
        if raw:
            try:
                ts = pd.to_datetime(raw, utc=True)
                return pd.Timestamp(ts.tz_convert("Asia/Shanghai").tz_localize(None))
            except Exception:
                return None
    return None


def leading_time(case_id: str) -> pd.Timestamp | None:
    try:
        return pd.Timestamp(pd.to_datetime(case_id[:14], format="%Y%m%d%H%M%S"))
    except Exception:
        return None


def file_md5(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def build_case_dir_index(root: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = defaultdict(list)
    for path in root.rglob("*"):
        if path.is_dir() and path.name.isdigit() and len(path.name) >= 13:
            index[path.name].append(path)
    return index


def parse_case_dir(
    case_dir: Path,
    cohort_names: list[str],
    caid_to_name: dict[str, str],
    phone_to_name: dict[str, str],
    alias_map: dict[str, str],
    *,
    duplicate: bool = False,
) -> dict[str, object]:
    case_id = case_dir.name
    pdf_path = case_dir / f"{case_id}.pdf"
    pdf_info = parse_pdf_report(pdf_path) if pdf_path.exists() else None
    caid = first_caid_from_case(case_dir)
    json_time = start_time_from_json(case_dir)
    collected_at = json_time or (pdf_info.report_time if pdf_info else None) or leading_time(case_id)
    pdf_name = pdf_info.name if pdf_info else ""
    pdf_phone = (pdf_info.phone_masked if pdf_info else "").replace("*", "")

    canonical_name = ""
    id_source = ""
    if caid and caid in caid_to_name:
        canonical_name = caid_to_name[caid]
        id_source = "CaId"
    elif pdf_name and rv.canonicalize_name(pdf_name, alias_map) in cohort_names:
        canonical_name = rv.canonicalize_name(pdf_name, alias_map)
        id_source = "PDF姓名"
    elif pdf_phone and pdf_phone in phone_to_name:
        canonical_name = phone_to_name[pdf_phone]
        id_source = "PDF脱敏电话"

    ask_path = case_dir / "dataAsk.json"
    pulse_json = case_dir / "pulse" / "dataPulse.json"
    pulse_image = case_dir / "pulse" / "pulseImage.jpg"
    tongue_json = case_dir / "tongue" / "dataTongue.json"
    tongue_images = [
        case_dir / "tongue" / "OriginPic.jpg",
        case_dir / "tongue" / "CutPic.jpg",
        case_dir / "tongue" / "RectanglePic.jpg",
    ]
    voice_json = case_dir / "voice" / "dataVoice.json"

    has_ask = json_has_payload(ask_path)
    has_pulse = pulse_json.exists() or pulse_image.exists()
    has_tongue = tongue_json.exists() or any(path.exists() for path in tongue_images)
    has_voice = voice_json.exists()
    has_pdf = pdf_path.exists()
    missing = []
    if not has_ask:
        missing.append("问诊")
    if not has_pulse:
        missing.append("脉诊")
    if not has_tongue:
        missing.append("舌诊")
    if not has_voice:
        missing.append("声诊")
    if not has_pdf:
        missing.append("PDF")

    status = "complete" if has_pdf and has_pulse and has_tongue and not duplicate else "incomplete"
    if duplicate:
        status = "duplicate"
    remarks = []
    if missing:
        remarks.append("缺少模态：" + ",".join(missing))
    if not canonical_name:
        remarks.append("未能映射到20人cohort")
    if pdf_name and canonical_name and rv.normalize_name(pdf_name) != rv.normalize_name(canonical_name):
        remarks.append(f"PDF姓名与映射姓名不一致：PDF={pdf_name}")
    if duplicate:
        remarks.append("重复病例目录")

    return {
        COL_NAME: canonical_name or pdf_name or "",
        COL_CASE_ID: case_id,
        COL_DATE: pd.Timestamp(collected_at).normalize() if collected_at is not None else "",
        COL_TIME: pd.Timestamp(collected_at).strftime("%H:%M:%S") if collected_at is not None else "",
        COL_SLOT: "重复" if duplicate else "",
        COL_STATUS: status,
        COL_REMARK: "；".join(remarks),
        COL_VENDOR: "玉生堂",
        COL_CAID: caid,
        COL_ID_SOURCE: id_source,
        COL_PDF_NAME: pdf_name,
        COL_PDF_TIME: "" if not pdf_info or pdf_info.report_time is None else pdf_info.report_time.strftime("%Y-%m-%d %H:%M:%S"),
        COL_FOLDER_NAME: case_dir.parent.name,
        COL_CASE_DIR: str(case_dir),
        COL_DUP: "1" if duplicate else "",
        COL_ASK: "1" if has_ask else "",
        COL_PULSE: "1" if has_pulse else "",
        COL_TONGUE: "1" if has_tongue else "",
        COL_VOICE: "1" if has_voice else "",
        COL_FACE: "",
        COL_PDF: "1" if has_pdf else "",
        COL_ASK_PATH: str(ask_path) if ask_path.exists() else "",
        COL_PULSE_PATH: str(pulse_json if pulse_json.exists() else pulse_image if pulse_image.exists() else ""),
        COL_TONGUE_PATH: str(tongue_json if tongue_json.exists() else next((p for p in tongue_images if p.exists()), "")),
        COL_VOICE_PATH: str(voice_json) if voice_json.exists() else "",
        COL_FACE_PATH: "",
        COL_PDF_PATH: str(pdf_path) if pdf_path.exists() else "",
        "_collected_at": collected_at,
        "_modality_score": int(has_ask) + int(has_pulse) + int(has_tongue) + int(has_voice) + int(has_pdf),
        "_vendor_key": "yst",
        "_pdf_md5": file_md5(pdf_path),
    }


def build_raw_detail(
    cohort_names: list[str],
    caid_to_name: dict[str, str],
    phone_to_name: dict[str, str],
    alias_map: dict[str, str],
) -> pd.DataFrame:
    if not YST_APRIL_DIR.exists():
        raise RuntimeError(f"April Yushengtang directory not found: {YST_APRIL_DIR}")
    yst_root = YST_APRIL_DIR.parent
    case_index = build_case_dir_index(yst_root)
    rows = []
    duplicate_rows = []
    for case_dir in sorted(path for path in YST_APRIL_DIR.iterdir() if path.is_dir() and path.name.isdigit()):
        rows.append(parse_case_dir(case_dir, cohort_names, caid_to_name, phone_to_name, alias_map, duplicate=False))
        for duplicate_dir in sorted(path for path in case_index.get(case_dir.name, []) if path.resolve() != case_dir.resolve()):
            duplicate_rows.append(parse_case_dir(duplicate_dir, cohort_names, caid_to_name, phone_to_name, alias_map, duplicate=True))
    detail = pd.DataFrame(rows + duplicate_rows)
    if detail.empty:
        return detail
    detail["_sort_dup"] = detail[COL_DUP].astype(str).ne("").astype(int)
    detail["_sort_name"] = detail[COL_NAME].fillna("")
    detail["_sort_date"] = pd.to_datetime(detail[COL_DATE], errors="coerce")
    detail["_sort_time"] = detail[COL_TIME].fillna("")
    return detail.sort_values(["_sort_dup", "_sort_name", "_sort_date", "_sort_time", COL_CASE_ID]).reset_index(drop=True)


def first_text(values: pd.Series) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and text.lower() != "nan":
            return text
    return ""


def zhongke_cluster_key_frame(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.sort_values(["canonical_name", "source_visit_id", "collected_at"]).copy()
    cluster_ids: list[int] = []
    cluster_id = -1
    last_key: tuple[str, str] | None = None
    cluster_start: pd.Timestamp | None = None
    for _, row in raw.iterrows():
        key = (str(row["canonical_name"]), str(row["source_visit_id"]))
        ts = row["collected_at"]
        start_new = (
            last_key != key
            or pd.isna(ts)
            or cluster_start is None
            or pd.Timestamp(ts) - cluster_start > pd.Timedelta(minutes=5)
        )
        if start_new:
            cluster_id += 1
            cluster_start = None if pd.isna(ts) else pd.Timestamp(ts)
        cluster_ids.append(cluster_id)
        last_key = key
    raw["_zk_cluster_id"] = cluster_ids
    return raw


def classify_zhongke_export_modality(path: Path, sheet_name: str) -> str | None:
    text = f"{path} {sheet_name}"
    if "问诊汇总" in sheet_name or re.search(r"问诊", text):
        return "ask"
    if re.search(r"脉诊", text):
        return "pulse"
    if re.search(r"舌诊", text):
        return "tongue"
    if re.search(r"面诊", text):
        return "face"
    return None


def parse_zhongke_table_exports(root: Path) -> pd.DataFrame:
    modality_rows: list[dict[str, object]] = []
    excel_paths = sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in {".xls", ".xlsx"})
    for path in excel_paths:
        try:
            excel = pd.ExcelFile(path)
        except Exception:
            continue
        for sheet_name in excel.sheet_names:
            modality = classify_zhongke_export_modality(path, sheet_name)
            if modality is None:
                continue
            try:
                frame = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=object)
            except Exception:
                continue
            seen_keys: set[tuple[str, str, str, pd.Timestamp]] = set()
            for _, row in frame.iterrows():
                values = row.tolist()
                if len(values) < 8:
                    continue
                user_name = str(values[2] or "").strip()
                collected_at = parse_datetime_value(values[6])
                case_id = coerce_id(values[7])
                if not user_name or user_name.lower() == "nan" or not case_id or collected_at is None:
                    continue
                key = (user_name, case_id, modality, collected_at)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                modality_rows.append(
                    {
                        "source_vendor": "zhongke",
                        "user_name": user_name,
                        "folder_name": path.parent.name,
                        "source_visit_id": case_id,
                        "collected_at": collected_at,
                        "modality": modality,
                        "source_file_path": str(path),
                    }
                )
    if not modality_rows:
        return pd.DataFrame()

    modality_df = pd.DataFrame(modality_rows).drop_duplicates(
        subset=["source_vendor", "user_name", "source_visit_id", "collected_at", "modality"]
    )
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
    path_df.columns = [f"path_{column}" if column in {"ask", "pulse", "tongue", "face"} else column for column in path_df.columns]
    visits = visits.merge(path_df, on=["source_vendor", "user_name", "folder_name", "source_visit_id", "collected_at"], how="left")
    for modality in ("ask", "pulse", "tongue", "face"):
        if modality not in visits.columns:
            visits[modality] = False
        path_col = f"path_{modality}"
        if path_col not in visits.columns:
            visits[path_col] = ""
    return visits


def build_zhongke_detail(cohort_names: list[str], alias_map: dict[str, str]) -> pd.DataFrame:
    if not ZHONGKE_APRIL_DIR.exists():
        raise RuntimeError(f"April Zhongke directory not found: {ZHONGKE_APRIL_DIR}")
    raw = parse_zhongke_visits(ZHONGKE_APRIL_DIR)
    if raw.empty:
        raw = parse_zhongke_table_exports(ZHONGKE_APRIL_DIR)
    if raw.empty:
        return pd.DataFrame()

    raw = raw.copy()
    raw["canonical_name"] = raw["user_name"].map(lambda value: rv.canonicalize_name(value, alias_map))
    raw["collected_at"] = pd.to_datetime(raw["collected_at"], errors="coerce")
    raw = raw.loc[
        raw["canonical_name"].isin(cohort_names)
        & raw["collected_at"].ge(APRIL_START)
        & raw["collected_at"].lt(APRIL_END)
    ].copy()
    if raw.empty:
        return pd.DataFrame()
    raw = zhongke_cluster_key_frame(raw)

    rows: list[dict[str, object]] = []
    group_cols = ["_zk_cluster_id", "source_visit_id", "canonical_name"]
    for (_, visit_id, canonical_name), group in raw.groupby(group_cols, dropna=False, sort=True):
        collected_at = group["collected_at"].dropna().min()
        has_ask = bool(group["ask"].fillna(False).astype(bool).any())
        has_pulse = bool(group["pulse"].fillna(False).astype(bool).any())
        has_tongue = bool(group["tongue"].fillna(False).astype(bool).any())
        has_face = bool(group["face"].fillna(False).astype(bool).any())
        missing = []
        if not has_ask:
            missing.append("问诊")
        if not has_pulse:
            missing.append("脉诊")
        if not has_tongue:
            missing.append("舌诊")
        if not has_face:
            missing.append("面诊")

        raw_names = sorted({str(value).strip() for value in group["user_name"] if str(value).strip()})
        remarks = []
        if missing:
            remarks.append("缺少模态：" + ",".join(missing))
        if any(rv.normalize_name(name) != rv.normalize_name(canonical_name) for name in raw_names):
            remarks.append("表格姓名按别名映射归一：" + ",".join(raw_names))
        collected_times = sorted(
            pd.Timestamp(value).strftime("%H:%M:%S")
            for value in group["collected_at"].dropna().unique()
        )
        if len(collected_times) > 1:
            remarks.append("同病例号5分钟内多模态合并：" + ",".join(collected_times))

        rows.append(
            {
                COL_NAME: canonical_name,
                COL_CASE_ID: str(visit_id or ""),
                COL_DATE: pd.Timestamp(collected_at).normalize() if pd.notna(collected_at) else "",
                COL_TIME: pd.Timestamp(collected_at).strftime("%H:%M:%S") if pd.notna(collected_at) else "",
                COL_SLOT: "",
                COL_STATUS: "complete" if has_ask and has_pulse and has_tongue and has_face else "incomplete",
                COL_REMARK: "；".join(remarks),
                COL_VENDOR: "中科",
                COL_CAID: "",
                COL_ID_SOURCE: "中科表格姓名",
                COL_PDF_NAME: "",
                COL_PDF_TIME: "",
                COL_FOLDER_NAME: ",".join(sorted({str(value).strip() for value in group["folder_name"] if str(value).strip()})),
                COL_CASE_DIR: str(ZHONGKE_APRIL_DIR),
                COL_DUP: "",
                COL_ASK: "1" if has_ask else "",
                COL_PULSE: "1" if has_pulse else "",
                COL_TONGUE: "1" if has_tongue else "",
                COL_VOICE: "",
                COL_FACE: "1" if has_face else "",
                COL_PDF: "",
                COL_ASK_PATH: first_text(group.loc[group["ask"].fillna(False).astype(bool), "path_ask"]),
                COL_PULSE_PATH: first_text(group.loc[group["pulse"].fillna(False).astype(bool), "path_pulse"]),
                COL_TONGUE_PATH: first_text(group.loc[group["tongue"].fillna(False).astype(bool), "path_tongue"]),
                COL_VOICE_PATH: "",
                COL_FACE_PATH: first_text(group.loc[group["face"].fillna(False).astype(bool), "path_face"]),
                COL_PDF_PATH: "",
                "_collected_at": collected_at if pd.notna(collected_at) else None,
                "_modality_score": int(has_ask) + int(has_pulse) + int(has_tongue) + int(has_face),
                "_vendor_key": "zhongke",
                "_pdf_md5": "",
            }
        )

    detail = pd.DataFrame(rows)
    detail["_sort_dup"] = detail[COL_DUP].astype(str).ne("").astype(int)
    detail["_sort_name"] = detail[COL_NAME].fillna("")
    detail["_sort_date"] = pd.to_datetime(detail[COL_DATE], errors="coerce")
    detail["_sort_time"] = detail[COL_TIME].fillna("")
    return detail.sort_values(["_sort_dup", "_sort_name", "_sort_date", "_sort_time", COL_CASE_ID]).reset_index(drop=True)


def assign_slots(detail: pd.DataFrame, cohort_names: list[str]) -> pd.DataFrame:
    detail = detail.copy()
    detail["_is_matrix_candidate"] = False
    candidate_mask = detail[COL_NAME].isin(cohort_names) & detail[COL_DUP].astype(str).eq("")
    timestamps = pd.to_datetime(
        pd.to_datetime(detail[COL_DATE], errors="coerce").dt.strftime("%Y-%m-%d") + " " + detail[COL_TIME].astype(str),
        errors="coerce",
    )
    for idx in detail[candidate_mask].index:
        ts = timestamps.loc[idx]
        if pd.isna(ts):
            continue
        if ts.time() < pd.Timestamp("11:00").time():
            slot = "早"
        elif ts.time() < pd.Timestamp("16:00").time():
            slot = "中"
        else:
            slot = "晚"
        detail.loc[idx, COL_SLOT] = slot
        detail.loc[idx, "_is_matrix_candidate"] = True
    return detail


def matrix_from_detail(detail: pd.DataFrame, cohort_names: list[str], date_index: pd.DatetimeIndex) -> pd.DataFrame:
    labels = [f"{name}-{slot}" for name in cohort_names for slot in SLOT_LABELS]
    matrix = pd.DataFrame(0, index=labels, columns=[day.strftime("%Y-%m-%d") for day in date_index])
    for _, row in detail[detail["_is_matrix_candidate"]].iterrows():
        label = f"{row[COL_NAME]}-{row[COL_SLOT]}"
        date_label = pd.Timestamp(row[COL_DATE]).strftime("%Y-%m-%d")
        if label in matrix.index and date_label in matrix.columns:
            matrix.loc[label, date_label] += 1
    return matrix


def available_output_path(path: Path) -> Path:
    try:
        with path.open("ab"):
            return path
    except PermissionError:
        return path.with_name(f"{path.stem}_raw_detail{path.suffix}")


def build_person_summary(detail: pd.DataFrame, cohort_names: list[str]) -> pd.DataFrame:
    rows = []
    for name in cohort_names:
        name_rows = detail.loc[detail[COL_NAME].eq(name)]
        yst_rows = name_rows.loc[name_rows[COL_VENDOR].eq("玉生堂") & name_rows[COL_DUP].astype(str).eq("")]
        zk_rows = name_rows.loc[name_rows[COL_VENDOR].eq("中科") & name_rows[COL_DUP].astype(str).eq("")]
        rows.append(
            {
                "姓名": name,
                "总计有效打卡次数": int(name_rows.get("_is_matrix_candidate", pd.Series(dtype=bool)).fillna(False).sum()),
                "总计全部打卡次数": int(name_rows[COL_DUP].astype(str).eq("").sum()),
                "玉生堂有效打卡次数": int(yst_rows.get("_is_matrix_candidate", pd.Series(dtype=bool)).fillna(False).sum()),
                "玉生堂全部打卡次数": int(len(yst_rows)),
                "中科有效打卡次数": int(zk_rows.get("_is_matrix_candidate", pd.Series(dtype=bool)).fillna(False).sum()),
                "中科全部打卡次数": int(len(zk_rows)),
            }
        )
    return pd.DataFrame(rows)


def write_workbook(detail: pd.DataFrame, matrix: pd.DataFrame, date_index: pd.DatetimeIndex, summary: pd.DataFrame) -> Path:
    output_path = available_output_path(OUTPUT)
    columns = [
        COL_NAME, COL_CASE_ID, COL_DATE, COL_TIME, COL_SLOT, COL_STATUS, COL_REMARK,
        COL_VENDOR, COL_CAID, COL_ID_SOURCE, COL_PDF_NAME, COL_PDF_TIME, COL_FOLDER_NAME,
        COL_CASE_DIR, COL_DUP, COL_ASK, COL_PULSE, COL_TONGUE, COL_VOICE, COL_FACE, COL_PDF,
        COL_ASK_PATH, COL_PULSE_PATH, COL_TONGUE_PATH, COL_VOICE_PATH, COL_FACE_PATH, COL_PDF_PATH,
    ]
    with pd.ExcelWriter(output_path, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        workbook: xlsxwriter.Workbook = writer.book
        matrix_sheet = workbook.add_worksheet("打卡矩阵")
        yst_sheet = workbook.add_worksheet("玉生堂打卡详情")
        zhongke_sheet = workbook.add_worksheet("中科打卡详情")
        summary_sheet = workbook.add_worksheet("个人汇总")
        rules_sheet = workbook.add_worksheet("规则说明")
        writer.sheets["打卡矩阵"] = matrix_sheet
        writer.sheets["玉生堂打卡详情"] = yst_sheet
        writer.sheets["中科打卡详情"] = zhongke_sheet
        writer.sheets["个人汇总"] = summary_sheet
        writer.sheets["规则说明"] = rules_sheet

        header = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1, "align": "center"})
        row_label = workbook.add_format({"bold": True, "border": 1})
        blank = workbook.add_format({"border": 1, "align": "center"})
        green = workbook.add_format({"border": 1, "align": "center", "bg_color": "#C6EFCE", "font_color": "#0563C1", "underline": 1})
        yellow = workbook.add_format({"border": 1, "align": "center", "bg_color": "#FFEB9C", "font_color": "#0563C1", "underline": 1})
        red = workbook.add_format({"border": 1, "align": "center", "bg_color": "#FFC7CE", "font_color": "#0563C1", "underline": 1})
        text_fmt = workbook.add_format({"border": 1, "valign": "top"})
        red_text = workbook.add_format({"border": 1, "valign": "top", "bg_color": "#FFC7CE"})
        link_fmt = workbook.add_format({"border": 1, "valign": "top", "font_color": "#0563C1", "underline": 1})
        red_link = workbook.add_format({"border": 1, "valign": "top", "bg_color": "#FFC7CE", "font_color": "#0563C1", "underline": 1})

        yst_detail = detail.loc[detail[COL_VENDOR].eq("玉生堂")].reset_index(drop=False)
        zhongke_detail = detail.loc[detail[COL_VENDOR].eq("中科")].reset_index(drop=False)
        detail_targets: dict[int, tuple[str, int]] = {}
        for row_idx, row in yst_detail.iterrows():
            detail_targets[int(row["index"])] = ("玉生堂打卡详情", row_idx + 2)
        for row_idx, row in zhongke_detail.iterrows():
            detail_targets[int(row["index"])] = ("中科打卡详情", row_idx + 2)

        matrix_sheet.write(0, 0, "用户时段", header)
        for col_idx, date_label in enumerate(matrix.columns, start=1):
            matrix_sheet.write(0, col_idx, date_label, header)

        key_to_detail_target = {}
        for idx, row in detail[detail["_is_matrix_candidate"]].iterrows():
            key = (str(row[COL_NAME]), str(row[COL_SLOT]), pd.Timestamp(row[COL_DATE]).strftime("%Y-%m-%d"))
            if idx in detail_targets:
                key_to_detail_target.setdefault(key, detail_targets[idx])
        for row_idx, label in enumerate(matrix.index, start=1):
            matrix_sheet.write(row_idx, 0, label, row_label)
            name, slot = label.rsplit("-", 1)
            for col_idx, date_label in enumerate(matrix.columns, start=1):
                key = (name, slot, date_label)
                count = int(matrix.loc[label, date_label] or 0)
                if count > 0 and key in key_to_detail_target:
                    cell_format = green if count == 1 else yellow
                    target_sheet, target_row = key_to_detail_target[key]
                    matrix_sheet.write_url(
                        row_idx,
                        col_idx,
                        f"internal:'{target_sheet}'!A{target_row}",
                        cell_format,
                        string=str(count),
                    )
                else:
                    matrix_sheet.write_blank(row_idx, col_idx, None, blank)

        path_columns = {COL_CASE_DIR, COL_ASK_PATH, COL_PULSE_PATH, COL_TONGUE_PATH, COL_VOICE_PATH, COL_FACE_PATH, COL_PDF_PATH}

        def write_detail_sheet(sheet: xlsxwriter.worksheet.Worksheet, frame: pd.DataFrame) -> None:
            for col_idx, column in enumerate(columns):
                sheet.write(0, col_idx, column, header)
            for row_idx, row in frame.iterrows():
                is_red = bool(row.get(COL_DUP)) or row.get(COL_STATUS) in {"duplicate", "incomplete"} or not row.get(COL_NAME)
                for col_idx, column in enumerate(columns):
                    value = row.get(column, "")
                    fmt = red_link if is_red and column in path_columns and value else link_fmt if column in path_columns and value else red_text if is_red else text_fmt
                    if column == COL_DATE and isinstance(value, pd.Timestamp):
                        sheet.write_datetime(row_idx + 1, col_idx, value.to_pydatetime(), fmt)
                    elif column in path_columns and value and Path(str(value)).exists():
                        sheet.write_url(row_idx + 1, col_idx, f"external:{Path(str(value))}", fmt, string=str(value))
                    else:
                        sheet.write(row_idx + 1, col_idx, value, fmt)

        write_detail_sheet(yst_sheet, yst_detail)
        write_detail_sheet(zhongke_sheet, zhongke_detail)

        for col_idx, column in enumerate(summary.columns):
            summary_sheet.write(0, col_idx, column, header)
        for row_idx, row in summary.iterrows():
            for col_idx, column in enumerate(summary.columns):
                summary_sheet.write(row_idx + 1, col_idx, row[column], text_fmt)

        rules = [
            ("rule_version", rv.RULE_VERSION),
            ("detail_grain_yst", "玉生堂打卡详情一行对应一个原始玉生堂病例目录；病例号显示在第二列"),
            ("detail_grain_zhongke", "中科打卡详情一行对应一个中科表格病例号/采集时间聚合后的原始采集记录；病例号显示在第二列"),
            ("pdf_fallback", "当结构化JSON缺失时，从PDF报告解析姓名、档案编号、评估日期"),
            ("identity_priority", "身份优先级：CaId映射 > PDF姓名 > PDF脱敏电话"),
            ("slot_definition", "早/中/晚按时间窗划分：早 <11:00；中 11:00-15:59:59；晚 >=16:00"),
            ("matrix_count", "矩阵单元格显示该用户该日期该时段的玉生堂+中科原始记录次数，超过一次显示实际数字"),
            ("duplicates", "重复病例目录排在详细记录末尾，时段列标注为重复"),
            ("zhongke_source", str(ZHONGKE_APRIL_DIR)),
        ]
        for row_idx, (key, value) in enumerate(rules):
            rules_sheet.write(row_idx, 0, key, row_label)
            rules_sheet.write(row_idx, 1, value, text_fmt)

        matrix_sheet.freeze_panes(1, 1)
        yst_sheet.freeze_panes(1, 0)
        zhongke_sheet.freeze_panes(1, 0)
        summary_sheet.freeze_panes(1, 0)
        matrix_sheet.set_column(0, 0, 18)
        matrix_sheet.set_column(1, len(matrix.columns), 4.2)
        for sheet in (yst_sheet, zhongke_sheet):
            sheet.set_column(0, 0, 12)
            sheet.set_column(1, 1, 22)
            sheet.set_column(2, 12, 16)
            sheet.set_column(13, len(columns) - 1, 58)
        summary_sheet.set_column(0, len(summary.columns) - 1, 18)
    return output_path


def main() -> None:
    rv.ensure_output_dirs()
    cohort_names, caid_to_name, phone_to_name = load_cohort_identity_map()
    if not cohort_names:
        cohort_names = sorted(path.name for path in rv.REFERENCE_DIR.iterdir() if path.is_dir())
    alias_map = rv.load_name_alias_config()
    alias_map.update({rv.normalize_name(name): name for name in cohort_names})

    yst_detail = build_raw_detail(cohort_names, caid_to_name, phone_to_name, alias_map)
    yst_detail = yst_detail.loc[
        (yst_detail[COL_DUP].astype(str).ne(""))
        | ((pd.to_datetime(yst_detail[COL_DATE], errors="coerce") >= APRIL_START) & (pd.to_datetime(yst_detail[COL_DATE], errors="coerce") < APRIL_END))
        | (yst_detail[COL_DATE].astype(str).eq(""))
    ].copy()
    zhongke_detail = build_zhongke_detail(cohort_names, alias_map)
    detail = pd.concat([yst_detail, zhongke_detail], ignore_index=True, sort=False).fillna("")
    detail = assign_slots(detail, cohort_names)
    date_index = pd.date_range(APRIL_START, APRIL_END - pd.Timedelta(days=1), freq="D")
    matrix = matrix_from_detail(detail, cohort_names, date_index)
    summary = build_person_summary(detail, cohort_names)
    output_path = write_workbook(detail, matrix, date_index, summary)

    yst_rows = int(detail[COL_VENDOR].eq("玉生堂").sum())
    zhongke_rows = int(detail[COL_VENDOR].eq("中科").sum())
    primary_rows = int(detail[COL_DUP].astype(str).eq("").sum())
    duplicate_rows = int(detail[COL_DUP].astype(str).ne("").sum())
    print(f"Workbook: {output_path}")
    print(f"Yushengtang detail rows: {yst_rows}")
    print(f"Zhongke detail rows: {zhongke_rows}")
    print(f"Primary raw rows: {primary_rows}")
    print(f"Duplicate rows: {duplicate_rows}")
    print(f"Total detail rows: {len(detail)}")
    print(f"Mapped cohort rows: {int(detail[COL_NAME].isin(cohort_names).sum())}")
    print(f"Matrix counted rows: {int(detail['_is_matrix_candidate'].fillna(False).sum())}")


if __name__ == "__main__":
    main()
