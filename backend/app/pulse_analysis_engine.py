from __future__ import annotations

import math
from typing import Any


CHANNEL_ORDER = ["cun", "guan", "chi"]


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(number) else number


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


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


def extract_preview_values(preview: Any) -> list[float]:
    if isinstance(preview, dict) and isinstance(preview.get("points"), list):
        raw_values = preview["points"]
    elif isinstance(preview, list):
        raw_values = preview
    else:
        raw_values = []
    values = []
    for point in raw_values:
        value = safe_float(point.get("y") if isinstance(point, dict) else point)
        if value is not None:
            values.append(value)
    return values


def mean_std(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    var = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(max(0.0, var))


def variance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


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


def linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float]:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0, ys[0] if ys else 0.0
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return 0.0, y_mean
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator
    return slope, y_mean - slope * x_mean


def linear_detrend(values: list[float]) -> list[float]:
    if len(values) < 2:
        return values[:]
    slope, intercept = linear_regression([float(index) for index in range(len(values))], values)
    return [value - (intercept + slope * index) for index, value in enumerate(values)]


def preview_seconds_per_point(duration_seconds: float | None, point_count: int) -> float | None:
    if duration_seconds is None or duration_seconds <= 0 or point_count < 2:
        return None
    return duration_seconds / (point_count - 1)


