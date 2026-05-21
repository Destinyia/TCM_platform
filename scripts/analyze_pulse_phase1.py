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
CHANNEL_ORDER = ["cun", "guan", "chi"]


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


def parse_json_value(value: Any, default: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return value if value is not None else default


def extract_preview_values(row: dict[str, Any]) -> list[float]:
    preview = parse_json_value(row.get("preview_json"), [])
    if isinstance(preview, dict) and isinstance(preview.get("points"), list):
        raw_values = preview["points"]
    elif isinstance(preview, list):
        raw_values = preview
    else:
        raw_values = []

    y_values = []
    for point in raw_values:
        if isinstance(point, dict):
            y_values.append(safe_float(point.get("y")))
        else:
            y_values.append(safe_float(point))
    return [value for value in y_values if value is not None]


def standard_channel_name(channel_name: Any) -> str:
    value = str(channel_name or "").strip().lower()
    if value in {"cun", "寸"}:
        return "cun"
    if value in {"guan", "guanmai", "guan_mai", "关", "關"}:
        return "guan"
    if value in {"chi", "尺"}:
        return "chi"
    if value in {"singlepluse", "singlepulse", "single_pulse", "overall"}:
        return "overall"
    return value or "unknown"


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * ratio
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def mean_std(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(max(0.0, variance))


def variance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0, ys[0] if ys else 0.0
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return 0.0, y_mean
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    intercept = y_mean - slope * x_mean
    return slope, intercept


def linear_detrend(values: list[float]) -> list[float]:
    if len(values) < 2:
        return values[:]
    n = len(values)
    slope, intercept = linear_regression([float(index) for index in range(n)], values)
    return [value - (intercept + slope * index) for index, value in enumerate(values)]


def autocorrelation_peak(values: list[float]) -> tuple[float, int | None]:
    if len(values) < 16:
        return 0.0, None
    _, value_std = mean_std(values)
    if not value_std:
        return 0.0, None
    centered = [value - (sum(values) / len(values)) for value in values]
    denominator = sum(value * value for value in centered)
    if denominator <= 0:
        return 0.0, None

    max_lag = min(28, max(3, len(values) // 2))
    best_corr = 0.0
    best_lag = None
    for lag in range(3, max_lag + 1):
        numerator = sum(centered[index] * centered[index - lag] for index in range(lag, len(centered)))
        corr = numerator / denominator
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    return best_corr, best_lag


def autocorrelation_peak_for_lag_range(values: list[float], min_lag: int, max_lag: int) -> tuple[float, int | None]:
    if len(values) < 16:
        return 0.0, None
    mean = sum(values) / len(values)
    centered = [value - mean for value in values]
    denominator = sum(value * value for value in centered)
    if denominator <= 0:
        return 0.0, None

    min_lag = max(2, min_lag)
    max_lag = min(max_lag, max(2, len(values) // 2))
    if max_lag < min_lag:
        return 0.0, None

    best_corr = 0.0
    best_lag = None
    for lag in range(min_lag, max_lag + 1):
        numerator = sum(centered[index] * centered[index - lag] for index in range(lag, len(centered)))
        corr = numerator / denominator
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    return best_corr, best_lag


def preview_seconds_per_point(duration_seconds: float | None, point_count: int) -> float | None:
    if duration_seconds is None or duration_seconds <= 0 or point_count < 2:
        return None
    return duration_seconds / (point_count - 1)


def pulse_lag_range(point_count: int, duration_seconds: float | None) -> tuple[int, int]:
    seconds_per_point = preview_seconds_per_point(duration_seconds, point_count)
    if seconds_per_point:
        min_lag = math.floor((60 / 180) / seconds_per_point)
        max_lag = math.ceil((60 / 40) / seconds_per_point)
        return max(2, min_lag), min(max(2, point_count // 2), max_lag)
    return 3, min(28, max(3, point_count // 2))


def detect_preview_peaks(values: list[float]) -> list[int]:
    if len(values) < 5:
        return []
    detrended = linear_detrend(values)
    mean, std = mean_std(detrended)
    threshold = (mean or 0.0) + (std or 0.0) * 0.25
    peaks = []
    for index in range(1, len(detrended) - 1):
        if detrended[index] >= detrended[index - 1] and detrended[index] > detrended[index + 1] and detrended[index] >= threshold:
            peaks.append(index)
    return peaks


def period_consistency_from_peaks(peaks: list[int]) -> float | None:
    if len(peaks) < 3:
        return None
    intervals = [peaks[index] - peaks[index - 1] for index in range(1, len(peaks))]
    interval_mean, interval_std = mean_std([float(value) for value in intervals])
    if not interval_mean:
        return None
    return clamp(1 - ((interval_std or 0.0) / interval_mean), 0, 1)


def build_periodic_template(values: list[float], lag: int | None) -> tuple[list[float], list[float], list[float]]:
    if not lag or lag < 2 or len(values) < lag * 2:
        return [], [], values[:]

    phase_values: list[list[float]] = [[] for _ in range(lag)]
    for index, value in enumerate(values):
        phase_values[index % lag].append(value)
    template = []
    for bucket in phase_values:
        template.append(sum(bucket) / len(bucket) if bucket else 0.0)
    repeated = [template[index % lag] for index in range(len(values))]
    residual = [value - predicted for value, predicted in zip(values, repeated)]
    return template, repeated, residual


def normalize_vector(values: list[float]) -> list[float]:
    if not values:
        return []
    mean, std = mean_std(values)
    if not std:
        return [0.0 for _ in values]
    return [(value - (mean or 0.0)) / std for value in values]


def round_vector(values: list[float], places: int = 6) -> list[float]:
    return [round(float(value), places) for value in values]


def dfa_alpha(values: list[float]) -> tuple[float | None, float | None]:
    if len(values) < 16:
        return None, None
    mean = sum(values) / len(values)
    integrated = []
    total = 0.0
    for value in values:
        total += value - mean
        integrated.append(total)

    scales = [4, 8, 16, 32]
    fluctuations = []
    for scale in scales:
        if scale * 2 > len(integrated):
            continue
        segment_fluctuations = []
        for start in range(0, len(integrated) - scale + 1, scale):
            segment = integrated[start : start + scale]
            xs = [float(index) for index in range(scale)]
            slope, intercept = linear_regression(xs, segment)
            residuals = [value - (intercept + slope * index) for index, value in enumerate(segment)]
            rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
            if rms > 0:
                segment_fluctuations.append(rms)
        if segment_fluctuations:
            fluctuations.append((scale, sum(segment_fluctuations) / len(segment_fluctuations)))
    if len(fluctuations) < 2:
        return None, None

    log_scales = [math.log(scale) for scale, _ in fluctuations]
    log_fluctuations = [math.log(fluctuation) for _, fluctuation in fluctuations if fluctuation > 0]
    if len(log_scales) != len(log_fluctuations) or len(log_fluctuations) < 2:
        return None, None
    slope, _ = linear_regression(log_scales, log_fluctuations)
    return slope, slope


def decompose_preview_signal(values: list[float], duration_seconds: float | None = None) -> dict[str, Any]:
    if len(values) < 16:
        return {
            "preview_point_count": len(values),
            "dominant_lag_preview_points": None,
            "template_vector": [],
            "normalized_template_vector": [],
            "residual_vector": [],
        }

    trend_slope, trend_intercept = linear_regression([float(index) for index in range(len(values))], values)
    detrended = [value - (trend_intercept + trend_slope * index) for index, value in enumerate(values)]
    min_lag, max_lag = pulse_lag_range(len(values), duration_seconds)
    template_coherence, dominant_lag = autocorrelation_peak_for_lag_range(detrended, min_lag, max_lag)
    if dominant_lag is None:
        template_coherence, dominant_lag = autocorrelation_peak(detrended)

    template, repeated, residual = build_periodic_template(detrended, dominant_lag)
    detrended_variance = variance(detrended) or 0.0
    residual_variance = variance(residual) or 0.0
    template_variance = variance(repeated) or 0.0
    explained_ratio = clamp(1 - (residual_variance / detrended_variance), 0, 1) if detrended_variance else 0.0
    periodic_snr = template_variance / (residual_variance + 1e-9)
    pulse_energy = template_variance
    residual_energy_ratio = residual_variance / (detrended_variance + 1e-9) if detrended_variance else 1.0
    residual_mean, residual_std = mean_std(residual)
    detrended_mean, detrended_std = mean_std(detrended)
    p05 = percentile(values, 0.05) or min(values)
    p95 = percentile(values, 0.95) or max(values)
    amplitude_range = max(0.0, p95 - p05)
    residual_fluctuation = (residual_std or 0.0) / (amplitude_range + 1e-9) if amplitude_range else 1.0

    peaks = detect_preview_peaks(values)
    peak_consistency = period_consistency_from_peaks(peaks)
    if peak_consistency is None:
        peak_consistency = template_coherence

    seconds_per_point = preview_seconds_per_point(duration_seconds, len(values))
    estimated_period_seconds = dominant_lag * seconds_per_point if dominant_lag and seconds_per_point else None
    estimated_pulse_rate_bpm = 60 / estimated_period_seconds if estimated_period_seconds and estimated_period_seconds > 0 else None
    pulse_count_estimate = duration_seconds / estimated_period_seconds if duration_seconds and estimated_period_seconds else None
    dfa, multiscale_slope = dfa_alpha(residual)

    return {
        "preview_point_count": len(values),
        "pulse_energy": pulse_energy,
        "residual_fluctuation": residual_fluctuation,
        "residual_std": residual_std,
        "residual_cv": (residual_std or 0.0) / detrended_std if detrended_std else None,
        "residual_energy_ratio": residual_energy_ratio,
        "template_coherence": template_coherence,
        "periodic_snr": periodic_snr,
        "dominant_lag_preview_points": dominant_lag,
        "period_lag_min_preview_points": min_lag,
        "period_lag_max_preview_points": max_lag,
        "estimated_period_seconds": estimated_period_seconds,
        "estimated_pulse_rate_bpm": estimated_pulse_rate_bpm,
        "pulse_count_estimate": pulse_count_estimate,
        "peak_count_preview": len(peaks),
        "period_consistency_score": peak_consistency,
        "trend_slope_preview": trend_slope,
        "trend_intercept_preview": trend_intercept,
        "template_explained_variance_ratio": explained_ratio,
        "detrended_std": detrended_std,
        "dfa_alpha": dfa,
        "multi_scale_fluctuation_slope": multiscale_slope,
        "template_vector": template,
        "normalized_template_vector": normalize_vector(template),
        "residual_vector": residual,
    }


def preview_channel_metrics(values: list[float]) -> dict[str, Any]:
    metrics = decompose_preview_signal(values)
    return {key: value for key, value in metrics.items() if key not in {"template_vector", "normalized_template_vector", "residual_vector"}}


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
        y_values = extract_preview_values(row)
        summary = parse_json_value(row.get("summary_json"), {})
        summary = summary if isinstance(summary, dict) else {}

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
                "waveform_preview_point_count": len(y_values),
                "waveform_sample_count": safe_float(row.get("sample_count")) or safe_float(summary.get("count")),
                "waveform_sampling_rate": safe_float(row.get("sampling_rate")),
            }
        )
    if not result:
        return pd.DataFrame(
            columns=[
                "measurement_id",
                "waveform_channel_count",
                "baseline_drift_slope",
                "baseline_instability",
                "artifact_ratio_from_preview",
                "has_waveform_preview",
                "waveform_preview_point_count",
                "waveform_sample_count",
                "waveform_sampling_rate",
            ]
        )
    frame = pd.DataFrame(result)
    return frame.groupby("measurement_id", as_index=False).agg(
        {
            "waveform_channel_count": "sum",
            "baseline_drift_slope": "mean",
            "baseline_instability": "mean",
            "artifact_ratio_from_preview": "mean",
            "has_waveform_preview": "max",
            "waveform_preview_point_count": "max",
            "waveform_sample_count": "max",
            "waveform_sampling_rate": "max",
        }
    )


def analyze_channel_signal_quality(dataset_dir: Path, feature_matrix: pd.DataFrame) -> pd.DataFrame:
    rows = read_jsonl(dataset_dir / "waveform_manifest.jsonl")
    if not rows:
        return pd.DataFrame()

    metadata_columns = [
        "measurement_id",
        "user_id",
        "source_vendor",
        "device_id",
        "visit_slot",
        "start_time",
        "duration_seconds",
    ]
    metadata = pd.DataFrame()
    if not feature_matrix.empty:
        available_columns = [column for column in metadata_columns if column in feature_matrix.columns]
        metadata = feature_matrix[available_columns].drop_duplicates("measurement_id") if "measurement_id" in available_columns else pd.DataFrame()

    records = []
    for row in rows:
        summary = parse_json_value(row.get("summary_json"), {})
        summary = summary if isinstance(summary, dict) else {}
        values = extract_preview_values(row)
        sample_count = safe_float(row.get("sample_count")) or safe_float(summary.get("count"))
        sampling_rate = safe_float(row.get("sampling_rate")) or safe_float(summary.get("sampling_rate"))
        duration_seconds = safe_float(row.get("duration_seconds")) or safe_float(summary.get("duration_seconds"))
        if duration_seconds is None and sample_count and sampling_rate:
            duration_seconds = sample_count / sampling_rate
        metrics = decompose_preview_signal(values, duration_seconds)
        metrics = {key: value for key, value in metrics.items() if key not in {"template_vector", "normalized_template_vector", "residual_vector"}}

        records.append(
            {
                "measurement_id": row.get("measurement_id"),
                "waveform_asset_id": row.get("waveform_asset_id"),
                "channel_name": row.get("channel_name"),
                "standard_channel_name": standard_channel_name(row.get("channel_name")),
                "hand_side": row.get("hand_side"),
                "pulse_position": row.get("pulse_position"),
                "sample_count": sample_count,
                "sampling_rate": sampling_rate,
                "duration_seconds": duration_seconds,
                "data_format": row.get("data_format"),
                "storage_uri": row.get("storage_uri"),
                **metrics,
            }
        )

    frame = pd.DataFrame(records)
    if not metadata.empty:
        frame = frame.merge(metadata, on="measurement_id", how="left", suffixes=("", "_measurement"))
        if "duration_seconds_measurement" in frame:
            frame["duration_seconds"] = pd.to_numeric(frame["duration_seconds"], errors="coerce").fillna(
                pd.to_numeric(frame["duration_seconds_measurement"], errors="coerce")
            )
            frame = frame.drop(columns=["duration_seconds_measurement"])

    frame["pulse_energy"] = pd.to_numeric(frame["pulse_energy"], errors="coerce")
    frame["template_coherence"] = pd.to_numeric(frame["template_coherence"], errors="coerce")
    frame["periodic_snr"] = pd.to_numeric(frame["periodic_snr"], errors="coerce")
    frame["residual_fluctuation"] = pd.to_numeric(frame["residual_fluctuation"], errors="coerce")

    median_energy = frame.groupby("standard_channel_name")["pulse_energy"].transform("median")
    frame["channel_energy_ratio_to_median"] = frame["pulse_energy"] / median_energy.where(median_energy > 0)

    labels = []
    suspicion_scores = []
    for _, row in frame.iterrows():
        preview_count = safe_float(row.get("preview_point_count")) or 0
        energy_ratio = safe_float(row.get("channel_energy_ratio_to_median"))
        coherence = safe_float(row.get("template_coherence")) or 0.0
        snr = safe_float(row.get("periodic_snr")) or 0.0
        fluctuation = safe_float(row.get("residual_fluctuation")) or 1.0

        if preview_count < 16:
            suspicion = 100.0
            label = "insufficient_preview"
        else:
            flat_penalty = clamp(((0.35 - (energy_ratio or 0.0)) / 0.35) * 45, 0, 45) if energy_ratio is not None else 20.0
            periodic_penalty = clamp(((0.18 - coherence) / 0.18) * 35, 0, 35)
            snr_penalty = clamp(((0.15 - snr) / 0.15) * 20, 0, 20)
            fluctuation_penalty = clamp((fluctuation - 0.7) * 20, 0, 15)
            suspicion = flat_penalty + periodic_penalty + snr_penalty + fluctuation_penalty
            if suspicion >= 60:
                label = "suspected_misalignment"
            elif snr < 0.08 or coherence < 0.08:
                label = "low_snr"
            else:
                label = "valid"
        labels.append(label)
        suspicion_scores.append(round(suspicion, 3))

    frame["alignment_suspicion_score"] = suspicion_scores
    frame["channel_validity_label"] = labels
    numeric_columns = [
        "pulse_energy",
        "residual_fluctuation",
        "template_coherence",
        "periodic_snr",
        "channel_energy_ratio_to_median",
        "sample_count",
        "sampling_rate",
        "duration_seconds",
        "estimated_period_seconds",
        "estimated_pulse_rate_bpm",
        "pulse_count_estimate",
        "period_consistency_score",
        "trend_slope_preview",
        "trend_intercept_preview",
        "template_explained_variance_ratio",
        "residual_std",
        "residual_cv",
        "residual_energy_ratio",
        "detrended_std",
        "dfa_alpha",
        "multi_scale_fluctuation_slope",
    ]
    for column in numeric_columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").round(6)
    return frame


def summarize_measurement_channels(channel_quality: pd.DataFrame) -> pd.DataFrame:
    if channel_quality.empty:
        return pd.DataFrame()

    rows = []
    for measurement_id, group in channel_quality.groupby("measurement_id", dropna=False):
        row: dict[str, Any] = {"measurement_id": measurement_id}
        core = group[group["standard_channel_name"].isin(CHANNEL_ORDER)].copy()
        usable = core if not core.empty else group
        energy_values = pd.to_numeric(core["pulse_energy"], errors="coerce").dropna()
        mean_energy = energy_values.mean() if not energy_values.empty else None
        if mean_energy and mean_energy > 0 and len(energy_values) >= 2:
            channel_balance_index = clamp(1 - float(energy_values.std(ddof=0) / mean_energy), 0, 1)
        else:
            channel_balance_index = None

        row.update(
            {
                "valid_channel_count": int((usable["channel_validity_label"] == "valid").sum()),
                "low_snr_channel_count": int((usable["channel_validity_label"] == "low_snr").sum()),
                "suspected_alignment_channel_count": int((usable["channel_validity_label"] == "suspected_misalignment").sum()),
                "insufficient_preview_channel_count": int((usable["channel_validity_label"] == "insufficient_preview").sum()),
                "overall_periodic_snr": round(float(pd.to_numeric(usable["periodic_snr"], errors="coerce").mean()), 6),
                "overall_pulse_energy": round(float(pd.to_numeric(usable["pulse_energy"], errors="coerce").mean()), 6),
                "overall_template_coherence": round(float(pd.to_numeric(usable["template_coherence"], errors="coerce").mean()), 6),
                "overall_alignment_suspicion_score": round(float(pd.to_numeric(usable["alignment_suspicion_score"], errors="coerce").mean()), 3),
                "channel_balance_index": round(channel_balance_index, 6) if channel_balance_index is not None else None,
            }
        )
        for channel in CHANNEL_ORDER:
            match = core[core["standard_channel_name"] == channel]
            if match.empty:
                row[f"{channel}_periodic_snr"] = None
                row[f"{channel}_pulse_energy"] = None
                row[f"{channel}_template_coherence"] = None
                row[f"{channel}_alignment_suspicion_score"] = None
                row[f"{channel}_validity_label"] = None
                continue
            selected = match.iloc[0]
            row[f"{channel}_periodic_snr"] = selected.get("periodic_snr")
            row[f"{channel}_pulse_energy"] = selected.get("pulse_energy")
            row[f"{channel}_template_coherence"] = selected.get("template_coherence")
            row[f"{channel}_alignment_suspicion_score"] = selected.get("alignment_suspicion_score")
            row[f"{channel}_validity_label"] = selected.get("channel_validity_label")
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_longitudinal_channels(channel_quality: pd.DataFrame) -> pd.DataFrame:
    if channel_quality.empty or "user_id" not in channel_quality:
        return pd.DataFrame()
    frame = channel_quality.dropna(subset=["user_id"]).copy()
    if frame.empty:
        return pd.DataFrame()

    rows = []
    for (user_id, channel), group in frame.groupby(["user_id", "standard_channel_name"], dropna=False):
        periodic = pd.to_numeric(group["periodic_snr"], errors="coerce")
        energy = pd.to_numeric(group["pulse_energy"], errors="coerce")
        coherence = pd.to_numeric(group["template_coherence"], errors="coerce")
        suspicion = pd.to_numeric(group["alignment_suspicion_score"], errors="coerce")
        rows.append(
            {
                "user_id": user_id,
                "standard_channel_name": channel,
                "record_count": int(len(group)),
                "valid_channel_count": int((group["channel_validity_label"] == "valid").sum()),
                "low_snr_count": int((group["channel_validity_label"] == "low_snr").sum()),
                "suspected_misalignment_count": int((group["channel_validity_label"] == "suspected_misalignment").sum()),
                "avg_periodic_snr": round(float(periodic.mean()), 6) if periodic.notna().any() else None,
                "best_periodic_snr": round(float(periodic.max()), 6) if periodic.notna().any() else None,
                "avg_pulse_energy": round(float(energy.mean()), 6) if energy.notna().any() else None,
                "avg_template_coherence": round(float(coherence.mean()), 6) if coherence.notna().any() else None,
                "avg_alignment_suspicion_score": round(float(suspicion.mean()), 3) if suspicion.notna().any() else None,
                "energy_cv": round(coefficient_of_variation(energy), 6) if coefficient_of_variation(energy) is not None else None,
                "periodic_snr_cv": round(coefficient_of_variation(periodic), 6) if coefficient_of_variation(periodic) is not None else None,
            }
        )
    return pd.DataFrame(rows)


def analyze_pulse_periodicity(channel_quality: pd.DataFrame) -> pd.DataFrame:
    if channel_quality.empty:
        return pd.DataFrame()

    columns = [
        "measurement_id",
        "waveform_asset_id",
        "user_id",
        "source_vendor",
        "device_id",
        "visit_slot",
        "start_time",
        "channel_name",
        "standard_channel_name",
        "duration_seconds",
        "preview_point_count",
        "dominant_lag_preview_points",
        "period_lag_min_preview_points",
        "period_lag_max_preview_points",
        "estimated_period_seconds",
        "estimated_pulse_rate_bpm",
        "pulse_count_estimate",
        "peak_count_preview",
        "period_consistency_score",
        "periodic_snr",
        "pulse_energy",
        "template_coherence",
        "template_explained_variance_ratio",
        "channel_energy_ratio_to_median",
        "alignment_suspicion_score",
        "channel_validity_label",
    ]
    frame = channel_quality[[column for column in columns if column in channel_quality.columns]].copy()
    frame["periodic_snr"] = pd.to_numeric(frame["periodic_snr"], errors="coerce")
    frame["template_coherence"] = pd.to_numeric(frame["template_coherence"], errors="coerce")
    frame["period_consistency_score"] = pd.to_numeric(frame["period_consistency_score"], errors="coerce")
    frame["alignment_suspicion_score"] = pd.to_numeric(frame["alignment_suspicion_score"], errors="coerce")
    frame["estimated_pulse_rate_bpm"] = pd.to_numeric(frame["estimated_pulse_rate_bpm"], errors="coerce")

    labels = []
    for _, row in frame.iterrows():
        snr = safe_float(row.get("periodic_snr")) or 0.0
        coherence = safe_float(row.get("template_coherence")) or 0.0
        consistency = safe_float(row.get("period_consistency_score")) or 0.0
        suspicion = safe_float(row.get("alignment_suspicion_score")) or 0.0
        bpm = safe_float(row.get("estimated_pulse_rate_bpm"))
        plausible_bpm = bpm is None or 35 <= bpm <= 180
        if suspicion >= 60:
            label = "suspected_misalignment"
        elif snr >= 0.35 and coherence >= 0.25 and consistency >= 0.25 and plausible_bpm:
            label = "clear_periodic"
        elif snr >= 0.08 and coherence >= 0.08 and plausible_bpm:
            label = "weak_periodic"
        else:
            label = "non_periodic_or_noise"
        labels.append(label)
    frame["periodic_signal_label"] = labels
    frame["channel_periodicity_rank"] = (
        frame.groupby("measurement_id")["periodic_snr"].rank(method="first", ascending=False, na_option="bottom").astype("Int64")
    )
    return frame


def waveform_metadata(feature_matrix: pd.DataFrame) -> pd.DataFrame:
    metadata_columns = [
        "measurement_id",
        "user_id",
        "source_vendor",
        "device_id",
        "visit_slot",
        "start_time",
        "duration_seconds",
    ]
    if feature_matrix.empty:
        return pd.DataFrame()
    available_columns = [column for column in metadata_columns if column in feature_matrix.columns]
    if "measurement_id" not in available_columns:
        return pd.DataFrame()
    return feature_matrix[available_columns].drop_duplicates("measurement_id")


def analyze_template_decomposition(dataset_dir: Path, feature_matrix: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = read_jsonl(dataset_dir / "waveform_manifest.jsonl")
    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    metadata = waveform_metadata(feature_matrix)
    measurement_meta = metadata.set_index("measurement_id").to_dict(orient="index") if not metadata.empty else {}
    decomposition_rows = []
    template_rows = []
    for row in rows:
        summary = parse_json_value(row.get("summary_json"), {})
        summary = summary if isinstance(summary, dict) else {}
        values = extract_preview_values(row)
        sample_count = safe_float(row.get("sample_count")) or safe_float(summary.get("count"))
        sampling_rate = safe_float(row.get("sampling_rate")) or safe_float(summary.get("sampling_rate"))
        duration_seconds = safe_float(row.get("duration_seconds")) or safe_float(summary.get("duration_seconds"))
        if duration_seconds is None and sample_count and sampling_rate:
            duration_seconds = sample_count / sampling_rate
        meta = measurement_meta.get(row.get("measurement_id"), {})
        if duration_seconds is None:
            duration_seconds = safe_float(meta.get("duration_seconds"))

        metrics = decompose_preview_signal(values, duration_seconds)
        channel = standard_channel_name(row.get("channel_name"))
        template_quality_score = clamp(
            (safe_float(metrics.get("template_explained_variance_ratio")) or 0.0) * 45
            + (safe_float(metrics.get("template_coherence")) or 0.0) * 35
            + min(1.0, safe_float(metrics.get("periodic_snr")) or 0.0) * 20
            - (safe_float(metrics.get("residual_energy_ratio")) or 1.0) * 15
        )

        decomposition_rows.append(
            {
                "measurement_id": row.get("measurement_id"),
                "waveform_asset_id": row.get("waveform_asset_id"),
                "user_id": meta.get("user_id"),
                "source_vendor": meta.get("source_vendor"),
                "device_id": meta.get("device_id"),
                "visit_slot": meta.get("visit_slot"),
                "start_time": meta.get("start_time"),
                "channel_name": row.get("channel_name"),
                "standard_channel_name": channel,
                "duration_seconds": duration_seconds,
                "sample_count": sample_count,
                "sampling_rate": sampling_rate,
                "preview_point_count": metrics.get("preview_point_count"),
                "trend_slope_preview": metrics.get("trend_slope_preview"),
                "trend_intercept_preview": metrics.get("trend_intercept_preview"),
                "dominant_lag_preview_points": metrics.get("dominant_lag_preview_points"),
                "estimated_period_seconds": metrics.get("estimated_period_seconds"),
                "estimated_pulse_rate_bpm": metrics.get("estimated_pulse_rate_bpm"),
                "template_explained_variance_ratio": metrics.get("template_explained_variance_ratio"),
                "periodic_snr": metrics.get("periodic_snr"),
                "pulse_energy": metrics.get("pulse_energy"),
                "template_coherence": metrics.get("template_coherence"),
                "residual_std": metrics.get("residual_std"),
                "residual_cv": metrics.get("residual_cv"),
                "residual_energy_ratio": metrics.get("residual_energy_ratio"),
                "residual_fluctuation": metrics.get("residual_fluctuation"),
                "dfa_alpha": metrics.get("dfa_alpha"),
                "multi_scale_fluctuation_slope": metrics.get("multi_scale_fluctuation_slope"),
                "template_quality_score": template_quality_score,
                "decomposition_quality_label": "usable_template" if template_quality_score >= 45 else "weak_template" if template_quality_score >= 20 else "insufficient_periodic_structure",
            }
        )

        for template_type, vector in [
            ("amplitude_preserved_template", metrics.get("template_vector") or []),
            ("amplitude_normalized_template", metrics.get("normalized_template_vector") or []),
        ]:
            template_rows.append(
                {
                    "template_id": f"{row.get('waveform_asset_id') or row.get('measurement_id')}:{template_type}",
                    "measurement_id": row.get("measurement_id"),
                    "waveform_asset_id": row.get("waveform_asset_id"),
                    "user_id": meta.get("user_id"),
                    "channel_name": row.get("channel_name"),
                    "standard_channel_name": channel,
                    "template_type": template_type,
                    "template_point_count": len(vector),
                    "template_vector_json": json.dumps(round_vector(vector), ensure_ascii=False),
                    "template_quality_score": round(template_quality_score, 3),
                    "pulse_energy": metrics.get("pulse_energy"),
                    "template_coherence": metrics.get("template_coherence"),
                    "periodic_snr": metrics.get("periodic_snr"),
                    "source_segment_start": 0.0 if duration_seconds else None,
                    "source_segment_end": duration_seconds,
                }
            )

    decomposition = pd.DataFrame(decomposition_rows)
    templates = pd.DataFrame(template_rows)
    for frame in [decomposition, templates]:
        for column in frame.columns:
            if column.endswith("_json") or column in {"template_id", "measurement_id", "waveform_asset_id", "user_id", "source_vendor", "device_id", "visit_slot", "start_time", "channel_name", "standard_channel_name", "template_type", "decomposition_quality_label"}:
                continue
            converted = pd.to_numeric(frame[column], errors="coerce")
            if converted.notna().any() or frame[column].isna().all():
                frame[column] = converted
        numeric_columns = frame.select_dtypes(include=["number"]).columns
        frame[numeric_columns] = frame[numeric_columns].round(6)
    return decomposition, templates


def analyze_measurement_quality(feature_matrix: pd.DataFrame, waveform_frame: pd.DataFrame, channel_summary: pd.DataFrame | None = None) -> pd.DataFrame:
    if feature_matrix.empty:
        return pd.DataFrame()
    frame = feature_matrix.merge(waveform_frame, on="measurement_id", how="left")
    if channel_summary is not None and not channel_summary.empty:
        frame = frame.merge(channel_summary, on="measurement_id", how="left")
    frame["stability_score"] = pd.to_numeric(frame["stability_score"], errors="coerce")
    frame["amplitude"] = pd.to_numeric(frame["amplitude"], errors="coerce")
    frame["duration_seconds"] = pd.to_numeric(frame["duration_seconds"], errors="coerce").fillna(0)
    frame["waveform_sample_count"] = pd.to_numeric(frame.get("waveform_sample_count"), errors="coerce")
    frame["waveform_sampling_rate"] = pd.to_numeric(frame.get("waveform_sampling_rate"), errors="coerce")
    frame["baseline_instability"] = pd.to_numeric(frame["baseline_instability"], errors="coerce").fillna(1.0)
    frame["artifact_ratio_from_preview"] = pd.to_numeric(frame["artifact_ratio_from_preview"], errors="coerce").fillna(1.0)
    frame["has_waveform_preview"] = frame["has_waveform_preview"].map(lambda value: False if pd.isna(value) else bool(value))

    stability_component = frame["stability_score"].fillna(50).clip(0, 100)
    drift_penalty = (frame["baseline_instability"].clip(0, 1) * 35).fillna(35)
    artifact_penalty = (frame["artifact_ratio_from_preview"].clip(0, 1) * 15).fillna(15)
    waveform_bonus = frame["has_waveform_preview"].map(lambda value: 5 if bool(value) else -10)

    signal_quality = (stability_component - drift_penalty - artifact_penalty + waveform_bonus).map(lambda value: clamp(float(value)))
    has_channel_quality = "overall_periodic_snr" in frame
    if has_channel_quality:
        frame["overall_periodic_snr"] = pd.to_numeric(frame["overall_periodic_snr"], errors="coerce")
        frame["overall_template_coherence"] = pd.to_numeric(frame["overall_template_coherence"], errors="coerce")
        frame["valid_channel_count"] = pd.to_numeric(frame["valid_channel_count"], errors="coerce").fillna(0)
        frame["suspected_alignment_channel_count"] = pd.to_numeric(frame["suspected_alignment_channel_count"], errors="coerce").fillna(0)
        frame["overall_alignment_suspicion_score"] = pd.to_numeric(frame["overall_alignment_suspicion_score"], errors="coerce")
        periodic_component = (frame["overall_periodic_snr"].clip(0, 0.6) / 0.6 * 35).fillna(0)
        coherence_component = (frame["overall_template_coherence"].clip(0, 0.6) / 0.6 * 35).fillna(0)
        channel_count_component = (frame["valid_channel_count"].clip(0, 3) / 3 * 30).fillna(0)
        alignment_penalty = (frame["suspected_alignment_channel_count"].clip(0, 3) * 12).fillna(0)
        channel_quality_score = (periodic_component + coherence_component + channel_count_component - alignment_penalty).map(lambda value: clamp(float(value)))
        signal_quality = (signal_quality * 0.45 + channel_quality_score * 0.55).map(lambda value: clamp(float(value)))
    else:
        channel_quality_score = pd.Series([pd.NA] * len(frame), index=frame.index)
    drift_index = (frame["baseline_instability"].clip(0, 1) * 70 + (100 - stability_component) * 0.3).map(lambda value: clamp(float(value)))
    stable_segment_ratio = (stability_component / 100 - frame["baseline_instability"].clip(0, 1) * 0.25).clip(0, 1)
    inferred_duration = frame["duration_seconds"].where(frame["duration_seconds"] > 0)
    waveform_duration = frame["waveform_sample_count"] / frame["waveform_sampling_rate"]
    waveform_duration = waveform_duration.where((frame["waveform_sample_count"] > 0) & (frame["waveform_sampling_rate"] > 0))
    inferred_duration = inferred_duration.fillna(waveform_duration)
    has_duration = inferred_duration.notna() & (inferred_duration > 0)
    best_duration = (inferred_duration.fillna(0) * stable_segment_ratio).clip(lower=0)

    labels = []
    reasons = []
    validity_iter = zip(
        signal_quality,
        best_duration,
        stable_segment_ratio,
        has_duration,
        frame["valid_channel_count"] if has_channel_quality else [None] * len(frame),
        frame["suspected_alignment_channel_count"] if has_channel_quality else [None] * len(frame),
        channel_quality_score if has_channel_quality else [None] * len(frame),
    )
    for quality, duration, ratio, duration_available, valid_channels, suspected_alignment, channel_score in validity_iter:
        valid_channels = safe_float(valid_channels)
        suspected_alignment = safe_float(suspected_alignment) or 0.0
        channel_score = safe_float(channel_score)
        if channel_score is not None:
            if duration_available and duration >= 20 and valid_channels is not None and valid_channels >= 2 and channel_score >= 50 and suspected_alignment <= 1:
                labels.append("valid")
                reasons.append("")
            elif valid_channels is not None and valid_channels >= 1 and channel_score >= 35:
                labels.append("partial_valid")
                reasons.append("channel periodic signal is usable but not enough for full validity")
            elif valid_channels is not None and valid_channels == 0 and suspected_alignment > 0:
                labels.append("invalid")
                reasons.append("no valid periodic channel; suspected misalignment or contact issue")
            else:
                labels.append("invalid")
                reasons.append("insufficient periodic pulse signal")
        elif duration_available and quality >= 75 and duration >= 20 and ratio >= 0.5:
            labels.append("valid")
            reasons.append("")
        elif duration_available and quality >= 60 and duration >= 10:
            labels.append("partial_valid")
            reasons.append("stable segment is short or quality is moderate")
        elif not duration_available and quality >= 75 and ratio >= 0.5:
            labels.append("partial_valid")
            reasons.append("duration unavailable; waveform preview supports quality-only screening")
        elif not duration_available and quality >= 60:
            labels.append("partial_valid")
            reasons.append("duration unavailable; moderate quality-only screening")
        else:
            labels.append("invalid")
            reasons.append("insufficient stable high-quality segment")

    best_start = ((inferred_duration - best_duration) / 2).where(has_duration).clip(lower=0)
    best_end = (best_start + best_duration).where(has_duration)

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
            "channel_quality_score": channel_quality_score.round(3),
            "valid_channel_count": frame.get("valid_channel_count"),
            "low_snr_channel_count": frame.get("low_snr_channel_count"),
            "suspected_alignment_channel_count": frame.get("suspected_alignment_channel_count"),
            "overall_periodic_snr": frame.get("overall_periodic_snr"),
            "overall_pulse_energy": frame.get("overall_pulse_energy"),
            "overall_template_coherence": frame.get("overall_template_coherence"),
            "overall_alignment_suspicion_score": frame.get("overall_alignment_suspicion_score"),
            "channel_balance_index": frame.get("channel_balance_index"),
            "inferred_duration_seconds": inferred_duration.round(3),
            "duration_available": has_duration,
            "best_segment_start_time": best_start.round(3),
            "best_segment_end_time": best_end.round(3),
            "best_segment_duration": best_duration.where(has_duration).round(3),
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
    channel_quality = frames.get("channel_signal_quality", pd.DataFrame())
    pulse_periodicity = frames.get("pulse_periodicity", pd.DataFrame())
    decomposition = frames.get("trend_residual_decomposition", pd.DataFrame())
    templates = frames.get("pulse_templates", pd.DataFrame())
    measurement_channels = frames.get("measurement_channel_summary", pd.DataFrame())
    longitudinal_channels = frames.get("longitudinal_channel_summary", pd.DataFrame())
    reliability = frames.get("feature_reliability", pd.DataFrame())
    device = frames.get("device_consistency", pd.DataFrame())
    lines = [
        "# Pulse Phase 1-3 Analysis Report",
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
        f"- duration unavailable measurements: {summary['duration_unavailable_measurement_count']}",
        f"- waveform channel rows: {summary['channel_signal_count']}",
        f"- valid channel rows: {summary['valid_channel_signal_count']}",
        f"- suspected misalignment channel rows: {summary['suspected_misalignment_channel_count']}",
        f"- periodicity rows: {summary['pulse_periodicity_count']}",
        f"- decomposition rows: {summary['trend_residual_decomposition_count']}",
        f"- pulse template rows: {summary['pulse_template_count']}",
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
        if summary["duration_unavailable_measurement_count"]:
            lines.append("- duration is unavailable for some measurements; these rows cannot be promoted from `partial_valid` to `valid`.")
    lines.extend(["", "## Channel Periodic Signal Quality", ""])
    if channel_quality.empty:
        lines.append("No channel waveform preview rows were produced.")
    else:
        label_counts = channel_quality["channel_validity_label"].value_counts().to_dict()
        for label in ["valid", "low_snr", "suspected_misalignment", "insufficient_preview"]:
            if label in label_counts:
                lines.append(f"- {label}: {label_counts[label]}")
        avg_snr = channel_quality["periodic_snr"].mean()
        avg_coherence = channel_quality["template_coherence"].mean()
        lines.append(f"- average periodic_snr: {avg_snr:.4f}")
        lines.append(f"- average template_coherence: {avg_coherence:.4f}")
        lines.append("- metrics are computed from waveform preview points in the current dataset; full-waveform exports should replace this estimator in later phases.")
    if not measurement_channels.empty:
        avg_balance = measurement_channels["channel_balance_index"].mean()
        lines.append(f"- measurement channel summaries: {len(measurement_channels)}")
        if not math.isnan(avg_balance):
            lines.append(f"- average channel_balance_index: {avg_balance:.4f}")
    if not longitudinal_channels.empty:
        lines.append(f"- longitudinal user-channel summaries: {len(longitudinal_channels)}")
    lines.extend(["", "## Pulse Periodicity", ""])
    if pulse_periodicity.empty:
        lines.append("No pulse periodicity rows were produced.")
    else:
        label_counts = pulse_periodicity["periodic_signal_label"].value_counts().to_dict()
        for label in ["clear_periodic", "weak_periodic", "non_periodic_or_noise", "suspected_misalignment"]:
            if label in label_counts:
                lines.append(f"- {label}: {label_counts[label]}")
        avg_bpm = pulse_periodicity["estimated_pulse_rate_bpm"].mean()
        if not math.isnan(avg_bpm):
            lines.append(f"- average estimated pulse rate: {avg_bpm:.2f} bpm")
    lines.extend(["", "## Trend And Template Decomposition", ""])
    if decomposition.empty:
        lines.append("No trend/template decomposition rows were produced.")
    else:
        label_counts = decomposition["decomposition_quality_label"].value_counts().to_dict()
        for label in ["usable_template", "weak_template", "insufficient_periodic_structure"]:
            if label in label_counts:
                lines.append(f"- {label}: {label_counts[label]}")
        avg_dfa = decomposition["dfa_alpha"].mean()
        avg_residual = decomposition["residual_energy_ratio"].mean()
        if not math.isnan(avg_dfa):
            lines.append(f"- average DFA alpha: {avg_dfa:.4f}")
        if not math.isnan(avg_residual):
            lines.append(f"- average residual energy ratio: {avg_residual:.4f}")
    if not templates.empty:
        lines.append(f"- pulse templates: {len(templates)}")
    lines.extend(["", "## Device Consistency", ""])
    if device.empty:
        lines.append(f"No cross-device feature pairs were produced within {summary['near_time_pair_window_minutes']} minutes.")
    else:
        lines.append(f"- feature rows: {summary['device_consistency_feature_count']}")
        lines.append(f"- paired comparisons: {summary['device_consistency_pair_count']}")
    return "\n".join(lines) + "\n"


def analyze(dataset_dir: Path, output_dir: Path, near_minutes: int) -> None:
    feature_matrix = load_feature_matrix(dataset_dir)
    waveform_frame = waveform_metrics(dataset_dir)
    channel_quality = analyze_channel_signal_quality(dataset_dir, feature_matrix)
    pulse_periodicity = analyze_pulse_periodicity(channel_quality)
    decomposition, templates = analyze_template_decomposition(dataset_dir, feature_matrix)
    measurement_channels = summarize_measurement_channels(channel_quality)
    longitudinal_channels = summarize_longitudinal_channels(channel_quality)
    quality = analyze_measurement_quality(feature_matrix, waveform_frame, measurement_channels)
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
        "duration_unavailable_measurement_count": int((quality["duration_available"] == False).sum()) if not quality.empty and "duration_available" in quality else 0,
        "channel_signal_count": int(len(channel_quality)),
        "valid_channel_signal_count": int((channel_quality["channel_validity_label"] == "valid").sum()) if not channel_quality.empty else 0,
        "low_snr_channel_count": int((channel_quality["channel_validity_label"] == "low_snr").sum()) if not channel_quality.empty else 0,
        "suspected_misalignment_channel_count": int((channel_quality["channel_validity_label"] == "suspected_misalignment").sum()) if not channel_quality.empty else 0,
        "insufficient_preview_channel_count": int((channel_quality["channel_validity_label"] == "insufficient_preview").sum()) if not channel_quality.empty else 0,
        "pulse_periodicity_count": int(len(pulse_periodicity)),
        "clear_periodic_channel_count": int((pulse_periodicity["periodic_signal_label"] == "clear_periodic").sum()) if not pulse_periodicity.empty else 0,
        "weak_periodic_channel_count": int((pulse_periodicity["periodic_signal_label"] == "weak_periodic").sum()) if not pulse_periodicity.empty else 0,
        "trend_residual_decomposition_count": int(len(decomposition)),
        "usable_template_decomposition_count": int((decomposition["decomposition_quality_label"] == "usable_template").sum()) if not decomposition.empty else 0,
        "pulse_template_count": int(len(templates)),
        "measurement_channel_summary_count": int(len(measurement_channels)),
        "longitudinal_channel_summary_count": int(len(longitudinal_channels)),
        "feature_count": int(len(reliability)),
        "device_consistency_feature_count": int(len(device)),
        "device_consistency_pair_count": int(device["pair_count"].sum()) if not device.empty and "pair_count" in device else 0,
        "near_time_pair_window_minutes": near_minutes,
    }
    write_outputs(
        output_dir,
        {
            "measurement_quality": quality,
            "channel_signal_quality": channel_quality,
            "pulse_periodicity": pulse_periodicity,
            "trend_residual_decomposition": decomposition,
            "pulse_templates": templates,
            "measurement_channel_summary": measurement_channels,
            "longitudinal_channel_summary": longitudinal_channels,
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
