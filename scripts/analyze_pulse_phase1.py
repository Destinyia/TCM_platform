from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


QUALITY_FEATURES = ["stability_score"]
CORE_FEATURES = ["pulse_rate", "force", "tension", "fluency", "amplitude", "h1", "h3", "w", "as", "ad", "stability_score"]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_table(dataset_dir: Path, stem: str) -> pd.DataFrame:
    parquet_path = dataset_dir / f"{stem}.parquet"
    csv_path = dataset_dir / f"{stem}.csv"
    jsonl_path = dataset_dir / f"{stem}.jsonl"
    if parquet_path.exists():
        try:
            return pd.read_parquet(parquet_path)
        except Exception:
            pass
    if csv_path.exists():
        return pd.read_csv(csv_path)
    rows = read_jsonl(jsonl_path)
    return pd.DataFrame(rows)


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def load_feature_matrix(dataset_dir: Path) -> pd.DataFrame:
    measurements = read_table(dataset_dir, "measurements")
    features = read_table(dataset_dir, "measurement_features")
    if measurements.empty:
        return pd.DataFrame()
    if features.empty:
        return measurements.copy()

    features = features.copy()
    features["feature_value"] = pd.to_numeric(features["feature_value"], errors="coerce")
    wide = features.pivot_table(index="measurement_id", columns="feature_name", values="feature_value", aggfunc="mean").reset_index()
    merged = measurements.merge(wide, on="measurement_id", how="left")
    for column in CORE_FEATURES:
        if column not in merged.columns:
            merged[column] = pd.NA
    return merged


def waveform_metrics(dataset_dir: Path) -> pd.DataFrame:
    rows = read_jsonl(dataset_dir / "waveform_manifest.jsonl")
    result = []
    for row in rows:
        preview = row.get("preview_json")
        if isinstance(preview, str):
            try:
                preview = json.loads(preview)
            except json.JSONDecodeError:
                preview = []
        preview = preview or []
        y_values = [safe_float(point.get("y")) for point in preview if isinstance(point, dict)]
        y_values = [value for value in y_values if value is not None]
        if len(y_values) >= 2:
            drift_slope = (y_values[-1] - y_values[0]) / max(1, len(y_values) - 1)
            amplitude_range = max(y_values) - min(y_values)
            baseline_instability = abs(drift_slope) / amplitude_range if amplitude_range else 0.0
            artifact_ratio = sum(1 for value in y_values if value == max(y_values) or value == min(y_values)) / len(y_values)
        else:
            drift_slope = 0.0
            baseline_instability = 1.0
            artifact_ratio = 1.0
        result.append(
            {
                "measurement_id": row.get("measurement_id"),
                "waveform_channel_count": 1,
                "baseline_drift_slope": drift_slope,
                "baseline_instability": baseline_instability,
                "artifact_ratio_from_preview": artifact_ratio,
                "has_waveform_preview": bool(y_values),
            }
        )
    if not result:
        return pd.DataFrame(columns=["measurement_id", "waveform_channel_count", "baseline_drift_slope", "baseline_instability", "artifact_ratio_from_preview", "has_waveform_preview"])
    frame = pd.DataFrame(result)
    return frame.groupby("measurement_id", as_index=False).agg(
        {
            "waveform_channel_count": "sum",
            "baseline_drift_slope": "mean",
            "baseline_instability": "mean",
            "artifact_ratio_from_preview": "mean",
            "has_waveform_preview": "max",
        }
    )


