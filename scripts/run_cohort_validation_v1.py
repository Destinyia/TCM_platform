from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd
import xlsxwriter

from analyze_cohort_checkin_matrix import (
    COL_DATE,
    COL_DEVICE_COUNT,
    COL_DUPLICATE,
    COL_FOLDER_NAMES,
    COL_NAME,
    COL_NAME_MISMATCH,
    COL_REMARK,
    COL_SLOT,
    COL_STATUS,
    COL_TABLE_NAMES,
    COL_TIME,
    COL_YST_ASK,
    COL_YST_ASK_PATH,
    COL_YST_PULSE,
    COL_YST_PULSE_PATH,
    COL_YST_TONGUE,
    COL_YST_TONGUE_PATH,
    COL_YST_VISIT_IDS,
    COL_YST_VOICE,
    COL_YST_VOICE_PATH,
    COL_ZK_ASK,
    COL_ZK_ASK_PATH,
    COL_ZK_FACE,
    COL_ZK_FACE_PATH,
    COL_ZK_PULSE,
    COL_ZK_PULSE_PATH,
    COL_ZK_TONGUE,
    COL_ZK_TONGUE_PATH,
    COL_ZK_VISIT_IDS,
    OUTPUT_DIR,
    PLOT_OUTPUT,
    RULE_VERSION,
    SHEET_DETAIL,
    SHEET_MATRIX,
    SHEET_RULES,
    SLOT_LABELS,
    START_DATE,
    WORKBOOK_OUTPUT,
    apply_visit_quality_flags,
    build_date_index,
    build_heatmap_matrix,
    canonicalize_name,
    collect_missing_modalities,
    detect_duplicate_numeric_visits,
    determine_required_modalities,
    ensure_output_dirs,
    load_name_alias_config,
    normalize_name,
    parse_yushengtang_visits,
    parse_zhongke_visits,
    plot_heatmap,
    source_has,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = PROJECT_ROOT / "四诊仪数据整理"
REFERENCE_DIR = DATA_ROOT / "中科四诊仪" / "2025.11.09-2025.12.10"


def discover_local_roots() -> tuple[Path | None, Path | None]:
    zhongke_root = DATA_ROOT / "中科四诊仪"
    yst_root = DATA_ROOT / "玉生堂四诊仪"
    return (zhongke_root if zhongke_root.exists() else None, yst_root if yst_root.exists() else None)


def build_effective_slots(visits: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    gap = pd.Timedelta(minutes=30)
    suspicious_gap = pd.Timedelta(minutes=10)
    grouped = visits.sort_values(["canonical_name", "collected_at", "source_vendor"]).groupby(["canonical_name", "date"], sort=True)
    for (user_name, date_value), day_visits in grouped:
        clusters: list[pd.DataFrame] = []
        current: list[dict[str, object]] = []
        anchor = None
        for record in day_visits.to_dict("records"):
            ts = pd.Timestamp(record["collected_at"])
            if anchor is None or ts - anchor >= gap:
                if current:
                    clusters.append(pd.DataFrame(current))
                current = [record]
                anchor = ts
            else:
                current.append(record)
        if current:
            clusters.append(pd.DataFrame(current))

        accepted = 0
        for cluster_df in clusters:
            selected_rows = []
            for _, vendor_subset in cluster_df.groupby("source_vendor", sort=True):
                vendor_subset = vendor_subset.sort_values(
                    ["is_complete_visit", "modality_score", "duplicate_numeric_flag", "collected_at"],
                    ascending=[False, False, True, True],
                )
                selected_rows.append(vendor_subset.iloc[0])
            selected = pd.DataFrame(selected_rows).sort_values("collected_at").reset_index(drop=True)
            representative = selected.sort_values(["is_complete_visit", "modality_score", "collected_at"], ascending=[False, False, True]).iloc[0]
            status = "complete" if bool(selected["is_complete_visit"].any()) else "incomplete"
            reason = "no_complete_visit_in_slot" if status == "incomplete" else ""
            if bool(selected["duplicate_numeric_flag"].fillna(False).any()):
                status = "suspicious"
                reason = "duplicate_numeric"
            elif int(cluster_df["source_visit_id"].nunique()) >= 3 and (cluster_df["collected_at"].max() - cluster_df["collected_at"].min()) <= suspicious_gap:
                status = "suspicious"
                reason = "triplicate_within_10m"
            if accepted >= len(SLOT_LABELS):
                slot_label = ""
                status = "invalid"
                reason = "overflow_gt_3"
            else:
                slot_label = SLOT_LABELS[accepted]
                accepted += 1
            rows.append(
                {
                    "user_name": user_name,
                    "date": date_value,
                    "cluster_start": pd.Timestamp(representative["collected_at"]),
                    "slot_label": slot_label,
                    "slot_status": status,
                    "reason": reason,
                    "device_count": int(selected["source_vendor"].nunique()),
                    "zhongke_visit_ids": ",".join(selected.loc[selected["source_vendor"] == "zhongke", "source_visit_id"].astype(str).tolist()),
                    "yushengtang_visit_ids": ",".join(selected.loc[selected["source_vendor"] == "yushengtang", "source_visit_id"].astype(str).tolist()),
                    "duplicate_numeric_flag": bool(selected["duplicate_numeric_flag"].fillna(False).any()),
                    "duplicate_numeric_type": ",".join(sorted({str(v) for v in selected["duplicate_numeric_type"].fillna("") if str(v).strip()})),
                    "duplicate_numeric_partner": ",".join(sorted({str(v) for v in selected["duplicate_numeric_partner"].fillna("") if str(v).strip()})),
                    "name_mismatch_flag": bool(selected["name_mismatch_flag"].fillna(False).any()),
                    "alias_mapped_flag": bool(selected["alias_mapped_flag"].fillna(False).any()),
                    "selected_visit_ids": set(selected["source_visit_id"].astype(str).tolist()),
                }
            )
    return pd.DataFrame(rows)


def build_detail_export(day_slots: pd.DataFrame, visits: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for _, slot_row in day_slots.iterrows():
        cluster_visits = visits.loc[
            (visits["canonical_name"] == slot_row["user_name"])
            & (visits["date"] == slot_row["date"])
            & (visits["source_visit_id"].astype(str).isin(slot_row["selected_visit_ids"]))
        ].copy()
        folder_names = sorted({str(v).strip() for v in cluster_visits["folder_name"] if str(v).strip()})
        table_names = sorted({str(v).strip() for v in cluster_visits["raw_user_name"] if str(v).strip()})
        remark_parts = []
        if bool(slot_row.get("alias_mapped_flag", False)):
            remark_parts.append("姓名别名已归一")
        if bool(slot_row.get("name_mismatch_flag", False)):
            remark_parts.append(f"姓名不一致：文件夹姓名={','.join(folder_names)}；表格姓名={','.join(table_names)}")
        if slot_row["reason"] == "triplicate_within_10m":
            remark_parts.append("疑似作弊：10分钟内连续多次打卡")
        elif slot_row["reason"] == "duplicate_numeric":
            remark_parts.append("疑似重复：数值重复或高度相似")
        elif slot_row["reason"] == "overflow_gt_3":
            remark_parts.append("无效：超出早中晚三次上限")
        if slot_row["slot_status"] == "incomplete":
            remark_parts.append("不完整")
        missing = collect_missing_modalities(cluster_visits)
        if missing:
            remark_parts.append(f"缺少模态：{','.join(missing)}")
        rows.append(
            {
                COL_NAME: slot_row["user_name"],
                COL_DATE: pd.Timestamp(slot_row["date"]).normalize(),
                COL_TIME: pd.Timestamp(slot_row["cluster_start"]).strftime("%H:%M:%S"),
                COL_SLOT: slot_row["slot_label"] or "",
                COL_STATUS: slot_row["slot_status"],
                COL_REMARK: "；".join(remark_parts),
                COL_FOLDER_NAMES: ",".join(folder_names),
                COL_TABLE_NAMES: ",".join(table_names),
                COL_DUPLICATE: "1" if bool(slot_row.get("duplicate_numeric_flag", False)) else "",
                COL_NAME_MISMATCH: "1" if bool(slot_row.get("name_mismatch_flag", False)) else "",
                COL_DEVICE_COUNT: int(slot_row.get("device_count", 0) or 0),
                COL_ZK_VISIT_IDS: slot_row.get("zhongke_visit_ids", ""),
                COL_YST_VISIT_IDS: slot_row.get("yushengtang_visit_ids", ""),
                COL_ZK_ASK: "1" if source_has(cluster_visits, "zhongke", "ask") else "",
                COL_ZK_PULSE: "1" if source_has(cluster_visits, "zhongke", "pulse") else "",
                COL_ZK_TONGUE: "1" if source_has(cluster_visits, "zhongke", "tongue") else "",
                COL_ZK_FACE: "1" if source_has(cluster_visits, "zhongke", "face") else "",
                COL_YST_ASK: "1" if source_has(cluster_visits, "yushengtang", "ask") else "",
                COL_YST_PULSE: "1" if source_has(cluster_visits, "yushengtang", "pulse") else "",
                COL_YST_TONGUE: "1" if source_has(cluster_visits, "yushengtang", "tongue") else "",
                COL_YST_VOICE: "1" if source_has(cluster_visits, "yushengtang", "voice") else "",
                COL_ZK_ASK_PATH: cluster_visits.loc[(cluster_visits["source_vendor"] == "zhongke") & cluster_visits["ask"], "path_ask"].astype(str).head(1).tolist()[0] if source_has(cluster_visits, "zhongke", "ask") else "",
                COL_ZK_PULSE_PATH: cluster_visits.loc[(cluster_visits["source_vendor"] == "zhongke") & cluster_visits["pulse"], "path_pulse"].astype(str).head(1).tolist()[0] if source_has(cluster_visits, "zhongke", "pulse") else "",
                COL_ZK_TONGUE_PATH: cluster_visits.loc[(cluster_visits["source_vendor"] == "zhongke") & cluster_visits["tongue"], "path_tongue"].astype(str).head(1).tolist()[0] if source_has(cluster_visits, "zhongke", "tongue") else "",
                COL_ZK_FACE_PATH: cluster_visits.loc[(cluster_visits["source_vendor"] == "zhongke") & cluster_visits["face"], "path_face"].astype(str).head(1).tolist()[0] if source_has(cluster_visits, "zhongke", "face") else "",
                COL_YST_ASK_PATH: cluster_visits.loc[(cluster_visits["source_vendor"] == "yushengtang") & cluster_visits["ask"], "path_ask"].astype(str).head(1).tolist()[0] if source_has(cluster_visits, "yushengtang", "ask") else "",
                COL_YST_PULSE_PATH: cluster_visits.loc[(cluster_visits["source_vendor"] == "yushengtang") & cluster_visits["pulse"], "path_pulse"].astype(str).head(1).tolist()[0] if source_has(cluster_visits, "yushengtang", "pulse") else "",
                COL_YST_TONGUE_PATH: cluster_visits.loc[(cluster_visits["source_vendor"] == "yushengtang") & cluster_visits["tongue"], "path_tongue"].astype(str).head(1).tolist()[0] if source_has(cluster_visits, "yushengtang", "tongue") else "",
                COL_YST_VOICE_PATH: cluster_visits.loc[(cluster_visits["source_vendor"] == "yushengtang") & cluster_visits["voice"], "path_voice"].astype(str).head(1).tolist()[0] if source_has(cluster_visits, "yushengtang", "voice") else "",
                "_fill_red": bool(slot_row.get("duplicate_numeric_flag", False) or slot_row.get("name_mismatch_flag", False) or slot_row["slot_status"] == "suspicious"),
            }
        )
    return pd.DataFrame(rows).sort_values([COL_NAME, COL_DATE, COL_TIME, COL_SLOT]).reset_index(drop=True)


def write_workbook(date_index: pd.DatetimeIndex, detail_df: pd.DataFrame, matrix: pd.DataFrame) -> None:
    with pd.ExcelWriter(WORKBOOK_OUTPUT, engine="xlsxwriter", datetime_format="yyyy-mm-dd") as writer:
        workbook: xlsxwriter.Workbook = writer.book
        matrix_sheet = workbook.add_worksheet(SHEET_MATRIX)
        detail_sheet = workbook.add_worksheet(SHEET_DETAIL)
        rules_sheet = workbook.add_worksheet(SHEET_RULES)
        writer.sheets[SHEET_MATRIX] = matrix_sheet
        writer.sheets[SHEET_DETAIL] = detail_sheet
        writer.sheets[SHEET_RULES] = rules_sheet
        header = workbook.add_format({"bold": True, "bg_color": "#D9EAF7", "border": 1, "align": "center"})
        row_label = workbook.add_format({"bold": True, "border": 1})
        blank = workbook.add_format({"border": 1, "align": "center"})
        green = workbook.add_format({"border": 1, "align": "center", "bg_color": "#C6EFCE", "font_color": "#0563C1", "underline": 1})
        yellow = workbook.add_format({"border": 1, "align": "center", "bg_color": "#FFEB9C", "font_color": "#0563C1", "underline": 1})
        orange = workbook.add_format({"border": 1, "align": "center", "bg_color": "#F4B183", "font_color": "#0563C1", "underline": 1})
        red = workbook.add_format({"border": 1, "align": "center", "bg_color": "#FFC7CE", "font_color": "#0563C1", "underline": 1})
        detail = workbook.add_format({"border": 1, "valign": "top"})
        detail_red = workbook.add_format({"border": 1, "valign": "top", "bg_color": "#FFC7CE"})

        matrix_dates = [day.strftime("%Y-%m-%d") for day in date_index]
        matrix_sheet.write(0, 0, "用户时段", header)
        for col_idx, date_label in enumerate(matrix_dates, start=1):
            matrix_sheet.write(0, col_idx, date_label, header)

        detail_columns = [column for column in detail_df.columns if column != "_fill_red"]
        for col_idx, column in enumerate(detail_columns):
            detail_sheet.write(0, col_idx, column, header)
        for row_idx, row in detail_df.iterrows():
            fmt = detail_red if bool(row["_fill_red"]) else detail
            for col_idx, column in enumerate(detail_columns):
                detail_sheet.write(row_idx + 1, col_idx, row[column], fmt)

        status_by_key = {}
        detail_row_by_key = {}
        priority = {"suspicious": 4, "invalid": 3, "incomplete": 2, "complete": 1}
        for row_idx, row in detail_df.iterrows():
            key = (str(row[COL_NAME]), str(row[COL_SLOT]), pd.Timestamp(row[COL_DATE]).strftime("%Y-%m-%d"))
            detail_row_by_key.setdefault(key, row_idx + 2)
            if key not in status_by_key or priority.get(str(row[COL_STATUS]), 0) > priority.get(status_by_key[key], 0):
                status_by_key[key] = str(row[COL_STATUS])
        for row_idx, row_label_text in enumerate(matrix.index, start=1):
            matrix_sheet.write(row_idx, 0, row_label_text, row_label)
            user_name, slot_label = row_label_text.rsplit("-", 1)
            for col_idx, date_label in enumerate(matrix_dates, start=1):
                key = (user_name, slot_label, date_label)
                status = status_by_key.get(key)
                if not status:
                    matrix_sheet.write_blank(row_idx, col_idx, None, blank)
                    continue
                fmt = {"complete": green, "incomplete": yellow, "invalid": orange, "suspicious": red}.get(status, blank)
                matrix_sheet.write_url(row_idx, col_idx, f"internal:'{SHEET_DETAIL}'!A{detail_row_by_key[key]}", fmt, string="1")

        rules = [
            ("rule_version", RULE_VERSION),
            ("visit_merge", "同一用户同一天内，间隔30分钟以内的记录视为同一候选时段"),
            ("slot_definition", "早/中/晚 = 当天第1/2/3次有效采集"),
            ("cross_device_merge", "同日同槽位的中科/玉生堂记录合并为一个visit的不同模态"),
            ("overlap_resolution", "时间重叠时取模态最完整的一次作为有效代表"),
        ]
        for row_idx, (key, value) in enumerate(rules):
            rules_sheet.write(row_idx, 0, key, row_label)
            rules_sheet.write(row_idx, 1, value, detail)


def main() -> None:
    ensure_output_dirs()
    alias_map = load_name_alias_config()
    zhongke_root, yst_root = discover_local_roots()
    cohort_names = sorted(path.name for path in REFERENCE_DIR.iterdir() if path.is_dir())
    alias_map.update({normalize_name(name): name for name in cohort_names})

    visits_frames = []
    if zhongke_root is not None:
        zhongke_visits = parse_zhongke_visits(zhongke_root)
        if not zhongke_visits.empty:
            visits_frames.append(zhongke_visits)
    if yst_root is not None:
        yst_visits = parse_yushengtang_visits(yst_root)
        if not yst_visits.empty:
            visits_frames.append(yst_visits)
    visits = pd.concat(visits_frames, ignore_index=True, sort=False)
    if "raw_user_name" not in visits.columns and "user_name" in visits.columns:
        visits["raw_user_name"] = visits["user_name"]
    for column in ["ask", "pulse", "tongue", "face", "voice"]:
        if column not in visits.columns:
            visits[column] = False
        visits[column] = visits[column].fillna(False).astype(bool)
        path_col = f"path_{column}"
        if path_col not in visits.columns:
            visits[path_col] = ""
        visits[path_col] = visits[path_col].fillna("").astype(str)

    visits["canonical_name"] = visits["raw_user_name"].apply(lambda value: canonicalize_name(value, alias_map))
    visits["alias_mapped_flag"] = visits.apply(lambda row: normalize_name(row["raw_user_name"]) in alias_map and str(row["canonical_name"]).strip() != str(row["raw_user_name"]).strip(), axis=1)
    visits["name_mismatch_flag"] = visits.apply(lambda row: bool(str(row.get("folder_name", "")).strip()) and normalize_name(row.get("folder_name", "")) != normalize_name(row.get("canonical_name", "")), axis=1)
    visits["collected_at"] = pd.to_datetime(visits["collected_at"])
    visits = visits.loc[visits["canonical_name"].astype(str).isin(cohort_names)].copy()
    visits = visits.loc[visits["collected_at"] >= START_DATE].copy()
    modality_rules = determine_required_modalities(visits)
    visits = apply_visit_quality_flags(visits, modality_rules)
    if "modality_score" not in visits.columns:
        visits["modality_score"] = visits[["ask", "pulse", "tongue", "face", "voice"]].fillna(False).astype(bool).sum(axis=1)
    visits = detect_duplicate_numeric_visits(visits, zhongke_root)
    day_slots = build_effective_slots(visits)
    detail_df = build_detail_export(day_slots, visits)
    date_index = build_date_index(visits)
    matrix = build_heatmap_matrix(day_slots, cohort_names, date_index)
    write_workbook(date_index, detail_df, matrix)
    plot_heatmap(matrix)
    print(f"Workbook: {WORKBOOK_OUTPUT}")
    print(f"Heatmap: {PLOT_OUTPUT}")
    print(f"RuleVersion: {RULE_VERSION}")
    print(f"DetailRows: {len(detail_df)}")


if __name__ == "__main__":
    main()
