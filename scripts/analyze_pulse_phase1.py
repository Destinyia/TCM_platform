from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


QUALITY_FEATURES = ["stability_score"]
CORE_FEATURES = ["pulse_rate", "force", "tension", "fluency", "amplitude", "h1", "h3", "w", "as", "ad", "stability_score"]
CHANNEL_ORDER = ["cun", "guan", "chi"]
RAW_CHANNEL_FIELDS = {"cun": "Cun", "guan": "GuanMai", "chi": "Chi"}
PERIOD_SEARCH_BANDS = (0.05, 0.10, 0.15, 0.20)
PERIOD_CONSISTENCY_VERSION = "pulse_rate_period_consistency_v1"


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


def normalized_entropy(values: list[float], bin_count: int = 10) -> float | None:
    if len(values) < 2:
        return None
    minimum = min(values)
    maximum = max(values)
    if maximum <= minimum:
        return 0.0
    counts = [0 for _ in range(bin_count)]
    width = (maximum - minimum) / bin_count
    for value in values:
        index = min(bin_count - 1, int((value - minimum) / width))
        counts[index] += 1
    probabilities = [count / len(values) for count in counts if count]
    entropy = -sum(probability * math.log(probability) for probability in probabilities)
    return entropy / math.log(bin_count)


def robust_center_scale(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    center = percentile(values, 0.5)
    deviations = [abs(value - (center or 0.0)) for value in values]
    scale = (percentile(deviations, 0.5) or 0.0) * 1.4826
    if not scale:
        _, scale = mean_std(values)
    return center, scale or 1.0


def circular_shift(values: list[float], shift: int) -> list[float]:
    if not values:
        return []
    offset = shift % len(values)
    if not offset:
        return values[:]
    return values[-offset:] + values[:-offset]


def fit_beat_to_template(cycle: list[float], template: list[float]) -> dict[str, float | None]:
    if len(cycle) < 3 or len(cycle) != len(template):
        return {
            "baseline_offset": None,
            "amplitude_scale": None,
            "phase_shift_points": None,
            "phase_shift_ratio": None,
            "template_fit_r2": None,
            "fit_residual_std": None,
            "fit_residual_energy_ratio": None,
        }

    max_shift = max(1, min(8, len(template) // 4))
    cycle_mean, _ = mean_std(cycle)
    cycle_variance = variance(cycle) or 0.0
    best: dict[str, float | None] | None = None
    best_sse: float | None = None
    for shift in range(-max_shift, max_shift + 1):
        aligned_template = circular_shift(template, shift)
        template_mean, _ = mean_std(aligned_template)
        centered_template = [value - (template_mean or 0.0) for value in aligned_template]
        denominator = sum(value * value for value in centered_template)
        if denominator <= 0:
            continue
        amplitude_scale = sum(
            (value - (cycle_mean or 0.0)) * template_value
            for value, template_value in zip(cycle, centered_template)
        ) / denominator
        baseline_offset = (cycle_mean or 0.0) - amplitude_scale * (template_mean or 0.0)
        fitted = [baseline_offset + amplitude_scale * value for value in aligned_template]
        residual = [value - predicted for value, predicted in zip(cycle, fitted)]
        sse = sum(value * value for value in residual)
        if best_sse is not None and sse >= best_sse:
            continue
        residual_std = mean_std(residual)[1]
        best_sse = sse
        best = {
            "baseline_offset": baseline_offset,
            "amplitude_scale": amplitude_scale,
            "phase_shift_points": float(shift),
            "phase_shift_ratio": shift / len(template),
            "template_fit_r2": clamp(1 - (sse / (cycle_variance * max(1, len(cycle) - 1) + 1e-9)), 0, 1),
            "fit_residual_std": residual_std,
            "fit_residual_energy_ratio": sse / (sum(value * value for value in cycle) + 1e-9),
        }
    return best or {
        "baseline_offset": None,
        "amplitude_scale": None,
        "phase_shift_points": None,
        "phase_shift_ratio": None,
        "template_fit_r2": None,
        "fit_residual_std": None,
        "fit_residual_energy_ratio": None,
    }


def normalized_shape_features(cycle: list[float]) -> dict[str, float | None]:
    normalized = normalize_vector(cycle)
    if len(normalized) < 3:
        return {
            "normalized_peak_phase": None,
            "normalized_rise_time_ratio": None,
            "normalized_half_width_ratio": None,
            "normalized_notch_phase": None,
        }
    peak_index = max(range(len(normalized)), key=normalized.__getitem__)
    minimum = min(normalized)
    half_height = minimum + (normalized[peak_index] - minimum) / 2
    above_half = [index for index, value in enumerate(normalized) if value >= half_height]
    after_peak = normalized[peak_index + 1 :]
    notch_index = peak_index + 1 + min(range(len(after_peak)), key=after_peak.__getitem__) if after_peak else None
    denominator = max(1, len(normalized) - 1)
    return {
        "normalized_peak_phase": peak_index / denominator,
        "normalized_rise_time_ratio": peak_index / denominator,
        "normalized_half_width_ratio": (above_half[-1] - above_half[0] + 1) / len(normalized) if above_half else None,
        "normalized_notch_phase": notch_index / denominator if notch_index is not None else None,
    }


def phase_rmssd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    differences = [values[index] - values[index - 1] for index in range(1, len(values))]
    return math.sqrt(sum(value * value for value in differences) / len(differences))


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
    residual_entropy = normalized_entropy(residual)

    return {
        "preview_point_count": len(values),
        "pulse_energy": pulse_energy,
        "residual_fluctuation": residual_fluctuation,
        "residual_std": residual_std,
        "residual_cv": (residual_std or 0.0) / detrended_std if detrended_std else None,
        "residual_energy_ratio": residual_energy_ratio,
        "residual_entropy": residual_entropy,
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


def classify_channel_metrics(metrics: dict[str, Any], energy_ratio_to_median: float | None = None) -> dict[str, Any]:
    preview_count = safe_float(metrics.get("preview_point_count")) or 0
    coherence = safe_float(metrics.get("template_coherence")) or 0.0
    snr = safe_float(metrics.get("periodic_snr")) or 0.0
    fluctuation = safe_float(metrics.get("residual_fluctuation")) or 1.0
    if preview_count < 16:
        suspicion = 100.0
        channel_label = "insufficient_preview"
    else:
        flat_penalty = clamp(((0.35 - (energy_ratio_to_median or 0.0)) / 0.35) * 45, 0, 45) if energy_ratio_to_median is not None else 20.0
        periodic_penalty = clamp(((0.18 - coherence) / 0.18) * 35, 0, 35)
        snr_penalty = clamp(((0.15 - snr) / 0.15) * 20, 0, 20)
        fluctuation_penalty = clamp((fluctuation - 0.7) * 20, 0, 15)
        suspicion = flat_penalty + periodic_penalty + snr_penalty + fluctuation_penalty
        if suspicion >= 60:
            channel_label = "suspected_misalignment"
        elif snr < 0.08 or coherence < 0.08:
            channel_label = "low_snr"
        else:
            channel_label = "valid"

    bpm = safe_float(metrics.get("estimated_pulse_rate_bpm"))
    consistency = safe_float(metrics.get("period_consistency_score")) or 0.0
    plausible_bpm = bpm is None or 35 <= bpm <= 180
    if channel_label == "suspected_misalignment":
        periodic_label = "suspected_misalignment"
    elif snr >= 0.35 and coherence >= 0.25 and consistency >= 0.25 and plausible_bpm:
        periodic_label = "clear_periodic"
    elif snr >= 0.08 and coherence >= 0.08 and plausible_bpm:
        periodic_label = "weak_periodic"
    else:
        periodic_label = "non_periodic_or_noise"

    return {
        "alignment_suspicion_score": round(suspicion, 3),
        "channel_validity_label": channel_label,
        "periodic_signal_label": periodic_label,
    }


def window_preview_segments(point_count: int, dominant_lag: int | None = None) -> list[tuple[int, int]]:
    if point_count < 32:
        return []
    preferred = (dominant_lag or 10) * 4
    window_size = int(min(point_count, max(32, preferred)))
    if point_count >= 96:
        window_size = min(window_size, max(32, point_count // 2))
    step = max(8, window_size // 2)
    segments = []
    start = 0
    while start + window_size <= point_count:
        segments.append((start, start + window_size))
        start += step
    if segments and segments[-1][1] < point_count:
        tail = (max(0, point_count - window_size), point_count)
        if tail != segments[-1]:
            segments.append(tail)
    if not segments:
        segments.append((0, point_count))
    return segments


def window_quality_score(metrics: dict[str, Any], alignment_suspicion_score: float) -> float:
    return clamp(
        (safe_float(metrics.get("template_explained_variance_ratio")) or 0.0) * 35
        + (safe_float(metrics.get("template_coherence")) or 0.0) * 30
        + min(1.0, safe_float(metrics.get("periodic_snr")) or 0.0) * 25
        - (safe_float(metrics.get("residual_energy_ratio")) or 1.0) * 15
        - alignment_suspicion_score * 0.20
    )


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
        "residual_entropy",
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


def analyze_windowed_pattern_stability(dataset_dir: Path, feature_matrix: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = read_jsonl(dataset_dir / "waveform_manifest.jsonl")
    if not rows:
        return pd.DataFrame(), pd.DataFrame()

    metadata = waveform_metadata(feature_matrix)
    measurement_meta = metadata.set_index("measurement_id").to_dict(orient="index") if not metadata.empty else {}
    records = []
    for row in rows:
        values = extract_preview_values(row)
        channel = standard_channel_name(row.get("channel_name"))
        if channel not in {*CHANNEL_ORDER, "overall"}:
            continue
        summary = parse_json_value(row.get("summary_json"), {})
        summary = summary if isinstance(summary, dict) else {}
        sample_count = safe_float(row.get("sample_count")) or safe_float(summary.get("count"))
        sampling_rate = safe_float(row.get("sampling_rate")) or safe_float(summary.get("sampling_rate"))
        duration_seconds = safe_float(row.get("duration_seconds")) or safe_float(summary.get("duration_seconds"))
        if duration_seconds is None and sample_count and sampling_rate:
            duration_seconds = sample_count / sampling_rate
        meta = measurement_meta.get(row.get("measurement_id"), {})
        if duration_seconds is None:
            duration_seconds = safe_float(meta.get("duration_seconds"))

        full_metrics = decompose_preview_signal(values, duration_seconds)
        segments = window_preview_segments(len(values), safe_float(full_metrics.get("dominant_lag_preview_points")))
        seconds_per_point = preview_seconds_per_point(duration_seconds, len(values))
        for window_index, (start, end) in enumerate(segments):
            window_values = values[start:end]
            window_duration = (end - start - 1) * seconds_per_point if seconds_per_point else None
            metrics = decompose_preview_signal(window_values, window_duration)
            compact_metrics = {key: value for key, value in metrics.items() if key not in {"template_vector", "normalized_template_vector", "residual_vector"}}
            records.append(
                {
                    "window_id": f"{row.get('waveform_asset_id') or row.get('measurement_id')}:{window_index}",
                    "measurement_id": row.get("measurement_id"),
                    "waveform_asset_id": row.get("waveform_asset_id"),
                    "user_id": meta.get("user_id"),
                    "source_vendor": meta.get("source_vendor"),
                    "device_id": meta.get("device_id"),
                    "visit_slot": meta.get("visit_slot"),
                    "start_time": meta.get("start_time"),
                    "channel_name": row.get("channel_name"),
                    "standard_channel_name": channel,
                    "window_index": window_index,
                    "start_preview_index": start,
                    "end_preview_index": end - 1,
                    "start_offset_seconds": round(start * seconds_per_point, 6) if seconds_per_point else None,
                    "end_offset_seconds": round((end - 1) * seconds_per_point, 6) if seconds_per_point else None,
                    "duration_seconds": round(window_duration, 6) if window_duration else None,
                    **compact_metrics,
                }
            )

    window_features = pd.DataFrame(records)
    if window_features.empty:
        return pd.DataFrame(), pd.DataFrame()

    window_features["pulse_energy"] = pd.to_numeric(window_features["pulse_energy"], errors="coerce")
    median_energy = window_features.groupby("standard_channel_name")["pulse_energy"].transform("median")
    window_features["channel_energy_ratio_to_median"] = window_features["pulse_energy"] / median_energy.where(median_energy > 0)

    labels = []
    suspicion_scores = []
    quality_scores = []
    for _, row in window_features.iterrows():
        metrics = row.to_dict()
        label_info = classify_channel_metrics(metrics, safe_float(row.get("channel_energy_ratio_to_median")))
        suspicion = safe_float(label_info.get("alignment_suspicion_score")) or 0.0
        labels.append(label_info)
        suspicion_scores.append(suspicion)
        quality_scores.append(round(window_quality_score(metrics, suspicion), 3))
    window_features["alignment_suspicion_score"] = suspicion_scores
    window_features["quality_score"] = quality_scores
    window_features["channel_validity_label"] = [label["channel_validity_label"] for label in labels]
    window_features["periodic_signal_label"] = [label["periodic_signal_label"] for label in labels]

    numeric_columns = window_features.select_dtypes(include=["number"]).columns
    window_features[numeric_columns] = window_features[numeric_columns].round(6)
    return window_features, summarize_measurement_pattern_stability(window_features)


def summarize_measurement_pattern_stability(window_features: pd.DataFrame) -> pd.DataFrame:
    if window_features.empty:
        return pd.DataFrame()

    rows = []
    for measurement_id, group in window_features.groupby("measurement_id", dropna=False):
        core = group[group["standard_channel_name"].isin(CHANNEL_ORDER)].copy()
        usable = core if not core.empty else group.copy()
        quality = pd.to_numeric(usable["quality_score"], errors="coerce")
        valid_window_count = int((usable["channel_validity_label"] == "valid").sum())
        total_window_count = int(len(usable))
        avg_quality = float(quality.mean()) if quality.notna().any() else 0.0
        best_quality = float(quality.max()) if quality.notna().any() else 0.0

        per_window_quality = usable.groupby("window_index")["quality_score"].mean()
        best_window_index = int(per_window_quality.idxmax()) if not per_window_quality.empty else None
        best_rows = usable[usable["window_index"] == best_window_index] if best_window_index is not None else usable.iloc[0:0]
        best_start = pd.to_numeric(best_rows["start_offset_seconds"], errors="coerce").min() if not best_rows.empty else None
        best_end = pd.to_numeric(best_rows["end_offset_seconds"], errors="coerce").max() if not best_rows.empty else None

        channel_spreads = []
        for _, window_group in usable.groupby("window_index"):
            channel_quality = pd.to_numeric(window_group["quality_score"], errors="coerce").dropna()
            if len(channel_quality) >= 2:
                channel_spreads.append(float(channel_quality.max() - channel_quality.min()))
        channel_drift = sum(channel_spreads) / len(channel_spreads) if channel_spreads else 0.0

        ordered_window_quality = [float(value) for value in per_window_quality.sort_index().dropna().tolist()]
        posture_shift = (
            sum(abs(ordered_window_quality[index] - ordered_window_quality[index - 1]) for index in range(1, len(ordered_window_quality)))
            / (len(ordered_window_quality) - 1)
            if len(ordered_window_quality) >= 2
            else 0.0
        )
        valid_fraction = valid_window_count / total_window_count if total_window_count else 0.0
        pattern_stability = clamp(avg_quality * 0.55 + best_quality * 0.35 + valid_fraction * 10 - channel_drift * 0.4 - posture_shift * 0.4)
        if total_window_count < 3:
            label = "insufficient_windows"
        elif pattern_stability >= 60 and best_quality >= 50 and valid_window_count >= 3:
            label = "stable_valid"
        elif best_quality >= 45 and valid_window_count >= 1:
            label = "local_valid_segment"
        else:
            label = "unstable_or_noisy"

        first = usable.iloc[0]
        rows.append(
            {
                "measurement_id": measurement_id,
                "user_id": first.get("user_id"),
                "source_vendor": first.get("source_vendor"),
                "device_id": first.get("device_id"),
                "visit_slot": first.get("visit_slot"),
                "start_time": first.get("start_time"),
                "valid_window_count": valid_window_count,
                "total_window_count": total_window_count,
                "avg_window_quality_score": round(avg_quality, 3),
                "pattern_stability_score": round(pattern_stability, 3),
                "best_pattern_window_index": best_window_index,
                "best_segment_start_time": round(float(best_start), 6) if pd.notna(best_start) else None,
                "best_segment_end_time": round(float(best_end), 6) if pd.notna(best_end) else None,
                "best_segment_duration": round(float(best_end - best_start), 6) if pd.notna(best_start) and pd.notna(best_end) else None,
                "best_segment_quality_score": round(best_quality, 3),
                "channel_specific_drift_score": round(clamp(channel_drift), 3),
                "global_posture_shift_score": round(clamp(posture_shift), 3),
                "pattern_validity_label": label,
            }
        )
    return pd.DataFrame(rows)


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


def raw_waveform_index(raw_pulse_root: Path) -> dict[str, Path]:
    if not raw_pulse_root.exists():
        return {}
    return {path.stem: path for path in raw_pulse_root.rglob("*.json")}


def raw_channel_values(payload: dict[str, Any], source_field: str) -> list[float]:
    raw_values = parse_json_value(payload.get(source_field), [])
    if not isinstance(raw_values, list):
        return []
    values = [safe_float(value) for value in raw_values]
    return [value for value in values if value is not None]


def detrended_raw_autocorrelation(values: list[float]) -> tuple[np.ndarray, np.ndarray] | tuple[None, None]:
    if len(values) < 32:
        return None, None
    signal = np.asarray(values, dtype=float)
    positions = np.arange(signal.size, dtype=float)
    slope, intercept = np.polyfit(positions, signal, 1)
    detrended = signal - (slope * positions + intercept)
    centered = detrended - float(detrended.mean())
    energy = float(np.dot(centered, centered))
    if energy <= 1e-12:
        return None, None
    fft_size = 1 << (2 * signal.size - 1).bit_length()
    spectrum = np.fft.rfft(centered, fft_size)
    acf = np.fft.irfft(spectrum * np.conjugate(spectrum), fft_size)[: signal.size] / energy
    return centered, acf


def raw_template_metrics_at_lag(signal: np.ndarray, acf: np.ndarray, lag: int, sampling_rate: float) -> dict[str, Any] | None:
    if lag < 2 or lag >= signal.size:
        return None
    phase = np.arange(signal.size) % lag
    counts = np.bincount(phase, minlength=lag)
    sums = np.bincount(phase, weights=signal, minlength=lag)
    template = sums / np.maximum(counts, 1)
    reconstructed = template[phase]
    residual = signal - reconstructed
    signal_variance = float(np.var(signal))
    template_variance = float(np.var(reconstructed))
    residual_variance = float(np.var(residual))
    return {
        "lag_samples": int(lag),
        "period_seconds": float(lag / sampling_rate),
        "pulse_rate_bpm": float(sampling_rate * 60.0 / lag),
        "coherence": float(acf[lag]),
        "periodic_snr": float(template_variance / max(residual_variance, 1e-12)),
        "template_explained_variance_ratio": float(1.0 - residual_variance / max(signal_variance, 1e-12)),
        "template_vector": template.tolist(),
    }


def raw_period_candidate(
    signal: np.ndarray,
    acf: np.ndarray,
    sampling_rate: float,
    center_lag: float,
    search_band: float,
) -> dict[str, Any] | None:
    low = max(2, int(round(center_lag * (1.0 - search_band))))
    high = min(signal.size - 1, int(round(center_lag * (1.0 + search_band))))
    if high < low:
        return None
    lag = low + int(np.argmax(acf[low : high + 1]))
    return raw_template_metrics_at_lag(signal, acf, lag, sampling_rate)


def raw_free_period_candidate(signal: np.ndarray, acf: np.ndarray, sampling_rate: float) -> dict[str, Any] | None:
    low = max(2, int(round(sampling_rate * 60.0 / 180.0)))
    high = min(signal.size - 1, int(round(sampling_rate * 60.0 / 20.0)))
    if high < low:
        return None
    lag = low + int(np.argmax(acf[low : high + 1]))
    return raw_template_metrics_at_lag(signal, acf, lag, sampling_rate)


def prefixed_period_metrics(prefix: str, metrics: dict[str, Any] | None) -> dict[str, Any]:
    return {
        f"{prefix}_lag_samples": metrics.get("lag_samples") if metrics else None,
        f"{prefix}_seconds": metrics.get("period_seconds") if metrics else None,
        f"{prefix}_pulse_rate_bpm": metrics.get("pulse_rate_bpm") if metrics else None,
        f"{prefix}_coherence": metrics.get("coherence") if metrics else None,
        f"{prefix}_periodic_snr": metrics.get("periodic_snr") if metrics else None,
        f"{prefix}_template_explained_variance_ratio": metrics.get("template_explained_variance_ratio") if metrics else None,
    }


def summarize_period_experiment(experiment_rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(experiment_rows)
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for channel_name in ["all", *CHANNEL_ORDER]:
        channel_frame = frame if channel_name == "all" else frame[frame["standard_channel_name"] == channel_name]
        for arm, group in channel_frame.groupby("experiment_arm", sort=False):
            error = pd.to_numeric(group["period_error_ratio"], errors="coerce").dropna()
            ratio = pd.to_numeric(group["period_ratio_to_pulse_rate"], errors="coerce").dropna()
            coherence = pd.to_numeric(group["template_coherence"], errors="coerce").dropna()
            periodic_snr = pd.to_numeric(group["periodic_snr"], errors="coerce").dropna()
            rows.append(
                {
                    "experiment_arm": arm,
                    "standard_channel_name": channel_name,
                    "sample_count": int(len(group)),
                    "median_abs_period_error_ratio": float(error.median()) if not error.empty else None,
                    "within_10_percent_rate": float((error <= 0.10).mean()) if not error.empty else None,
                    "within_20_percent_rate": float((error <= 0.20).mean()) if not error.empty else None,
                    "double_period_rate": float(((ratio >= 1.8) & (ratio <= 2.2)).mean()) if not ratio.empty else None,
                    "median_template_coherence": float(coherence.median()) if not coherence.empty else None,
                    "median_periodic_snr": float(periodic_snr.median()) if not periodic_snr.empty else None,
                }
            )
    return pd.DataFrame(rows)


def select_promoted_period_arm(experiment: pd.DataFrame) -> str:
    default_arm = "rate_guided_band_0.10"
    if experiment.empty:
        return default_arm
    candidates = experiment[
        (experiment["standard_channel_name"] == "all")
        & experiment["experiment_arm"].str.startswith("rate_guided_band_", na=False)
    ].copy()
    candidates = candidates[pd.to_numeric(candidates["within_20_percent_rate"], errors="coerce") >= 0.95]
    if candidates.empty:
        return default_arm
    candidates = candidates.sort_values(
        ["median_abs_period_error_ratio", "median_template_coherence"],
        ascending=[True, False],
    )
    return str(candidates.iloc[0]["experiment_arm"])


def analyze_pulse_rate_period_consistency(
    feature_matrix: pd.DataFrame,
    raw_pulse_root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if feature_matrix.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    raw_index = raw_waveform_index(raw_pulse_root)
    if not raw_index:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    prepared = []
    experiment_rows = []
    for source_row in feature_matrix.to_dict(orient="records"):
        source_measurement_id = str(source_row.get("source_measurement_id") or "").strip()
        pulse_rate = safe_float(source_row.get("pulse_rate"))
        raw_path = raw_index.get(source_measurement_id)
        if not raw_path or not pulse_rate or pulse_rate <= 0:
            continue
        try:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sampling_rate = safe_float(source_row.get("sampling_rate")) or safe_float(payload.get("SampleRate")) or 500.0
        expected_period_seconds = 60.0 / pulse_rate
        expected_lag_samples = expected_period_seconds * sampling_rate
        for channel_name, source_field in RAW_CHANNEL_FIELDS.items():
            values = raw_channel_values(payload, source_field)
            signal, acf = detrended_raw_autocorrelation(values)
            if signal is None or acf is None:
                continue
            free_candidate = raw_free_period_candidate(signal, acf, sampling_rate)
            band_candidates = {}
            for band in PERIOD_SEARCH_BANDS:
                band_key = f"rate_guided_band_{band:.2f}"
                candidates = {
                    "half_period_candidate": raw_period_candidate(signal, acf, sampling_rate, expected_lag_samples * 0.5, band),
                    "nominal_period_candidate": raw_period_candidate(signal, acf, sampling_rate, expected_lag_samples, band),
                    "double_period_candidate": raw_period_candidate(signal, acf, sampling_rate, expected_lag_samples * 2.0, band),
                }
                band_candidates[band_key] = candidates
                selected = candidates["nominal_period_candidate"]
                if selected:
                    ratio = selected["period_seconds"] / expected_period_seconds
                    experiment_rows.append(
                        {
                            "experiment_arm": band_key,
                            "standard_channel_name": channel_name,
                            "period_ratio_to_pulse_rate": ratio,
                            "period_error_ratio": abs(ratio - 1.0),
                            "template_coherence": selected["coherence"],
                            "periodic_snr": selected["periodic_snr"],
                        }
                    )
            if free_candidate:
                ratio = free_candidate["period_seconds"] / expected_period_seconds
                experiment_rows.append(
                    {
                        "experiment_arm": "free_acf_baseline",
                        "standard_channel_name": channel_name,
                        "period_ratio_to_pulse_rate": ratio,
                        "period_error_ratio": abs(ratio - 1.0),
                        "template_coherence": free_candidate["coherence"],
                        "periodic_snr": free_candidate["periodic_snr"],
                    }
                )
            prepared.append(
                {
                    "source_row": source_row,
                    "source_measurement_id": source_measurement_id,
                    "raw_path": raw_path,
                    "standard_channel_name": channel_name,
                    "sampling_rate": sampling_rate,
                    "raw_sample_count": len(values),
                    "pulse_rate_bpm": pulse_rate,
                    "expected_period_seconds": expected_period_seconds,
                    "expected_lag_samples": expected_lag_samples,
                    "free_candidate": free_candidate,
                    "band_candidates": band_candidates,
                }
            )

    experiment = summarize_period_experiment(experiment_rows)
    promoted_arm = select_promoted_period_arm(experiment)
    if not experiment.empty:
        experiment["experiment_decision"] = experiment["experiment_arm"].map(
            lambda arm: "promote_period_alignment_only" if arm == promoted_arm else "baseline" if arm == "free_acf_baseline" else "not_promoted"
        )
        experiment["promoted_arm"] = promoted_arm

    rows = []
    template_rows = []
    for item in prepared:
        candidates = item["band_candidates"].get(promoted_arm) or item["band_candidates"]["rate_guided_band_0.10"]
        nominal = candidates["nominal_period_candidate"]
        if nominal is None:
            continue
        half = candidates["half_period_candidate"]
        double = candidates["double_period_candidate"]
        evidence_candidates = {
            "half_period_candidate": half,
            "nominal_period_candidate": nominal,
            "double_period_candidate": double,
        }
        evidence_candidates = {name: metrics for name, metrics in evidence_candidates.items() if metrics is not None}
        morphology_candidate_type, morphology_candidate = max(
            evidence_candidates.items(),
            key=lambda candidate: candidate[1]["coherence"],
        )
        period_ratio = nominal["period_seconds"] / item["expected_period_seconds"]
        period_error = abs(period_ratio - 1.0)
        half_margin = (half["coherence"] - nominal["coherence"]) if half else None
        double_margin = (double["coherence"] - nominal["coherence"]) if double else None
        half_dominant = bool(half and half["coherence"] >= 0.20 and (half_margin or 0.0) >= 0.10)
        double_dominant = bool(double and double["coherence"] >= 0.20 and (double_margin or 0.0) >= 0.10)
        if double_dominant:
            label = "double_period_dominant"
        elif half_dominant:
            label = "half_period_dominant"
        elif nominal["coherence"] >= 0.10 and period_error <= 0.20:
            label = "pulse_rate_consistent"
        else:
            label = "pulse_rate_locked_low_coherence"
        source_row = item["source_row"]
        common_template_fields = {
            "measurement_id": source_row.get("measurement_id"),
            "source_measurement_id": item["source_measurement_id"],
            "user_id": source_row.get("user_id"),
            "source_vendor": source_row.get("source_vendor"),
            "device_id": source_row.get("device_id"),
            "visit_slot": source_row.get("visit_slot"),
            "start_time": source_row.get("start_time"),
            "standard_channel_name": item["standard_channel_name"],
            "sampling_rate": item["sampling_rate"],
            "pulse_rate_bpm": item["pulse_rate_bpm"],
            "expected_period_seconds": item["expected_period_seconds"],
            "period_selection_method": promoted_arm,
            "period_consistency_version": PERIOD_CONSISTENCY_VERSION,
            "input_basis": "raw_waveform",
        }
        for template_role, candidate_type, candidate in [
            ("pulse_rate_guided_template", "nominal_period_candidate", nominal),
            ("morphology_dominant_template", morphology_candidate_type, morphology_candidate),
        ]:
            template_rows.append(
                {
                    **common_template_fields,
                    "template_id": f"{source_row.get('measurement_id')}:{item['standard_channel_name']}:{template_role}",
                    "template_role": template_role,
                    "candidate_type": candidate_type,
                    "template_period_lag_samples": candidate["lag_samples"],
                    "template_period_seconds": candidate["period_seconds"],
                    "template_pulse_rate_bpm": candidate["pulse_rate_bpm"],
                    "template_coherence": candidate["coherence"],
                    "template_periodic_snr": candidate["periodic_snr"],
                    "template_explained_variance_ratio": candidate["template_explained_variance_ratio"],
                    "template_vector_json": json.dumps(round_vector(candidate["template_vector"]), ensure_ascii=False),
                }
            )
        rows.append(
            {
                "measurement_id": source_row.get("measurement_id"),
                "source_measurement_id": item["source_measurement_id"],
                "user_id": source_row.get("user_id"),
                "source_vendor": source_row.get("source_vendor"),
                "device_id": source_row.get("device_id"),
                "visit_slot": source_row.get("visit_slot"),
                "start_time": source_row.get("start_time"),
                "quality_status": source_row.get("quality_status"),
                "standard_channel_name": item["standard_channel_name"],
                "raw_storage_path": str(item["raw_path"]),
                "raw_sample_count": item["raw_sample_count"],
                "sampling_rate": item["sampling_rate"],
                "pulse_rate_bpm": item["pulse_rate_bpm"],
                "expected_period_seconds": item["expected_period_seconds"],
                "expected_lag_samples": item["expected_lag_samples"],
                "selected_period_lag_samples": nominal["lag_samples"],
                "selected_period_seconds": nominal["period_seconds"],
                "selected_period_bpm": nominal["pulse_rate_bpm"],
                "selected_period_ratio_to_pulse_rate": period_ratio,
                "selected_period_error_ratio": period_error,
                "pulse_rate_period_consistency": max(0.0, 1.0 - period_error),
                "pulse_rate_period_consistency_label": label,
                "selected_template_coherence": nominal["coherence"],
                "selected_periodic_snr": nominal["periodic_snr"],
                "selected_template_explained_variance_ratio": nominal["template_explained_variance_ratio"],
                "morphology_dominant_candidate_type": morphology_candidate_type,
                "morphology_dominant_period_seconds": morphology_candidate["period_seconds"],
                "morphology_dominant_coherence": morphology_candidate["coherence"],
                "half_period_dominance_margin": half_margin,
                "double_period_dominance_margin": double_margin,
                "half_period_dominant_flag": half_dominant,
                "double_period_dominant_flag": double_dominant,
                "period_selection_method": promoted_arm,
                "period_consistency_version": PERIOD_CONSISTENCY_VERSION,
                "input_basis": "raw_waveform",
                **prefixed_period_metrics("half_period_candidate", half),
                **prefixed_period_metrics("nominal_period_candidate", nominal),
                **prefixed_period_metrics("double_period_candidate", double),
                **prefixed_period_metrics("free_acf_candidate", item["free_candidate"]),
            }
        )
    consistency = pd.DataFrame(rows)
    raw_templates = pd.DataFrame(template_rows)
    for frame in [consistency, experiment, raw_templates]:
        if not frame.empty:
            numeric_columns = frame.select_dtypes(include=["number"]).columns
            frame[numeric_columns] = frame[numeric_columns].round(6)
    return consistency, experiment, raw_templates


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
                "residual_entropy": metrics.get("residual_entropy"),
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


def analyze_beat_level_features(dataset_dir: Path, feature_matrix: pd.DataFrame) -> pd.DataFrame:
    rows = read_jsonl(dataset_dir / "waveform_manifest.jsonl")
    if not rows:
        return pd.DataFrame()

    metadata = waveform_metadata(feature_matrix)
    measurement_meta = metadata.set_index("measurement_id").to_dict(orient="index") if not metadata.empty else {}
    candidates: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        channel = standard_channel_name(row.get("channel_name"))
        if channel not in CHANNEL_ORDER:
            continue
        values = extract_preview_values(row)
        summary = parse_json_value(row.get("summary_json"), {})
        summary = summary if isinstance(summary, dict) else {}
        sample_count = safe_float(row.get("sample_count")) or safe_float(summary.get("count"))
        sampling_rate = safe_float(row.get("sampling_rate")) or safe_float(summary.get("sampling_rate"))
        duration_seconds = safe_float(row.get("duration_seconds")) or safe_float(summary.get("duration_seconds"))
        if duration_seconds is None and sample_count and sampling_rate:
            duration_seconds = sample_count / sampling_rate
        meta = measurement_meta.get(row.get("measurement_id"), {})
        if duration_seconds is None:
            duration_seconds = safe_float(meta.get("duration_seconds"))
        candidates.setdefault(row.get("measurement_id"), []).append(
            {
                "source": row,
                "channel": channel,
                "values": values,
                "duration_seconds": duration_seconds,
                "meta": meta,
                "metrics": decompose_preview_signal(values, duration_seconds),
            }
        )

    records = []
    for measurement_id, measurement_rows in candidates.items():
        anchors = [
            item for item in measurement_rows
            if safe_float(item["metrics"].get("dominant_lag_preview_points")) is not None
        ]
        if not anchors:
            continue
        anchor = max(
            anchors,
            key=lambda item: (
                safe_float(item["metrics"].get("periodic_snr")) or 0.0,
                safe_float(item["metrics"].get("pulse_energy")) or 0.0,
            ),
        )
        lag_points = int(safe_float(anchor["metrics"].get("dominant_lag_preview_points")) or 0)
        if lag_points < 3:
            continue
        for item in measurement_rows:
            row = item["source"]
            values = item["values"]
            duration_seconds = item["duration_seconds"]
            meta = item["meta"]
            channel = item["channel"]
            detrended = linear_detrend(values)
            template, _, _ = build_periodic_template(detrended, lag_points)
            if len(template) < 3:
                continue
            seconds_per_point = preview_seconds_per_point(duration_seconds, len(values))
            for beat_index, start in enumerate(range(0, len(values) - lag_points + 1, lag_points)):
                cycle = values[start : start + lag_points]
                fit = fit_beat_to_template(cycle, template)
                records.append(
                    {
                        "beat_id": f"{row.get('waveform_asset_id') or measurement_id}:{beat_index}",
                        "measurement_id": measurement_id,
                        "waveform_asset_id": row.get("waveform_asset_id"),
                        "user_id": meta.get("user_id"),
                        "source_vendor": meta.get("source_vendor"),
                        "device_id": meta.get("device_id"),
                        "visit_slot": meta.get("visit_slot"),
                        "start_time": meta.get("start_time"),
                        "standard_channel_name": channel,
                        "phase_reference_channel": anchor["channel"],
                        "unified_lag_preview_points": lag_points,
                        "beat_index": beat_index,
                        "start_preview_index": start,
                        "end_preview_index": start + lag_points - 1,
                        "start_offset_seconds": start * seconds_per_point if seconds_per_point else None,
                        "end_offset_seconds": (start + lag_points - 1) * seconds_per_point if seconds_per_point else None,
                        "cycle_point_count": lag_points,
                        **fit,
                        **normalized_shape_features(cycle),
                    }
                )
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame

    frame["baseline_deviation_z"] = pd.NA
    frame["amplitude_deviation_z"] = pd.NA
    frame["pressure_artifact_score"] = pd.NA
    for _, group in frame.groupby(["measurement_id", "standard_channel_name"], dropna=False):
        baseline_values = pd.to_numeric(group["baseline_offset"], errors="coerce").dropna().tolist()
        amplitude_values = pd.to_numeric(group["amplitude_scale"], errors="coerce").dropna().tolist()
        baseline_center, baseline_scale = robust_center_scale(baseline_values)
        amplitude_center, amplitude_scale = robust_center_scale(amplitude_values)
        for index in group.index:
            baseline_value = safe_float(frame.at[index, "baseline_offset"])
            amplitude_value = safe_float(frame.at[index, "amplitude_scale"])
            fit_r2 = safe_float(frame.at[index, "template_fit_r2"]) or 0.0
            baseline_z = (baseline_value - baseline_center) / baseline_scale if baseline_value is not None and baseline_center is not None and baseline_scale else None
            amplitude_z = (amplitude_value - amplitude_center) / amplitude_scale if amplitude_value is not None and amplitude_center is not None and amplitude_scale else None
            baseline_penalty = min(abs(baseline_z or 0.0) / 4, 1)
            amplitude_penalty = min(abs(amplitude_z or 0.0) / 4, 1)
            negative_scale_penalty = 1.0 if amplitude_value is not None and amplitude_value <= 0 else 0.0
            artifact = clamp(baseline_penalty * 0.3 + amplitude_penalty * 0.3 + (1 - fit_r2) * 0.3 + negative_scale_penalty * 0.1, 0, 1)
            frame.at[index, "baseline_deviation_z"] = baseline_z
            frame.at[index, "amplitude_deviation_z"] = amplitude_z
            frame.at[index, "pressure_artifact_score"] = artifact
    frame["feature_version"] = "pulse_standard_features_v1"
    numeric_columns = frame.select_dtypes(include=["number"]).columns
    frame[numeric_columns] = frame[numeric_columns].round(6)
    return frame


def analyze_channel_features(channel_quality: pd.DataFrame, beat_features: pd.DataFrame) -> pd.DataFrame:
    if channel_quality.empty:
        return pd.DataFrame()
    rows = []
    core = channel_quality[channel_quality["standard_channel_name"].isin(CHANNEL_ORDER)]
    for _, source in core.iterrows():
        beats = beat_features[beat_features["waveform_asset_id"] == source.get("waveform_asset_id")] if not beat_features.empty else pd.DataFrame()
        phases = pd.to_numeric(beats.get("phase_shift_ratio", pd.Series(dtype=float)), errors="coerce").dropna().tolist()
        row = {
            "measurement_id": source.get("measurement_id"),
            "waveform_asset_id": source.get("waveform_asset_id"),
            "user_id": source.get("user_id"),
            "source_vendor": source.get("source_vendor"),
            "device_id": source.get("device_id"),
            "visit_slot": source.get("visit_slot"),
            "start_time": source.get("start_time"),
            "standard_channel_name": source.get("standard_channel_name"),
            "periodic_snr": source.get("periodic_snr"),
            "pulse_energy": source.get("pulse_energy"),
            "template_coherence": source.get("template_coherence"),
            "alignment_suspicion_score": source.get("alignment_suspicion_score"),
            "channel_validity_label": source.get("channel_validity_label"),
            "beat_count": int(len(beats)),
            "phase_reference_channel": beats.iloc[0].get("phase_reference_channel") if not beats.empty else None,
            "unified_lag_preview_points": beats.iloc[0].get("unified_lag_preview_points") if not beats.empty else None,
            "baseline_offset_median": pd.to_numeric(beats.get("baseline_offset", pd.Series(dtype=float)), errors="coerce").median() if not beats.empty else None,
            "amplitude_scale_median": pd.to_numeric(beats.get("amplitude_scale", pd.Series(dtype=float)), errors="coerce").median() if not beats.empty else None,
            "template_fit_r2_mean": pd.to_numeric(beats.get("template_fit_r2", pd.Series(dtype=float)), errors="coerce").mean() if not beats.empty else None,
            "pressure_artifact_score_mean": pd.to_numeric(beats.get("pressure_artifact_score", pd.Series(dtype=float)), errors="coerce").mean() if not beats.empty else None,
            "phase_shift_mean": sum(phases) / len(phases) if phases else None,
            "phase_shift_sd": mean_std(phases)[1] if phases else None,
            "phase_shift_rmssd": phase_rmssd(phases),
            "normalized_peak_phase_mean": pd.to_numeric(beats.get("normalized_peak_phase", pd.Series(dtype=float)), errors="coerce").mean() if not beats.empty else None,
            "normalized_half_width_ratio_mean": pd.to_numeric(beats.get("normalized_half_width_ratio", pd.Series(dtype=float)), errors="coerce").mean() if not beats.empty else None,
            "residual_energy_ratio": source.get("residual_energy_ratio"),
            "residual_entropy": source.get("residual_entropy"),
            "dfa_alpha": source.get("dfa_alpha"),
            "feature_version": "pulse_standard_features_v1",
        }
        rows.append(row)
    frame = pd.DataFrame(rows)
    if not frame.empty:
        numeric_columns = frame.select_dtypes(include=["number"]).columns
        frame[numeric_columns] = frame[numeric_columns].round(6)
    return frame


def analyze_phase_variability_features(beat_features: pd.DataFrame) -> pd.DataFrame:
    if beat_features.empty:
        return pd.DataFrame()
    rows = []
    for keys, group in beat_features.groupby(["measurement_id", "waveform_asset_id", "user_id", "standard_channel_name"], dropna=False):
        phases = pd.to_numeric(group["phase_shift_ratio"], errors="coerce").dropna().tolist()
        if not phases:
            continue
        trend_slope, _ = linear_regression([float(index) for index in range(len(phases))], phases)
        baseline = pd.to_numeric(group["baseline_offset"], errors="coerce")
        amplitude = pd.to_numeric(group["amplitude_scale"], errors="coerce")
        phase_series = pd.to_numeric(group["phase_shift_ratio"], errors="coerce")
        rows.append(
            {
                "measurement_id": keys[0],
                "waveform_asset_id": keys[1],
                "user_id": keys[2],
                "standard_channel_name": keys[3],
                "phase_reference_channel": group.iloc[0].get("phase_reference_channel"),
                "unified_lag_preview_points": group.iloc[0].get("unified_lag_preview_points"),
                "beat_count": len(phases),
                "phase_shift_mean": sum(phases) / len(phases),
                "phase_shift_sd": mean_std(phases)[1],
                "phase_shift_rmssd": phase_rmssd(phases),
                "phase_shift_trend_slope": trend_slope,
                "phase_baseline_correlation": phase_series.corr(baseline),
                "phase_amplitude_correlation": phase_series.corr(amplitude),
                "phase_variability_interpretation": "requires_artifact_control",
                "feature_version": "pulse_standard_features_v1",
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        numeric_columns = frame.select_dtypes(include=["number"]).columns
        frame[numeric_columns] = frame[numeric_columns].round(6)
    return frame


def analyze_residual_fluctuation_features(decomposition: pd.DataFrame, beat_features: pd.DataFrame) -> pd.DataFrame:
    if decomposition.empty:
        return pd.DataFrame()
    rows = []
    for _, source in decomposition[decomposition["standard_channel_name"].isin(CHANNEL_ORDER)].iterrows():
        beats = beat_features[beat_features["waveform_asset_id"] == source.get("waveform_asset_id")] if not beat_features.empty else pd.DataFrame()
        fit_residual = pd.to_numeric(beats.get("fit_residual_energy_ratio", pd.Series(dtype=float)), errors="coerce")
        rows.append(
            {
                "measurement_id": source.get("measurement_id"),
                "waveform_asset_id": source.get("waveform_asset_id"),
                "user_id": source.get("user_id"),
                "standard_channel_name": source.get("standard_channel_name"),
                "residual_std": source.get("residual_std"),
                "residual_cv": source.get("residual_cv"),
                "residual_energy_ratio": source.get("residual_energy_ratio"),
                "residual_entropy": source.get("residual_entropy"),
                "residual_fluctuation": source.get("residual_fluctuation"),
                "residual_dfa_alpha": source.get("dfa_alpha"),
                "multi_scale_fluctuation_slope": source.get("multi_scale_fluctuation_slope"),
                "mean_beat_fit_residual_energy_ratio": fit_residual.mean() if fit_residual.notna().any() else None,
                "max_beat_fit_residual_energy_ratio": fit_residual.max() if fit_residual.notna().any() else None,
                "feature_version": "pulse_standard_features_v1",
            }
        )
    frame = pd.DataFrame(rows)
    if not frame.empty:
        numeric_columns = frame.select_dtypes(include=["number"]).columns
        frame[numeric_columns] = frame[numeric_columns].round(6)
    return frame


def vector_similarity(left: list[float], right: list[float]) -> float | None:
    count = min(len(left), len(right))
    if count < 3:
        return None
    left_values = left[:count]
    right_values = right[:count]
    left_mean, left_std = mean_std(left_values)
    right_mean, right_std = mean_std(right_values)
    if not left_std or not right_std:
        return None
    numerator = sum((a - (left_mean or 0.0)) * (b - (right_mean or 0.0)) for a, b in zip(left_values, right_values))
    return numerator / ((count - 1) * left_std * right_std)


def analyze_channel_structure_features(channel_features: pd.DataFrame, templates: pd.DataFrame) -> pd.DataFrame:
    if channel_features.empty:
        return pd.DataFrame()
    template_rows = templates[templates["template_type"] == "amplitude_normalized_template"] if not templates.empty else pd.DataFrame()
    rows = []
    for measurement_id, group in channel_features.groupby("measurement_id", dropna=False):
        by_channel = {row["standard_channel_name"]: row for _, row in group.iterrows()}
        energies = {channel: safe_float(by_channel[channel].get("pulse_energy")) for channel in CHANNEL_ORDER if channel in by_channel}
        total_energy = sum(value for value in energies.values() if value is not None)
        row: dict[str, Any] = {
            "measurement_id": measurement_id,
            "user_id": group.iloc[0].get("user_id"),
            "device_id": group.iloc[0].get("device_id"),
            "visit_slot": group.iloc[0].get("visit_slot"),
            "start_time": group.iloc[0].get("start_time"),
            "channel_count": int(len(group)),
            "channel_energy_total": total_energy if total_energy else None,
            "feature_version": "pulse_standard_features_v1",
        }
        for channel in CHANNEL_ORDER:
            energy = energies.get(channel)
            row[f"{channel}_energy_ratio"] = energy / total_energy if energy is not None and total_energy else None
        for left, right in [("cun", "guan"), ("cun", "chi"), ("guan", "chi")]:
            left_templates = template_rows[
                (template_rows["measurement_id"] == measurement_id) & (template_rows["standard_channel_name"] == left)
            ]
            right_templates = template_rows[
                (template_rows["measurement_id"] == measurement_id) & (template_rows["standard_channel_name"] == right)
            ]
            similarity = None
            if not left_templates.empty and not right_templates.empty:
                left_vector = parse_json_value(left_templates.iloc[0].get("template_vector_json"), [])
                right_vector = parse_json_value(right_templates.iloc[0].get("template_vector_json"), [])
                similarity = vector_similarity(left_vector, right_vector)
            row[f"{left}_{right}_template_similarity"] = similarity
            row[f"{left}_{right}_template_distance"] = 1 - similarity if similarity is not None else None
            left_phase = safe_float(by_channel[left].get("phase_shift_mean")) if left in by_channel else None
            right_phase = safe_float(by_channel[right].get("phase_shift_mean")) if right in by_channel else None
            row[f"{left}_{right}_phase_difference"] = left_phase - right_phase if left_phase is not None and right_phase is not None else None
        distances = [
            value for key, value in row.items() if key.endswith("_template_distance") and safe_float(value) is not None
        ]
        row["channel_morphology_distance_mean"] = sum(distances) / len(distances) if distances else None
        rows.append(row)
    frame = pd.DataFrame(rows)
    numeric_columns = frame.select_dtypes(include=["number"]).columns
    frame[numeric_columns] = frame[numeric_columns].round(6)
    return frame


def analyze_record_features(
    quality: pd.DataFrame,
    pattern_stability: pd.DataFrame,
    channel_features: pd.DataFrame,
    channel_structure: pd.DataFrame,
) -> pd.DataFrame:
    if quality.empty:
        return pd.DataFrame()
    channel_rows = []
    if not channel_features.empty:
        for measurement_id, group in channel_features.groupby("measurement_id", dropna=False):
            channel_rows.append(
                {
                    "measurement_id": measurement_id,
                    "standard_channel_count": int(len(group)),
                    "mean_template_fit_r2": pd.to_numeric(group["template_fit_r2_mean"], errors="coerce").mean(),
                    "mean_pressure_artifact_score": pd.to_numeric(group["pressure_artifact_score_mean"], errors="coerce").mean(),
                    "mean_phase_shift_sd": pd.to_numeric(group["phase_shift_sd"], errors="coerce").mean(),
                    "mean_residual_entropy": pd.to_numeric(group["residual_entropy"], errors="coerce").mean(),
                }
            )
    result = quality.copy()
    if channel_rows:
        result = result.merge(pd.DataFrame(channel_rows), on="measurement_id", how="left")
    if not pattern_stability.empty:
        columns = [
            "measurement_id",
            "pattern_stability_score",
            "best_segment_quality_score",
            "channel_specific_drift_score",
            "global_posture_shift_score",
            "pattern_validity_label",
        ]
        result = result.merge(pattern_stability[[column for column in columns if column in pattern_stability]], on="measurement_id", how="left")
    if not channel_structure.empty:
        result = result.merge(channel_structure, on="measurement_id", how="left", suffixes=("", "_structure"))
    result["feature_version"] = "pulse_standard_features_v1"
    numeric_columns = result.select_dtypes(include=["number"]).columns
    result[numeric_columns] = result[numeric_columns].round(6)
    return result


def analyze_standard_feature_audit(frames: dict[str, pd.DataFrame], quality: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for table_name, frame in frames.items():
        if frame.empty:
            continue
        audit_frame = frame.copy()
        if "signal_quality_score" not in audit_frame and "measurement_id" in audit_frame and not quality.empty:
            audit_frame = audit_frame.merge(
                quality[["measurement_id", "signal_quality_score"]],
                on="measurement_id",
                how="left",
            )
        for feature_name in frame.select_dtypes(include=["number"]).columns:
            values = pd.to_numeric(audit_frame[feature_name], errors="coerce")
            present = values.dropna()
            missing_rate = 1 - (len(present) / len(frame)) if len(frame) else 1.0
            outlier_rate = 0.0
            if len(present) >= 4:
                q1 = present.quantile(0.25)
                q3 = present.quantile(0.75)
                iqr = q3 - q1
                if iqr:
                    outlier_rate = float(((present < q1 - 1.5 * iqr) | (present > q3 + 1.5 * iqr)).mean())
            device_sensitivity = None
            if "device_id" in audit_frame and audit_frame["device_id"].nunique(dropna=True) >= 2:
                means = audit_frame.assign(_feature_value=values).groupby("device_id")["_feature_value"].mean().dropna()
                if len(means) >= 2 and means.mean():
                    device_sensitivity = float(means.std(ddof=0) / abs(means.mean()))
            quality_dependency = None
            if "signal_quality_score" in audit_frame:
                quality_values = pd.to_numeric(audit_frame["signal_quality_score"], errors="coerce")
                correlation = values.corr(quality_values)
                quality_dependency = abs(float(correlation)) if pd.notna(correlation) else None
            rows.append(
                {
                    "table_name": table_name,
                    "feature_name": feature_name,
                    "row_count": int(len(frame)),
                    "present_count": int(len(present)),
                    "missing_rate": round(float(missing_rate), 6),
                    "outlier_rate": round(outlier_rate, 6),
                    "device_sensitivity": round(device_sensitivity, 6) if device_sensitivity is not None else None,
                    "quality_dependency_score": round(quality_dependency, 6) if quality_dependency is not None else None,
                    "minimum": present.min() if not present.empty else None,
                    "maximum": present.max() if not present.empty else None,
                    "mean": present.mean() if not present.empty else None,
                    "feature_version": "pulse_standard_features_v1",
                }
            )
    result = pd.DataFrame(rows)
    if not result.empty:
        numeric_columns = result.select_dtypes(include=["number"]).columns
        result[numeric_columns] = result[numeric_columns].round(6)
    return result


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


def analyze_patient_quality_summary(quality: pd.DataFrame, channel_quality: pd.DataFrame) -> pd.DataFrame:
    if quality.empty or "user_id" not in quality:
        return pd.DataFrame()
    core_channels = channel_quality[channel_quality["standard_channel_name"].isin(CHANNEL_ORDER)].copy() if not channel_quality.empty else pd.DataFrame()
    rows = []
    for user_id, group in quality.dropna(subset=["user_id"]).groupby("user_id", dropna=False):
        measurement_count = int(len(group))
        row: dict[str, Any] = {
            "user_id": user_id,
            "measurement_count": measurement_count,
            "valid_measurement_count": int((group["measurement_validity_label"] == "valid").sum()),
            "partial_valid_measurement_count": int((group["measurement_validity_label"] == "partial_valid").sum()),
            "invalid_measurement_count": int((group["measurement_validity_label"] == "invalid").sum()),
            "valid_measurement_rate": round(float((group["measurement_validity_label"] == "valid").mean()), 6),
            "usable_measurement_rate": round(float(group["measurement_validity_label"].isin(["valid", "partial_valid"]).mean()), 6),
            "avg_signal_quality_score": round(float(pd.to_numeric(group["signal_quality_score"], errors="coerce").mean()), 6),
            "avg_overall_periodic_snr": round(float(pd.to_numeric(group["overall_periodic_snr"], errors="coerce").mean()), 6),
            "avg_stable_segment_ratio": round(float(pd.to_numeric(group["stable_segment_ratio"], errors="coerce").mean()), 6),
            "feature_version": "pulse_patient_quality_v1",
        }
        patient_channels = core_channels[core_channels["user_id"] == user_id] if not core_channels.empty else pd.DataFrame()
        for channel in CHANNEL_ORDER:
            selected = patient_channels[patient_channels["standard_channel_name"] == channel] if not patient_channels.empty else pd.DataFrame()
            total = len(selected)
            row[f"{channel}_channel_count"] = int(total)
            row[f"{channel}_valid_rate"] = round(float((selected["channel_validity_label"] == "valid").mean()), 6) if total else None
            row[f"{channel}_alignment_suspicion_rate"] = round(float((selected["channel_validity_label"] == "suspected_misalignment").mean()), 6) if total else None
        rows.append(row)
    return pd.DataFrame(rows)


def _patient_failure_pattern(group: pd.DataFrame, labels: set[str]) -> tuple[str, float]:
    patterns = []
    for _, measurement_rows in group.groupby("measurement_id", dropna=False):
        failed_channels = [
            channel
            for channel in CHANNEL_ORDER
            if not measurement_rows[
                (measurement_rows["standard_channel_name"] == channel)
                & (measurement_rows["channel_validity_label"].isin(labels))
            ].empty
        ]
        if failed_channels:
            patterns.append("+".join(failed_channels))
    if not patterns:
        return "none", 0.0
    counts = pd.Series(patterns).value_counts()
    return str(counts.index[0]), float(counts.iloc[0] / max(1, group["measurement_id"].nunique()))


def analyze_patient_device_fit_summary(channel_quality: pd.DataFrame) -> pd.DataFrame:
    if channel_quality.empty or "user_id" not in channel_quality:
        return pd.DataFrame()
    core = channel_quality[channel_quality["standard_channel_name"].isin(CHANNEL_ORDER)].dropna(subset=["user_id"]).copy()
    if core.empty:
        return pd.DataFrame()
    core["periodic_snr"] = pd.to_numeric(core["periodic_snr"], errors="coerce")
    core["channel_energy_ratio_to_median"] = pd.to_numeric(core["channel_energy_ratio_to_median"], errors="coerce")
    rows = []
    for user_id, group in core.groupby("user_id", dropna=False):
        measurement_count = int(group["measurement_id"].nunique())
        alignment_rates = {}
        for channel in CHANNEL_ORDER:
            selected = group[group["standard_channel_name"] == channel]
            alignment_rates[channel] = float((selected["channel_validity_label"] == "suspected_misalignment").mean()) if len(selected) else 0.0
        max_alignment_rate = max(alignment_rates.values()) if alignment_rates else 0.0
        low_snr_ratio = float((group["periodic_snr"] < 0.08).mean())
        low_energy_ratio = float((group["channel_energy_ratio_to_median"] < 0.35).mean())
        persistent_alignment_pattern, alignment_persistence = _patient_failure_pattern(group, {"suspected_misalignment"})
        failure_pattern, imbalance_persistence = _patient_failure_pattern(
            group,
            {"suspected_misalignment", "low_snr", "insufficient_preview"},
        )
        risk_score = 100 * (
            0.35 * max_alignment_rate
            + 0.25 * low_snr_ratio
            + 0.20 * low_energy_ratio
            + 0.20 * imbalance_persistence
        )
        if risk_score >= 60:
            risk_label = "high"
        elif risk_score >= 35:
            risk_label = "medium"
        else:
            risk_label = "low"
        rows.append(
            {
                "user_id": user_id,
                "measurement_count": measurement_count,
                "channel_row_count": int(len(group)),
                "device_count": int(group["device_id"].nunique(dropna=True)) if "device_id" in group else 0,
                "cun_alignment_suspicion_rate": round(alignment_rates["cun"], 6),
                "guan_alignment_suspicion_rate": round(alignment_rates["guan"], 6),
                "chi_alignment_suspicion_rate": round(alignment_rates["chi"], 6),
                "max_channel_alignment_suspicion_rate": round(max_alignment_rate, 6),
                "low_snr_channel_ratio": round(low_snr_ratio, 6),
                "low_energy_channel_ratio": round(low_energy_ratio, 6),
                "channel_imbalance_persistence_score": round(imbalance_persistence, 6),
                "persistent_channel_failure_pattern": failure_pattern,
                "persistent_alignment_pattern": persistent_alignment_pattern,
                "persistent_alignment_score": round(alignment_persistence, 6),
                "persistent_alignment_flag": bool(max_alignment_rate >= 0.5 or alignment_persistence >= 0.5),
                "patient_device_fit_risk_score": round(risk_score, 3),
                "device_fit_risk_label": risk_label,
                "wrist_circumference_available": False,
                "anthropometric_limitation": "wrist_circumference_not_available",
                "feature_version": "pulse_patient_device_fit_v1",
            }
        )
    return pd.DataFrame(rows).sort_values("patient_device_fit_risk_score", ascending=False).reset_index(drop=True)


BASELINE_FEATURE_COLUMNS = [
    "periodic_snr",
    "pulse_energy",
    "template_fit_r2_mean",
    "pressure_artifact_score_mean",
    "phase_shift_mean",
    "phase_shift_sd",
    "residual_energy_ratio",
    "residual_entropy",
    "dfa_alpha",
]


def _resample_template(values: list[float], point_count: int = 64) -> list[float]:
    if not values:
        return []
    if len(values) == 1:
        return [float(values[0])] * point_count
    source_x = np.linspace(0.0, 1.0, num=len(values))
    target_x = np.linspace(0.0, 1.0, num=point_count)
    return np.interp(target_x, source_x, np.asarray(values, dtype=float)).tolist()


def _median_mad(values: pd.Series) -> tuple[float | None, float | None]:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return None, None
    median = float(numeric.median())
    mad = float((numeric - median).abs().median())
    return median, mad


def _persistent_alignment_exclusions(patient_device_fit: pd.DataFrame) -> dict[str, set[str]]:
    exclusions: dict[str, set[str]] = {}
    if patient_device_fit.empty:
        return exclusions
    for _, row in patient_device_fit.iterrows():
        if not bool(row.get("persistent_alignment_flag")):
            continue
        pattern = str(row.get("persistent_alignment_pattern") or "")
        exclusions[str(row.get("user_id"))] = {channel for channel in pattern.split("+") if channel in CHANNEL_ORDER}
    return exclusions


def analyze_personal_baseline_features(
    channel_features: pd.DataFrame,
    templates: pd.DataFrame,
    quality: pd.DataFrame,
    patient_device_fit: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if channel_features.empty or templates.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    normalized_templates = templates[templates["template_type"] == "amplitude_normalized_template"].copy()
    if normalized_templates.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    usable_quality = quality[["measurement_id", "measurement_validity_label"]] if not quality.empty else pd.DataFrame()
    rows = channel_features[channel_features["standard_channel_name"].isin(CHANNEL_ORDER)].copy()
    rows = rows.merge(
        normalized_templates[["measurement_id", "standard_channel_name", "template_vector_json", "template_quality_score"]],
        on=["measurement_id", "standard_channel_name"],
        how="left",
    )
    if not usable_quality.empty:
        rows = rows.merge(usable_quality, on="measurement_id", how="left")
    exclusions = _persistent_alignment_exclusions(patient_device_fit)
    feature_rows = []
    range_rows = []
    deviation_rows = []
    for (user_id, channel), group in rows.dropna(subset=["user_id"]).groupby(["user_id", "standard_channel_name"], dropna=False):
        user_key = str(user_id)
        excluded_for_alignment = channel in exclusions.get(user_key, set())
        eligible = group[
            (group["channel_validity_label"] == "valid")
            & (pd.to_numeric(group["template_quality_score"], errors="coerce") >= 45)
            & (
                pd.to_numeric(group["pressure_artifact_score_mean"], errors="coerce").isna()
                | (pd.to_numeric(group["pressure_artifact_score_mean"], errors="coerce") <= 0.4)
            )
        ].copy()
        if "measurement_validity_label" in eligible:
            eligible = eligible[eligible["measurement_validity_label"].isin(["valid", "partial_valid"])]
        if excluded_for_alignment:
            status = "excluded_persistent_alignment"
        elif len(eligible) < 3:
            status = "insufficient_eligible_records"
        else:
            status = "available"
        template_vectors = [
            _resample_template(parse_json_value(value, []))
            for value in eligible["template_vector_json"].tolist()
            if parse_json_value(value, [])
        ]
        baseline_vector = []
        if status == "available" and template_vectors:
            baseline_vector = np.median(np.asarray(template_vectors, dtype=float), axis=0).tolist()
        feature_row: dict[str, Any] = {
            "user_id": user_id,
            "standard_channel_name": channel,
            "baseline_status": status,
            "candidate_record_count": int(len(group)),
            "eligible_record_count": int(len(eligible)),
            "persistent_alignment_excluded": excluded_for_alignment,
            "baseline_template_point_count": len(baseline_vector),
            "personal_baseline_template_json": json.dumps(round_vector(baseline_vector), ensure_ascii=False) if baseline_vector else None,
            "baseline_input_basis": "waveform_preview_normalized_template",
            "feature_version": "pulse_personal_baseline_v1",
        }
        for feature in BASELINE_FEATURE_COLUMNS:
            median, mad = _median_mad(eligible[feature]) if feature in eligible else (None, None)
            feature_row[f"{feature}_median"] = round(median, 6) if median is not None else None
            feature_row[f"{feature}_mad"] = round(mad, 6) if mad is not None else None
            if status == "available" and median is not None:
                range_rows.append(
                    {
                        "user_id": user_id,
                        "standard_channel_name": channel,
                        "feature_name": feature,
                        "baseline_median": round(median, 6),
                        "baseline_mad": round(mad or 0.0, 6),
                        "normal_lower": round(median - 3 * (mad or 0.0), 6),
                        "normal_upper": round(median + 3 * (mad or 0.0), 6),
                        "eligible_record_count": int(len(eligible)),
                        "feature_version": "pulse_personal_baseline_v1",
                    }
                )
        feature_rows.append(feature_row)
        if status != "available":
            continue
        baseline_metrics = {
            feature: _median_mad(eligible[feature]) if feature in eligible else (None, None)
            for feature in BASELINE_FEATURE_COLUMNS
        }
        for _, source in group.iterrows():
            scores: dict[str, float] = {}
            for feature, (median, mad) in baseline_metrics.items():
                value = safe_float(source.get(feature))
                if median is None or value is None:
                    continue
                scale = max(mad or 0.0, abs(median) * 0.05, 1e-6)
                scores[feature] = abs(value - median) / scale
            vector = _resample_template(parse_json_value(source.get("template_vector_json"), []))
            shape_distance = None
            if vector and baseline_vector:
                similarity = vector_similarity(vector, baseline_vector)
                shape_distance = (1 - similarity) if similarity is not None else None
                if shape_distance is not None:
                    scores["template_shape_distance"] = shape_distance / 0.15
            top_feature = max(scores, key=scores.get) if scores else None
            aggregate_score = min(100.0, float(np.mean([min(value, 5.0) for value in scores.values()])) * 20) if scores else None
            deviation_rows.append(
                {
                    "measurement_id": source.get("measurement_id"),
                    "user_id": user_id,
                    "standard_channel_name": channel,
                    "baseline_deviation_score": round(aggregate_score, 3) if aggregate_score is not None else None,
                    "template_shape_distance": round(shape_distance, 6) if shape_distance is not None else None,
                    "primary_deviation_feature": top_feature,
                    "within_personal_normal_range": bool(aggregate_score is not None and aggregate_score <= 40),
                    "baseline_record_used": bool(source.get("measurement_id") in set(eligible["measurement_id"])),
                    "feature_version": "pulse_personal_baseline_v1",
                }
            )
    return pd.DataFrame(feature_rows), pd.DataFrame(range_rows), pd.DataFrame(deviation_rows)


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
    window_features = frames.get("window_channel_features", pd.DataFrame())
    pattern_stability = frames.get("measurement_pattern_stability", pd.DataFrame())
    measurement_channels = frames.get("measurement_channel_summary", pd.DataFrame())
    longitudinal_channels = frames.get("longitudinal_channel_summary", pd.DataFrame())
    record_features = frames.get("record_feature", pd.DataFrame())
    channel_features = frames.get("channel_feature", pd.DataFrame())
    beat_features = frames.get("beat_level_feature", pd.DataFrame())
    phase_features = frames.get("phase_variability_feature", pd.DataFrame())
    residual_features = frames.get("residual_fluctuation_feature", pd.DataFrame())
    structure_features = frames.get("channel_structure_feature", pd.DataFrame())
    standard_feature_audit = frames.get("standard_feature_audit", pd.DataFrame())
    period_consistency = frames.get("pulse_rate_period_consistency", pd.DataFrame())
    period_experiment = frames.get("pulse_rate_period_experiment", pd.DataFrame())
    raw_period_templates = frames.get("raw_period_templates", pd.DataFrame())
    patient_quality = frames.get("patient_quality_summary", pd.DataFrame())
    patient_device_fit = frames.get("patient_device_fit_summary", pd.DataFrame())
    personal_baseline = frames.get("personal_baseline_feature", pd.DataFrame())
    personal_range = frames.get("personal_normal_range", pd.DataFrame())
    baseline_deviation = frames.get("baseline_deviation_score", pd.DataFrame())
    reliability = frames.get("feature_reliability", pd.DataFrame())
    device = frames.get("device_consistency", pd.DataFrame())
    lines = [
        "# Pulse Phase 1-7 Analysis Report",
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
        f"- window channel feature rows: {summary['window_channel_feature_count']}",
        f"- measurement pattern stability rows: {summary['measurement_pattern_stability_count']}",
        f"- standardized record feature rows: {summary['record_feature_count']}",
        f"- standardized channel feature rows: {summary['channel_feature_count']}",
        f"- beat-level feature rows: {summary['beat_level_feature_count']}",
        f"- phase variability feature rows: {summary['phase_variability_feature_count']}",
        f"- residual fluctuation feature rows: {summary['residual_fluctuation_feature_count']}",
        f"- channel structure feature rows: {summary['channel_structure_feature_count']}",
        f"- raw waveform pulse-rate consistency rows: {summary['pulse_rate_period_consistency_count']}",
        f"- raw waveform period template rows: {summary['raw_period_template_count']}",
        f"- patient quality summary rows: {summary['patient_quality_summary_count']}",
        f"- patient device-fit summary rows: {summary['patient_device_fit_summary_count']}",
        f"- personal baseline channel rows: {summary['personal_baseline_feature_count']}",
        f"- personal normal range rows: {summary['personal_normal_range_count']}",
        f"- baseline deviation rows: {summary['baseline_deviation_score_count']}",
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
    lines.extend(["", "## Standardized Phase 5 Features", ""])
    if record_features.empty or channel_features.empty:
        lines.append("No standardized phase 5 feature rows were produced.")
    else:
        lines.append(f"- record_feature rows: {len(record_features)}")
        lines.append(f"- channel_feature rows: {len(channel_features)}")
        lines.append(f"- beat_level_feature rows: {len(beat_features)}")
        lines.append(f"- phase_variability_feature rows: {len(phase_features)}")
        lines.append(f"- residual_fluctuation_feature rows: {len(residual_features)}")
        lines.append(f"- channel_structure_feature rows: {len(structure_features)}")
        mean_fit = channel_features["template_fit_r2_mean"].mean()
        mean_artifact = channel_features["pressure_artifact_score_mean"].mean()
        if not math.isnan(mean_fit):
            lines.append(f"- average template fit R2: {mean_fit:.4f}")
        if not math.isnan(mean_artifact):
            lines.append(f"- average pressure artifact score: {mean_artifact:.4f}")
        lines.append("- `b/a/delta/residual` fitting currently uses exported preview cycles; full waveform export is required before physiological interpretation.")
    if not standard_feature_audit.empty:
        lines.append(f"- standard feature audit rows: {len(standard_feature_audit)}")
    lines.extend(["", "## Raw Waveform Pulse Rate Period Consistency", ""])
    if period_consistency.empty:
        lines.append("No raw waveform period consistency rows were produced.")
    else:
        lines.append(f"- period consistency input basis: {summary['pulse_rate_period_input_basis']}")
        lines.append(f"- promoted period selection arm: {summary['promoted_period_selection_method']}")
        lines.append(f"- exported raw period templates: {len(raw_period_templates)}")
        lines.append(f"- pulse-rate consistent channel rows: {summary['pulse_rate_consistent_channel_count']}")
        lines.append(f"- double-period dominant channel rows: {summary['double_period_dominant_channel_count']}")
        lines.append(f"- Guan double-period dominant channel rows: {summary['guan_double_period_dominant_count']}")
        if not period_experiment.empty:
            promoted = period_experiment[
                (period_experiment["standard_channel_name"] == "all")
                & (period_experiment["experiment_decision"] == "promote_period_alignment_only")
            ]
            baseline = period_experiment[
                (period_experiment["standard_channel_name"] == "all")
                & (period_experiment["experiment_decision"] == "baseline")
            ]
            if not baseline.empty and not promoted.empty:
                base = baseline.iloc[0]
                chosen = promoted.iloc[0]
                lines.append(
                    f"- baseline median absolute period error: {base['median_abs_period_error_ratio']:.4f}; "
                    f"promoted: {chosen['median_abs_period_error_ratio']:.4f}"
                )
                lines.append(
                    f"- baseline within 20% rate: {base['within_20_percent_rate']:.2%}; "
                    f"promoted: {chosen['within_20_percent_rate']:.2%}"
                )
        lines.append("- the promoted arm is used for PulseNumbers-aligned period templates only; low coherence does not qualify a waveform as high quality.")
        lines.append("- double-period dominance is reported separately from PulseNumbers agreement; it is evidence for waveform morphology review, not an automatic pulse-rate correction.")
    lines.extend(["", "## Phase 6 Patient Device Fit Risk", ""])
    if patient_quality.empty or patient_device_fit.empty:
        lines.append("No patient-level quality or device-fit risk rows were produced.")
    else:
        lines.append(f"- patient quality rows: {len(patient_quality)}")
        lines.append(f"- patient device-fit rows: {len(patient_device_fit)}")
        lines.append(f"- high device-fit risk patients: {summary['high_device_fit_risk_patient_count']}")
        lines.append(f"- persistent alignment risk patients: {summary['persistent_alignment_patient_count']}")
        lines.append("- wrist circumference is unavailable in the current dataset; risk is based on longitudinal channel quality patterns and must not be interpreted as confirmed device-size mismatch.")
    lines.extend(["", "## Phase 7 Personal Baseline", ""])
    if personal_baseline.empty:
        lines.append("No personal baseline rows were produced.")
    else:
        available = int((personal_baseline["baseline_status"] == "available").sum())
        excluded = int((personal_baseline["baseline_status"] == "excluded_persistent_alignment").sum())
        lines.append(f"- baseline channel rows available: {available}")
        lines.append(f"- channels excluded for persistent alignment suspicion: {excluded}")
        lines.append(f"- personal normal range rows: {len(personal_range)}")
        lines.append(f"- record-channel deviation rows: {len(baseline_deviation)}")
        lines.append("- baseline construction requires valid channel signal, usable record quality, template quality >= 45, and pressure artifact score <= 0.4.")
        lines.append("- baseline templates are currently constructed from normalized waveform previews; full-waveform baselines remain a later validation requirement.")
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
    lines.extend(["", "## Windowed Three-Channel Pattern Stability", ""])
    if window_features.empty or pattern_stability.empty:
        lines.append("No windowed pattern stability rows were produced.")
    else:
        window_label_counts = window_features["channel_validity_label"].value_counts().to_dict()
        for label in ["valid", "low_snr", "suspected_misalignment", "insufficient_preview"]:
            if label in window_label_counts:
                lines.append(f"- window {label}: {window_label_counts[label]}")
        pattern_counts = pattern_stability["pattern_validity_label"].value_counts().to_dict()
        for label in ["stable_valid", "local_valid_segment", "unstable_or_noisy", "insufficient_windows"]:
            if label in pattern_counts:
                lines.append(f"- {label}: {pattern_counts[label]}")
        avg_stability = pattern_stability["pattern_stability_score"].mean()
        avg_shift = pattern_stability["global_posture_shift_score"].mean()
        if not math.isnan(avg_stability):
            lines.append(f"- average pattern_stability_score: {avg_stability:.2f}")
        if not math.isnan(avg_shift):
            lines.append(f"- average global_posture_shift_score: {avg_shift:.2f}")
        lines.append("- current windowing uses waveform preview points; full-waveform ingestion can preserve these outputs while increasing temporal resolution.")
    lines.extend(["", "## Device Consistency", ""])
    if device.empty:
        lines.append(f"No cross-device feature pairs were produced within {summary['near_time_pair_window_minutes']} minutes.")
    else:
        lines.append(f"- feature rows: {summary['device_consistency_feature_count']}")
        lines.append(f"- paired comparisons: {summary['device_consistency_pair_count']}")
    return "\n".join(lines) + "\n"


def analyze(dataset_dir: Path, output_dir: Path, near_minutes: int, raw_pulse_root: Path) -> None:
    feature_matrix = load_feature_matrix(dataset_dir)
    waveform_frame = waveform_metrics(dataset_dir)
    channel_quality = analyze_channel_signal_quality(dataset_dir, feature_matrix)
    pulse_periodicity = analyze_pulse_periodicity(channel_quality)
    decomposition, templates = analyze_template_decomposition(dataset_dir, feature_matrix)
    window_features, pattern_stability = analyze_windowed_pattern_stability(dataset_dir, feature_matrix)
    measurement_channels = summarize_measurement_channels(channel_quality)
    longitudinal_channels = summarize_longitudinal_channels(channel_quality)
    quality = analyze_measurement_quality(feature_matrix, waveform_frame, measurement_channels)
    beat_features = analyze_beat_level_features(dataset_dir, feature_matrix)
    channel_features = analyze_channel_features(channel_quality, beat_features)
    phase_features = analyze_phase_variability_features(beat_features)
    residual_features = analyze_residual_fluctuation_features(decomposition, beat_features)
    structure_features = analyze_channel_structure_features(channel_features, templates)
    record_features = analyze_record_features(quality, pattern_stability, channel_features, structure_features)
    period_consistency, period_experiment, raw_period_templates = analyze_pulse_rate_period_consistency(feature_matrix, raw_pulse_root)
    patient_quality = analyze_patient_quality_summary(quality, channel_quality)
    patient_device_fit = analyze_patient_device_fit_summary(channel_quality)
    personal_baseline, personal_range, baseline_deviation = analyze_personal_baseline_features(
        channel_features,
        templates,
        quality,
        patient_device_fit,
    )
    standard_feature_audit = analyze_standard_feature_audit(
        {
            "record_feature": record_features,
            "channel_feature": channel_features,
            "beat_level_feature": beat_features,
            "phase_variability_feature": phase_features,
            "residual_fluctuation_feature": residual_features,
            "channel_structure_feature": structure_features,
            "pulse_rate_period_consistency": period_consistency,
            "raw_period_templates": raw_period_templates,
        },
        quality,
    )
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
        "window_channel_feature_count": int(len(window_features)),
        "valid_window_channel_feature_count": int((window_features["channel_validity_label"] == "valid").sum()) if not window_features.empty else 0,
        "measurement_pattern_stability_count": int(len(pattern_stability)),
        "stable_pattern_measurement_count": int((pattern_stability["pattern_validity_label"] == "stable_valid").sum()) if not pattern_stability.empty else 0,
        "local_valid_pattern_measurement_count": int((pattern_stability["pattern_validity_label"] == "local_valid_segment").sum()) if not pattern_stability.empty else 0,
        "measurement_channel_summary_count": int(len(measurement_channels)),
        "longitudinal_channel_summary_count": int(len(longitudinal_channels)),
        "record_feature_count": int(len(record_features)),
        "channel_feature_count": int(len(channel_features)),
        "beat_level_feature_count": int(len(beat_features)),
        "phase_variability_feature_count": int(len(phase_features)),
        "residual_fluctuation_feature_count": int(len(residual_features)),
        "channel_structure_feature_count": int(len(structure_features)),
        "standard_feature_audit_count": int(len(standard_feature_audit)),
        "standard_feature_version": "pulse_standard_features_v1",
        "standard_feature_input_basis": "waveform_preview",
        "pulse_rate_period_consistency_count": int(len(period_consistency)),
        "raw_period_template_count": int(len(raw_period_templates)),
        "pulse_rate_period_input_basis": "raw_waveform",
        "pulse_rate_period_consistency_version": PERIOD_CONSISTENCY_VERSION,
        "pulse_rate_consistent_channel_count": int((period_consistency["pulse_rate_period_consistency_label"] == "pulse_rate_consistent").sum()) if not period_consistency.empty else 0,
        "double_period_dominant_channel_count": int(period_consistency["double_period_dominant_flag"].sum()) if not period_consistency.empty else 0,
        "guan_double_period_dominant_count": int(
            period_consistency[
                (period_consistency["standard_channel_name"] == "guan")
                & (period_consistency["double_period_dominant_flag"] == True)
            ].shape[0]
        ) if not period_consistency.empty else 0,
        "pulse_rate_period_experiment_count": int(len(period_experiment)),
        "promoted_period_selection_method": str(period_experiment["promoted_arm"].iloc[0]) if not period_experiment.empty else "unavailable",
        "promoted_period_selection_scope": "period_alignment_only",
        "patient_quality_summary_count": int(len(patient_quality)),
        "patient_device_fit_summary_count": int(len(patient_device_fit)),
        "high_device_fit_risk_patient_count": int((patient_device_fit["device_fit_risk_label"] == "high").sum()) if not patient_device_fit.empty else 0,
        "persistent_alignment_patient_count": int(patient_device_fit["persistent_alignment_flag"].sum()) if not patient_device_fit.empty else 0,
        "patient_device_fit_version": "pulse_patient_device_fit_v1",
        "patient_device_fit_input_basis": "waveform_preview_longitudinal_channel_quality",
        "wrist_circumference_available": False,
        "personal_baseline_feature_count": int(len(personal_baseline)),
        "available_personal_baseline_channel_count": int((personal_baseline["baseline_status"] == "available").sum()) if not personal_baseline.empty else 0,
        "available_personal_baseline_patient_count": int(personal_baseline[personal_baseline["baseline_status"] == "available"]["user_id"].nunique()) if not personal_baseline.empty else 0,
        "persistent_alignment_excluded_baseline_channel_count": int((personal_baseline["baseline_status"] == "excluded_persistent_alignment").sum()) if not personal_baseline.empty else 0,
        "personal_normal_range_count": int(len(personal_range)),
        "baseline_deviation_score_count": int(len(baseline_deviation)),
        "personal_baseline_version": "pulse_personal_baseline_v1",
        "personal_baseline_input_basis": "waveform_preview_normalized_template",
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
            "window_channel_features": window_features,
            "measurement_pattern_stability": pattern_stability,
            "measurement_channel_summary": measurement_channels,
            "longitudinal_channel_summary": longitudinal_channels,
            "record_feature": record_features,
            "channel_feature": channel_features,
            "beat_level_feature": beat_features,
            "phase_variability_feature": phase_features,
            "residual_fluctuation_feature": residual_features,
            "channel_structure_feature": structure_features,
            "pulse_rate_period_consistency": period_consistency,
            "pulse_rate_period_experiment": period_experiment,
            "raw_period_templates": raw_period_templates,
            "patient_quality_summary": patient_quality,
            "patient_device_fit_summary": patient_device_fit,
            "personal_baseline_feature": personal_baseline,
            "personal_normal_range": personal_range,
            "baseline_deviation_score": baseline_deviation,
            "standard_feature_audit": standard_feature_audit,
            "feature_reliability": reliability,
            "device_consistency": device,
        },
        summary,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pulse phase 1-7 analysis from an exported dataset directory.")
    parser.add_argument("--dataset-dir", required=True, help="Directory containing manifest.jsonl and exported pulse tables.")
    parser.add_argument("--output-dir", help="Analysis output directory. Defaults to dataset-dir/analysis/phase1.")
    parser.add_argument("--near-minutes", type=int, default=30, help="Near-time pairing window for cross-device analysis.")
    parser.add_argument("--raw-pulse-root", help="Directory containing original pulse JSON files. Defaults to storage/standard/assets/pulse_json inferred from dataset-dir.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset_dir = Path(args.dataset_dir)
    output_dir = Path(args.output_dir) if args.output_dir else dataset_dir / "analysis" / "phase1"
    raw_pulse_root = Path(args.raw_pulse_root) if args.raw_pulse_root else dataset_dir.parents[2] / "standard" / "assets" / "pulse_json"
    analyze(dataset_dir, output_dir, args.near_minutes, raw_pulse_root)
    print(f"Wrote pulse phase 1-7 analysis: {output_dir}")


if __name__ == "__main__":
    main()