def analyze_measurement_quality(feature_matrix: pd.DataFrame, waveform_frame: pd.DataFrame) -> pd.DataFrame:
    if feature_matrix.empty:
        return pd.DataFrame()
    frame = feature_matrix.merge(waveform_frame, on="measurement_id", how="left")
    frame["stability_score"] = pd.to_numeric(frame["stability_score"], errors="coerce")
    frame["amplitude"] = pd.to_numeric(frame["amplitude"], errors="coerce")
    frame["duration_seconds"] = pd.to_numeric(frame["duration_seconds"], errors="coerce").fillna(0)
    frame["baseline_instability"] = pd.to_numeric(frame["baseline_instability"], errors="coerce").fillna(1.0)
    frame["artifact_ratio_from_preview"] = pd.to_numeric(frame["artifact_ratio_from_preview"], errors="coerce").fillna(1.0)
    frame["has_waveform_preview"] = frame["has_waveform_preview"].fillna(False)

    stability_component = frame["stability_score"].fillna(50).clip(0, 100)
    drift_penalty = (frame["baseline_instability"].clip(0, 1) * 35).fillna(35)
    artifact_penalty = (frame["artifact_ratio_from_preview"].clip(0, 1) * 15).fillna(15)
    waveform_bonus = frame["has_waveform_preview"].map(lambda value: 5 if bool(value) else -10)

    signal_quality = (stability_component - drift_penalty - artifact_penalty + waveform_bonus).map(lambda value: clamp(float(value)))
    drift_index = (frame["baseline_instability"].clip(0, 1) * 70 + (100 - stability_component) * 0.3).map(lambda value: clamp(float(value)))
    stable_segment_ratio = (stability_component / 100 - frame["baseline_instability"].clip(0, 1) * 0.25).clip(0, 1)
    best_duration = (frame["duration_seconds"] * stable_segment_ratio).clip(lower=0)

    labels = []
    reasons = []
    for quality, duration, ratio in zip(signal_quality, best_duration, stable_segment_ratio):
        if quality >= 75 and duration >= 20 and ratio >= 0.5:
            labels.append("valid")
            reasons.append("")
        elif quality >= 60 and duration >= 10:
            labels.append("partial_valid")
            reasons.append("stable segment is short or quality is moderate")
        else:
            labels.append("invalid")
            reasons.append("insufficient stable high-quality segment")

    result = pd.DataFrame(
        {
            "measurement_id": frame["measurement_id"],
            "user_id": frame.get("user_id"),
            "source_vendor": frame.get("source_vendor"),
            "device_id": frame.get("device_id"),
            "visit_slot": frame.get("visit_slot"),
            "signal_quality_score": signal_quality.round(3),
            "drift_severity_index": drift_index.round(3),
            "baseline_drift_slope": frame["baseline_drift_slope"].fillna(0).round(6),
            "artifact_ratio": frame["artifact_ratio_from_preview"].round(3),
            "stable_segment_ratio": stable_segment_ratio.round(3),
            "best_segment_start_time": ((frame["duration_seconds"] - best_duration) / 2).clip(lower=0).round(3),
            "best_segment_end_time": (((frame["duration_seconds"] - best_duration) / 2) + best_duration).clip(lower=0).round(3),
            "best_segment_duration": best_duration.round(3),
            "best_segment_quality_score": signal_quality.round(3),
            "measurement_validity_label": labels,
            "invalid_segment_reason": reasons,
        }
    )
    return result


def coefficient_of_variation(values: pd.Series) -> float | None:
    values = pd.to_numeric(values, errors="coerce").dropna()
    if len(values) < 2:
        return None
    mean = values.mean()
    if mean == 0 or math.isnan(mean):
        return None
    return float(values.std(ddof=1) / abs(mean))


def simple_icc(values: pd.Series, groups: pd.Series) -> float | None:
    data = pd.DataFrame({"value": pd.to_numeric(values, errors="coerce"), "group": groups}).dropna()
    if data["group"].nunique() < 2 or len(data) < 3:
        return None
    grand_mean = data["value"].mean()
    group_means = data.groupby("group")["value"].mean()
    counts = data.groupby("group")["value"].count()
    between = float(((group_means - grand_mean) ** 2 * counts).sum() / max(1, len(group_means) - 1))
    within = float(data.groupby("group")["value"].var(ddof=1).fillna(0).mul(counts - 1).sum() / max(1, len(data) - len(group_means)))
    denominator = between + within
    if denominator <= 0:
        return None
    return between / denominator


