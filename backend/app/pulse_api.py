from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from flask import Blueprint, jsonify, request
from sqlalchemy import select

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


def as_json(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    return value


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
