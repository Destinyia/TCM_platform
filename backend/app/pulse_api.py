from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from flask import Blueprint, jsonify, request
from sqlalchemy import select

import pandas as pd

from backend.app.config import PROJECT_ROOT
from backend.app.database import SessionLocal, get_engine
from backend.app.models import (
    Device,
    FeatureVariable,
    FileAsset,
    PulseMeasurement,
    PulsePositionFeature,
    PulseWaveformAsset,
    User,
    Visit,
)

pulse_api = Blueprint("pulse_api", __name__)
PULSE_PHASE1_DATASET_DIR = PROJECT_ROOT / "storage" / "datasets" / "DS-PULSE-PHASE1" / "v2026.05.phase1.001"


def as_json(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


def _clean_number(value, digits: int = 3):
    if pd.isna(value):
        return None
    number = float(value)
    return round(number, digits)


def _count_rows(frame: pd.DataFrame, column: str) -> list[dict]:
    if frame.empty or column not in frame:
        return []
    counts = frame[column].fillna("unknown").value_counts().reset_index()
    counts.columns = [column, "count"]
    return [{column: str(row[column]), "count": int(row["count"])} for _, row in counts.iterrows()]


def _group_quality(frame: pd.DataFrame, group_column: str) -> list[dict]:
    if frame.empty or group_column not in frame:
        return []
    grouped = (
        frame.groupby(group_column, dropna=False)
        .agg(
            measurement_count=("measurement_id", "count"),
            valid_count=("measurement_validity_label", lambda values: int((values == "valid").sum())),
            partial_valid_count=("measurement_validity_label", lambda values: int((values == "partial_valid").sum())),
            invalid_count=("measurement_validity_label", lambda values: int((values == "invalid").sum())),
            avg_quality=("signal_quality_score", "mean"),
            avg_drift=("drift_severity_index", "mean"),
        )
        .reset_index()
    )
    rows = []
    for _, row in grouped.iterrows():
        total = int(row["measurement_count"])
        rows.append(
            {
                group_column: str(row[group_column]) if pd.notna(row[group_column]) else "unknown",
                "measurement_count": total,
                "valid_count": int(row["valid_count"]),
                "partial_valid_count": int(row["partial_valid_count"]),
                "invalid_count": int(row["invalid_count"]),
                "valid_rate": round(int(row["valid_count"]) / total, 3) if total else 0,
                "avg_quality": _clean_number(row["avg_quality"], 2),
                "avg_drift": _clean_number(row["avg_drift"], 2),
            }
        )
    return rows


def _load_phase1_analysis(dataset_dir: Path = PULSE_PHASE1_DATASET_DIR) -> dict:
    analysis_dir = dataset_dir / "analysis" / "phase1"
    quality_path = analysis_dir / "measurement_quality.csv"
    reliability_path = analysis_dir / "feature_reliability.csv"
    if not quality_path.exists() or not reliability_path.exists():
        return {
            "available": False,
            "dataset_dir": str(dataset_dir),
            "message": "pulse phase1 analysis output not found",
        }

    quality = pd.read_csv(quality_path)
    reliability = pd.read_csv(reliability_path)
    duration_missing = int((quality.get("duration_available", pd.Series(dtype=bool)) == False).sum()) if "duration_available" in quality else 0
    validity_distribution = _count_rows(quality, "measurement_validity_label")
    source_quality = _group_quality(quality, "source_vendor")
    slot_quality = _group_quality(quality, "visit_slot")

    risk_columns = [
        "feature_name",
        "feature_reliability_grade",
        "risk_score",
        "missing_rate",
        "outlier_rate",
        "device_sensitivity",
        "drift_sensitivity",
        "quality_dependency_score",
    ]
    risk_rows = []
    if not reliability.empty:
        for _, row in reliability.sort_values("risk_score", ascending=False).head(8).iterrows():
            risk_rows.append(
                {
                    key: (_clean_number(row[key], 4) if key not in {"feature_name", "feature_reliability_grade"} else row[key])
                    for key in risk_columns
                    if key in reliability.columns
                }
            )

    scatter_rows = []
    if not quality.empty:
        for _, row in quality.sort_values("signal_quality_score", ascending=False).head(160).iterrows():
            scatter_rows.append(
                {
                    "measurement_id": row["measurement_id"],
                    "source_vendor": row.get("source_vendor") if pd.notna(row.get("source_vendor")) else "unknown",
                    "visit_slot": row.get("visit_slot") if pd.notna(row.get("visit_slot")) else "unknown",
                    "quality": _clean_number(row.get("signal_quality_score"), 2),
                    "drift": _clean_number(row.get("drift_severity_index"), 2),
                    "label": row.get("measurement_validity_label") if pd.notna(row.get("measurement_validity_label")) else "unknown",
                }
            )

    return {
        "available": True,
        "dataset_dir": str(dataset_dir),
        "analysis_dir": str(analysis_dir),
        "measurement_count": int(len(quality)),
        "valid_count": int((quality["measurement_validity_label"] == "valid").sum()),
        "partial_valid_count": int((quality["measurement_validity_label"] == "partial_valid").sum()),
        "invalid_count": int((quality["measurement_validity_label"] == "invalid").sum()),
        "duration_unavailable_count": duration_missing,
        "validity_distribution": validity_distribution,
        "source_quality": source_quality,
        "slot_quality": slot_quality,
        "feature_risks": risk_rows,
        "quality_drift_scatter": scatter_rows,
    }


def measurement_payload(measurement: PulseMeasurement, visit: Visit, user: User, device: Device | None) -> dict:
    features = measurement.feature_json or {}
    return {
        "measurement_id": str(measurement.measurement_id),
        "visit_id": str(measurement.visit_id),
        "modality_record_id": str(measurement.modality_record_id),
        "user_id": str(measurement.user_id),
        "user_name": user.canonical_name,
        "source_vendor": measurement.source_vendor,
        "source_measurement_id": measurement.source_measurement_id,
        "start_time": as_json(measurement.start_time),
        "end_time": as_json(measurement.end_time),
        "duration_seconds": as_json(measurement.duration_seconds),
        "visit_slot": measurement.visit_slot,
        "collection_hour": as_json(measurement.collection_hour),
        "hand_side": measurement.hand_side,
        "pulse_position": measurement.pulse_position,
        "sampling_rate": as_json(measurement.sampling_rate),
        "quality_status": measurement.quality_status,
        "quality_flags": (visit.cheat_types or {}).get("flags") or [],
        "device_id": str(measurement.device_id) if measurement.device_id else None,
        "device_model": device.device_model if device else None,
        "source_device_id": device.source_device_id if device else None,
        "feature_json": features,
        "pulse_rate": features.get("pulse_rate"),
        "force": features.get("force"),
        "tension": features.get("tension"),
        "fluency": features.get("fluency"),
        "amplitude": features.get("amplitude"),
        "stability_score": features.get("stability_score"),
        "source_meta_json": measurement.source_meta_json,
    }


@pulse_api.route("/analysis/phase1-summary", methods=["GET"])
def phase1_analysis_summary():
    dataset_dir = request.args.get("dataset_dir")
    path = Path(dataset_dir) if dataset_dir else PULSE_PHASE1_DATASET_DIR
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return jsonify(_load_phase1_analysis(path))


@pulse_api.route("/measurements", methods=["GET"])
def measurements():
    get_engine()
    user_id = request.args.get("user_id")
    source_vendor = request.args.get("source_vendor")
    slot = request.args.get("visit_slot")
    quality_status = request.args.get("quality_status")
    device_id = request.args.get("device_id")
    has_waveform = request.args.get("has_waveform")

    with SessionLocal() as session:
        stmt = (
            select(PulseMeasurement, Visit, User, Device)
            .join(Visit, Visit.visit_id == PulseMeasurement.visit_id)
            .join(User, User.user_id == PulseMeasurement.user_id)
            .outerjoin(Device, Device.device_id == PulseMeasurement.device_id)
            .order_by(PulseMeasurement.start_time, PulseMeasurement.measurement_id)
        )
        if user_id:
            stmt = stmt.where(PulseMeasurement.user_id == UUID(user_id))
        if source_vendor:
            stmt = stmt.where(PulseMeasurement.source_vendor == source_vendor)
        if slot:
            stmt = stmt.where(PulseMeasurement.visit_slot == slot)
        if quality_status:
            stmt = stmt.where(PulseMeasurement.quality_status == quality_status)
        if device_id:
            stmt = stmt.where(PulseMeasurement.device_id == UUID(device_id))
        rows = session.execute(stmt).all()

        items = [measurement_payload(measurement, visit, user, device) for measurement, visit, user, device in rows]
        if has_waveform is not None:
            wanted = has_waveform.lower() == "true"
            counts = {
                measurement_id
                for (measurement_id,) in session.execute(select(PulseWaveformAsset.measurement_id).distinct()).all()
            }
            items = [item for item in items if (UUID(item["measurement_id"]) in counts) == wanted]
    return jsonify(items)


@pulse_api.route("/measurements/<measurement_id>", methods=["GET"])
def measurement_detail(measurement_id: str):
    get_engine()
    with SessionLocal() as session:
        row = session.execute(
            select(PulseMeasurement, Visit, User, Device)
            .join(Visit, Visit.visit_id == PulseMeasurement.visit_id)
            .join(User, User.user_id == PulseMeasurement.user_id)
            .outerjoin(Device, Device.device_id == PulseMeasurement.device_id)
            .where(PulseMeasurement.measurement_id == UUID(measurement_id))
        ).one_or_none()
        if not row:
            return jsonify({"message": "measurement not found"}), 404
        measurement, visit, user, device = row
        payload = measurement_payload(measurement, visit, user, device)
    return jsonify(payload)


@pulse_api.route("/measurements/<measurement_id>/waveforms", methods=["GET"])
def measurement_waveforms(measurement_id: str):
    get_engine()
    with SessionLocal() as session:
        rows = session.execute(
            select(PulseWaveformAsset, FileAsset)
            .outerjoin(FileAsset, FileAsset.asset_id == PulseWaveformAsset.asset_id)
            .where(PulseWaveformAsset.measurement_id == UUID(measurement_id))
            .order_by(PulseWaveformAsset.channel_name)
        ).all()
    return jsonify(
        [
            {
                "waveform_asset_id": str(waveform.waveform_asset_id),
                "measurement_id": str(waveform.measurement_id),
                "asset_id": str(waveform.asset_id) if waveform.asset_id else None,
                "channel_name": waveform.channel_name,
                "hand_side": waveform.hand_side,
                "pulse_position": waveform.pulse_position,
                "sample_count": waveform.sample_count,
                "sampling_rate": as_json(waveform.sampling_rate),
                "storage_uri": waveform.storage_uri,
                "data_format": waveform.data_format,
                "file_hash": waveform.file_hash,
                "preview_json": waveform.preview_json,
                "summary_json": waveform.summary_json,
                "file_name": asset.file_name if asset else None,
            }
            for waveform, asset in rows
        ]
    )


@pulse_api.route("/measurements/<measurement_id>/position-features", methods=["GET"])
def measurement_position_features(measurement_id: str):
    get_engine()
    with SessionLocal() as session:
        rows = session.execute(
            select(PulsePositionFeature)
            .where(PulsePositionFeature.measurement_id == UUID(measurement_id))
            .order_by(PulsePositionFeature.hand_side, PulsePositionFeature.pulse_position, PulsePositionFeature.feature_name)
        ).scalars().all()
    return jsonify(
        [
            {
                "position_feature_id": str(item.position_feature_id),
                "measurement_id": str(item.measurement_id),
                "hand_side": item.hand_side,
                "pulse_position": item.pulse_position,
                "feature_name": item.feature_name,
                "feature_value": as_json(item.feature_value),
                "feature_text": item.feature_text,
                "feature_unit": item.feature_unit,
                "source_field": item.source_field,
                "parser_version": item.parser_version,
                "quality_weight": as_json(item.quality_weight),
            }
            for item in rows
        ]
    )


@pulse_api.route("/features", methods=["GET"])
def pulse_features():
    get_engine()
    feature_name = request.args.get("feature_name")
    with SessionLocal() as session:
        rows = session.execute(
            select(PulseMeasurement).order_by(PulseMeasurement.start_time, PulseMeasurement.measurement_id)
        ).scalars().all()
    result = []
    for measurement in rows:
        for key, value in (measurement.feature_json or {}).items():
            if feature_name and key != feature_name:
                continue
            result.append(
                {
                    "measurement_id": str(measurement.measurement_id),
                    "visit_id": str(measurement.visit_id),
                    "user_id": str(measurement.user_id),
                    "feature_name": key,
                    "feature_value": value,
                    "feature_level": "measurement",
                    "source_vendor": measurement.source_vendor,
                }
            )
    return jsonify(result)


@pulse_api.route("/feature-variables", methods=["GET"])
def feature_variables():
    get_engine()
    with SessionLocal() as session:
        rows = session.execute(select(FeatureVariable).order_by(FeatureVariable.modality_type, FeatureVariable.feature_name)).scalars().all()
    return jsonify(
        [
            {
                "feature_name": item.feature_name,
                "display_name": item.display_name,
                "modality_type": item.modality_type,
                "feature_level": item.feature_level,
                "source_vendor": item.source_vendor,
                "data_type": item.data_type,
                "unit": item.unit,
                "category": item.category,
                "is_ml_feature": item.is_ml_feature,
                "is_quality_feature": item.is_quality_feature,
                "valid_range_json": item.valid_range_json,
                "description": item.description,
            }
            for item in rows
        ]
    )