def analyze_feature_reliability(feature_matrix: pd.DataFrame, quality: pd.DataFrame) -> pd.DataFrame:
    if feature_matrix.empty:
        return pd.DataFrame()
    frame = feature_matrix.merge(quality[["measurement_id", "drift_severity_index", "signal_quality_score"]], on="measurement_id", how="left")
    rows = []
    for feature in CORE_FEATURES:
        if feature not in frame.columns:
            continue
        values = pd.to_numeric(frame[feature], errors="coerce")
        present = values.notna()
        missing_rate = 1 - present.mean() if len(values) else 1
        if present.sum() >= 4:
            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                outlier_rate = 0.0
            else:
                outlier_rate = ((values < q1 - 1.5 * iqr) | (values > q3 + 1.5 * iqr)).mean()
        else:
            outlier_rate = 0.0

        within_cv = coefficient_of_variation(values)
        within_icc = simple_icc(values, frame["user_id"]) if "user_id" in frame else None

        if frame["device_id"].nunique(dropna=True) >= 2:
            device_values = pd.DataFrame({"device_id": frame["device_id"], "value": values})
            device_means = device_values.groupby("device_id")["value"].mean().dropna()
            device_sensitivity = float(device_means.std(ddof=0) / abs(device_means.mean())) if len(device_means) >= 2 and device_means.mean() else None
        else:
            device_sensitivity = None

        drift = pd.to_numeric(frame["drift_severity_index"], errors="coerce")
        drift_sensitivity = abs(values.corr(drift)) if values.notna().sum() >= 3 and drift.notna().sum() >= 3 else None
        quality_dependency = abs(values.corr(pd.to_numeric(frame["signal_quality_score"], errors="coerce"))) if values.notna().sum() >= 3 else None

        risk = 0.0
        risk += missing_rate * 35
        risk += outlier_rate * 20
        risk += min(1.0, within_cv or 0.0) * 20
        risk += min(1.0, device_sensitivity or 0.0) * 15
        risk += min(1.0, drift_sensitivity or 0.0) * 10
        if risk <= 20:
            grade = "A"
        elif risk <= 40:
            grade = "B"
        elif risk <= 65:
            grade = "C"
        else:
            grade = "D"

        rows.append(
            {
                "feature_name": feature,
                "missing_rate": round(float(missing_rate), 4),
                "outlier_rate": round(float(outlier_rate), 4),
                "within_session_cv": round(within_cv, 4) if within_cv is not None else None,
                "within_session_icc": round(within_icc, 4) if within_icc is not None else None,
                "device_sensitivity": round(device_sensitivity, 4) if device_sensitivity is not None else None,
                "drift_sensitivity": round(float(drift_sensitivity), 4) if drift_sensitivity is not None and not math.isnan(drift_sensitivity) else None,
                "quality_dependency_score": round(float(quality_dependency), 4) if quality_dependency is not None and not math.isnan(quality_dependency) else None,
                "feature_reliability_grade": grade,
                "risk_score": round(risk, 3),
            }
        )
    return pd.DataFrame(rows)


def analyze_device_consistency(feature_matrix: pd.DataFrame, quality: pd.DataFrame, near_minutes: int) -> pd.DataFrame:
    if feature_matrix.empty or "device_id" not in feature_matrix:
        return pd.DataFrame()
    frame = feature_matrix.merge(quality[["measurement_id", "measurement_validity_label"]], on="measurement_id", how="left")
    frame = frame[frame["measurement_validity_label"].isin(["valid", "partial_valid"])].copy()
    if frame["device_id"].nunique(dropna=True) < 2:
        return pd.DataFrame()
    frame["start_time_dt"] = pd.to_datetime(frame["start_time"], errors="coerce")
    rows = []
    for feature in CORE_FEATURES:
        if feature not in frame.columns:
            continue
        pairs = []
        for user_id, group in frame.dropna(subset=["start_time_dt", "device_id"]).groupby("user_id"):
            group = group.sort_values("start_time_dt")
            for left_index, left in group.iterrows():
                candidates = group[(group["device_id"] != left["device_id"]) & ((group["start_time_dt"] - left["start_time_dt"]).abs().dt.total_seconds() <= near_minutes * 60)]
                for _, right in candidates.iterrows():
                    left_value = safe_float(left.get(feature))
                    right_value = safe_float(right.get(feature))
                    if left_value is None or right_value is None:
                        continue
                    pairs.append((user_id, left["device_id"], right["device_id"], left_value, right_value))
        if not pairs:
            continue
        diffs = [right - left for _, _, _, left, right in pairs]
        means = [(right + left) / 2 for _, _, _, left, right in pairs]
        mean_diff = sum(diffs) / len(diffs)
        sd_diff = pd.Series(diffs).std(ddof=1) if len(diffs) > 1 else 0.0
        relative_bias = mean_diff / (sum(means) / len(means)) if means and sum(means) else None
        rows.append(
            {
                "feature_name": feature,
                "pair_count": len(pairs),
                "device_bias": round(mean_diff, 6),
                "device_relative_bias": round(relative_bias, 6) if relative_bias is not None else None,
                "bland_altman_mean_diff": round(mean_diff, 6),
                "bland_altman_loa_upper": round(mean_diff + 1.96 * sd_diff, 6),
                "bland_altman_loa_lower": round(mean_diff - 1.96 * sd_diff, 6),
                "device_merge_policy": "A" if abs(relative_bias or 0) <= 0.05 else "B" if abs(relative_bias or 0) <= 0.15 else "C",
            }
        )
    return pd.DataFrame(rows)