def pulse_lag_range(point_count: int, duration_seconds: float | None) -> tuple[int, int]:
    seconds_per_point = preview_seconds_per_point(duration_seconds, point_count)
    if seconds_per_point:
        min_lag = math.floor((60 / 180) / seconds_per_point)
        max_lag = math.ceil((60 / 35) / seconds_per_point)
        return max(2, min_lag), min(max(2, point_count // 2), max_lag)
    return 3, min(28, max(3, point_count // 2))


def autocorrelation_peak(values: list[float], min_lag: int, max_lag: int) -> tuple[float, int | None]:
    if len(values) < 16:
        return 0.0, None
    mean = sum(values) / len(values)
    centered = [value - mean for value in values]
    denominator = sum(value * value for value in centered)
    if denominator <= 0:
        return 0.0, None
    max_lag = min(max_lag, max(2, len(values) // 2))
    if max_lag < min_lag:
        return 0.0, None
    best_corr = 0.0
    best_lag = None
    for lag in range(max(2, min_lag), max_lag + 1):
        numerator = sum(centered[index] * centered[index - lag] for index in range(lag, len(centered)))
        corr = numerator / denominator
        if corr > best_corr:
            best_corr = corr
            best_lag = lag
    return best_corr, best_lag


def detect_preview_peaks(values: list[float]) -> list[int]:
    if len(values) < 5:
        return []
    detrended = linear_detrend(values)
    mean, std = mean_std(detrended)
    threshold = (mean or 0.0) + (std or 0.0) * 0.25
    return [
        index
        for index in range(1, len(detrended) - 1)
        if detrended[index] >= detrended[index - 1] and detrended[index] > detrended[index + 1] and detrended[index] >= threshold
    ]


def period_consistency_from_peaks(peaks: list[int]) -> float | None:
    if len(peaks) < 3:
        return None
    intervals = [float(peaks[index] - peaks[index - 1]) for index in range(1, len(peaks))]
    interval_mean, interval_std = mean_std(intervals)
    if not interval_mean:
        return None
    return clamp(1 - ((interval_std or 0.0) / interval_mean), 0, 1)


def build_periodic_template(values: list[float], lag: int | None) -> tuple[list[float], list[float], list[float]]:
    if not lag or lag < 2 or len(values) < lag * 2:
        return [], [], values[:]
    phase_values: list[list[float]] = [[] for _ in range(lag)]
    for index, value in enumerate(values):
        phase_values[index % lag].append(value)
    template = [sum(bucket) / len(bucket) if bucket else 0.0 for bucket in phase_values]
    repeated = [template[index % lag] for index in range(len(values))]
    residual = [value - predicted for value, predicted in zip(values, repeated)]
    return template, repeated, residual


def normalize_vector(values: list[float]) -> list[float]:
    _, std = mean_std(values)
    mean = sum(values) / len(values) if values else 0.0
    return [(value - mean) / std for value in values] if std else [0.0 for _ in values]


def dfa_alpha(values: list[float]) -> float | None:
    if len(values) < 16:
        return None
    mean = sum(values) / len(values)
    integrated = []
    total = 0.0
    for value in values:
        total += value - mean
        integrated.append(total)
    fluctuations = []
    for scale in [4, 8, 16, 32]:
        if scale * 2 > len(integrated):
            continue
        segment_fluctuations = []
        for start in range(0, len(integrated) - scale + 1, scale):
            segment = integrated[start : start + scale]
            slope, intercept = linear_regression([float(index) for index in range(scale)], segment)
            residuals = [value - (intercept + slope * index) for index, value in enumerate(segment)]
            rms = math.sqrt(sum(value * value for value in residuals) / len(residuals))
            if rms > 0:
                segment_fluctuations.append(rms)
        if segment_fluctuations:
            fluctuations.append((scale, sum(segment_fluctuations) / len(segment_fluctuations)))
    if len(fluctuations) < 2:
        return None
    slope, _ = linear_regression([math.log(scale) for scale, _ in fluctuations], [math.log(value) for _, value in fluctuations])
    return slope


def analyze_preview_signal(preview: Any, duration_seconds: float | None = None) -> dict[str, Any]:
    values = extract_preview_values(preview)
    if len(values) < 16:
        return {"preview_point_count": len(values), "values": values, "template_vector": [], "normalized_template_vector": []}
    trend_slope, trend_intercept = linear_regression([float(index) for index in range(len(values))], values)
    detrended = [value - (trend_intercept + trend_slope * index) for index, value in enumerate(values)]
    min_lag, max_lag = pulse_lag_range(len(values), duration_seconds)
    template_coherence, dominant_lag = autocorrelation_peak(detrended, min_lag, max_lag)
    template, repeated, residual = build_periodic_template(detrended, dominant_lag)
    detrended_variance = variance(detrended) or 0.0
    residual_variance = variance(residual) or 0.0
    template_variance = variance(repeated) or 0.0
    p05 = percentile(values, 0.05) or min(values)
    p95 = percentile(values, 0.95) or max(values)
    amplitude_range = max(0.0, p95 - p05)
    residual_mean, residual_std = mean_std(residual)
    _, detrended_std = mean_std(detrended)
    explained_ratio = clamp(1 - (residual_variance / detrended_variance), 0, 1) if detrended_variance else 0.0
    periodic_snr = template_variance / (residual_variance + 1e-9)
    residual_energy_ratio = residual_variance / (detrended_variance + 1e-9) if detrended_variance else 1.0
    seconds_per_point = preview_seconds_per_point(duration_seconds, len(values))
    estimated_period_seconds = dominant_lag * seconds_per_point if dominant_lag and seconds_per_point else None
    estimated_pulse_rate_bpm = 60 / estimated_period_seconds if estimated_period_seconds else None
    peaks = detect_preview_peaks(values)
    consistency = period_consistency_from_peaks(peaks)
    if consistency is None:
        consistency = template_coherence
    return {
        "values": values,
        "preview_point_count": len(values),
        "pulse_energy": template_variance,
        "residual_fluctuation": (residual_std or 0.0) / (amplitude_range + 1e-9) if amplitude_range else 1.0,
        "residual_std": residual_std,
        "residual_cv": (residual_std or 0.0) / detrended_std if detrended_std else None,
        "residual_energy_ratio": residual_energy_ratio,
        "template_coherence": template_coherence,
        "periodic_snr": periodic_snr,
        "dominant_lag_preview_points": dominant_lag,
        "estimated_period_seconds": estimated_period_seconds,
        "estimated_pulse_rate_bpm": estimated_pulse_rate_bpm,
        "peak_count_preview": len(peaks),
        "period_consistency_score": consistency,
        "trend_slope_preview": trend_slope,
        "template_explained_variance_ratio": explained_ratio,
        "dfa_alpha": dfa_alpha(residual),
        "template_vector": template,
        "normalized_template_vector": normalize_vector(template),
    }


def classify_channel(metrics: dict[str, Any], energy_ratio_to_median: float | None = None) -> dict[str, Any]:
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


def summarize_measurement_quality(channel_rows: list[dict[str, Any]], duration_seconds: float | None = None) -> dict[str, Any]:
    core = [row for row in channel_rows if row.get("standard_channel_name") in CHANNEL_ORDER]
    usable = core or channel_rows
    valid_count = sum(1 for row in usable if row.get("channel_validity_label") == "valid")
    suspected = sum(1 for row in usable if row.get("channel_validity_label") == "suspected_misalignment")
    avg_snr = sum(safe_float(row.get("periodic_snr")) or 0.0 for row in usable) / len(usable) if usable else 0.0
    avg_coherence = sum(safe_float(row.get("template_coherence")) or 0.0 for row in usable) / len(usable) if usable else 0.0
    quality = clamp(min(avg_snr, 0.6) / 0.6 * 35 + min(avg_coherence, 0.6) / 0.6 * 35 + min(valid_count, 3) / 3 * 30 - suspected * 12)
    if duration_seconds and duration_seconds >= 20 and valid_count >= 2 and quality >= 50 and suspected <= 1:
        label = "valid"
        reason = ""
    elif valid_count >= 1 and quality >= 35:
        label = "partial_valid"
        reason = "channel periodic signal is usable but not enough for full validity"
    else:
        label = "invalid"
        reason = "insufficient periodic pulse signal"
    return {
        "signal_quality_score": round(quality, 3),
        "measurement_validity_label": label,
        "invalid_segment_reason": reason,
        "valid_channel_count": valid_count,
        "suspected_alignment_channel_count": suspected,
        "overall_periodic_snr": round(avg_snr, 6),
        "overall_template_coherence": round(avg_coherence, 6),
    }