def write_outputs(output_dir: Path, frames: dict[str, pd.DataFrame], summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False, encoding="utf-8-sig")
        try:
            frame.to_parquet(output_dir / f"{name}.parquet", index=False)
        except Exception:
            pass
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(render_report(summary, frames), encoding="utf-8")


def render_report(summary: dict[str, Any], frames: dict[str, pd.DataFrame]) -> str:
    quality = frames.get("measurement_quality", pd.DataFrame())
    reliability = frames.get("feature_reliability", pd.DataFrame())
    lines = [
        "# Pulse Phase 1 Analysis Report",
        "",
        f"Generated at: {summary['created_at']}",
        "",
        "## Dataset",
        "",
        f"- dataset_dir: `{summary['dataset_dir']}`",
        f"- measurements: {summary['measurement_count']}",
        f"- valid measurements: {summary['valid_measurement_count']}",
        f"- partial valid measurements: {summary['partial_valid_measurement_count']}",
        f"- invalid measurements: {summary['invalid_measurement_count']}",
        "",
        "## Feature Reliability",
        "",
    ]
    if reliability.empty:
        lines.append("No feature reliability rows were produced.")
    else:
        for grade, count in reliability["feature_reliability_grade"].value_counts().sort_index().items():
            lines.append(f"- grade {grade}: {count}")
    lines.extend(["", "## Quality Notes", ""])
    if quality.empty:
        lines.append("No measurement quality rows were produced.")
    else:
        avg_quality = quality["signal_quality_score"].mean()
        avg_drift = quality["drift_severity_index"].mean()
        lines.append(f"- average signal quality score: {avg_quality:.2f}")
        lines.append(f"- average drift severity index: {avg_drift:.2f}")
    return "\n".join(lines) + "\n"


def analyze(dataset_dir: Path, output_dir: Path, near_minutes: int) -> None:
    feature_matrix = load_feature_matrix(dataset_dir)
    waveform_frame = waveform_metrics(dataset_dir)
    quality = analyze_measurement_quality(feature_matrix, waveform_frame)
    reliability = analyze_feature_reliability(feature_matrix, quality)
    device = analyze_device_consistency(feature_matrix, quality, near_minutes)
    summary = {
        "dataset_dir": str(dataset_dir),
        "output_dir": str(output_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "measurement_count": int(len(feature_matrix)),
        "valid_measurement_count": int((quality["measurement_validity_label"] == "valid").sum()) if not quality.empty else 0,
        "partial_valid_measurement_count": int((quality["measurement_validity_label"] == "partial_valid").sum()) if not quality.empty else 0,
        "invalid_measurement_count": int((quality["measurement_validity_label"] == "invalid").sum()) if not quality.empty else 0,
        "feature_count": int(len(reliability)),
        "device_consistency_feature_count": int(len(device)),
        "near_time_pair_window_minutes": near_minutes,
    }
    write_outputs(
        output_dir,
        {
            "measurement_quality": quality,
            "feature_reliability": reliability,
            "device_consistency": device,
        },
        summary,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pulse phase 1 reliability analysis from an exported dataset directory.")
    parser.add_argument("--dataset-dir", required=True, help="Directory containing manifest.jsonl and exported pulse tables.")
    parser.add_argument("--output-dir", help="Analysis output directory. Defaults to dataset-dir/analysis/phase1.")
    parser.add_argument("--near-minutes", type=int, default=30, help="Near-time pairing window for cross-device analysis.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_dir = Path(args.dataset_dir)
    output_dir = Path(args.output_dir) if args.output_dir else dataset_dir / "analysis" / "phase1"
    analyze(dataset_dir, output_dir, args.near_minutes)
    print(f"Wrote pulse phase 1 analysis: {output_dir}")


if __name__ == "__main__":
    main()
