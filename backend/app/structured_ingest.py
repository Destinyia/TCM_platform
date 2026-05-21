from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from backend.app.feature_wide import rebuild_visit_feature_wide
from backend.app.models import AnalysisRun, Device, FeatureVariable, FileAsset, ModalityRecord, PulseMeasurement, PulseMeasurementQuality, PulsePositionFeature, PulseWaveformAsset, Visit
from backend.app.pulse_analysis_engine import analyze_preview_signal, classify_channel, standard_channel_name, summarize_measurement_quality
from backend.app.structured_parser import build_structured_modalities

MODALITIES = ["ask", "pulse", "tongue", "face", "voice", "report"]
PULSE_QUALITY_FEATURES = {"stability_score", "valid_segment_count", "segment_count"}
PULSE_METADATA_NUMERIC_FIELDS = {"duration_seconds", "sampling_rate"}


def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _source_record_group_id(visit: Visit) -> str:
    if visit.cheat_types:
        return str(visit.cheat_types.get("source_record_group_id") or visit.source_visit_id or "")
    return str(visit.source_visit_id or "")


def _empty_payload(visit: Visit, modality: str) -> dict[str, Any]:
    return {
        "source_vendor": visit.source_vendor,
        "source_record_group_id": _source_record_group_id(visit),
        "modality": modality,
        "parser_stage": "db_parse",
        "asset_count": 0,
        "parsed_asset_count": 0,
        "assets": [],
    }


def _normalize_payload(visit: Visit, modality: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or _empty_payload(visit, modality))
    payload.setdefault("source_vendor", visit.source_vendor)
    payload.setdefault("source_record_group_id", _source_record_group_id(visit))
    payload.setdefault("modality", modality)
    payload["parser_stage"] = "db_parse"
    payload.setdefault("assets", [])
    payload["asset_count"] = len(payload["assets"])
    payload["parsed_asset_count"] = sum(1 for item in payload["assets"] if item.get("parse_status") == "ok")
    return payload


def _feature_summary(payload: dict[str, Any]) -> dict[str, Any]:
    statuses = Counter(str(item.get("parse_status") or "unknown") for item in payload.get("assets") or [])
    return {
        "asset_count": payload.get("asset_count", 0),
        "parsed_asset_count": payload.get("parsed_asset_count", 0),
        "parse_status_counts": dict(sorted(statuses.items())),
        "parser_stage": payload.get("parser_stage"),
    }


def _deterministic_uuid(namespace: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, namespace)


def _scalars(session: Session, stmt):
    if hasattr(session, "scalars"):
        return session.scalars(stmt).all()
    return session.execute(stmt).scalars().all()


def _scalar(session: Session, stmt):
    if hasattr(session, "scalar"):
        return session.scalar(stmt)
    return session.execute(stmt).scalar()


def _numeric_items(record: dict[str, Any]) -> dict[str, float | int]:
    return {
        key: value
        for key, value in record.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool) and key not in PULSE_METADATA_NUMERIC_FIELDS
    }


def _source_measurement_id(modality_record: ModalityRecord, record: dict[str, Any], index: int) -> str:
    return str(
        record.get("record_id")
        or record.get("source_measurement_id")
        or record.get("source_asset_id")
        or f"{modality_record.modality_record_id}:{index}"
    )


def _upsert_pulse_device(session: Session, visit: Visit, record: dict[str, Any]) -> uuid.UUID:
    source_device_id = str(record.get("source_device_id") or record.get("device_id") or "unknown")
    device_id = _deterministic_uuid(f"pulse-device:{visit.source_vendor}:{source_device_id}")
    stmt = insert(Device).values(
        device_id=device_id,
        source_vendor=visit.source_vendor,
        source_device_id=source_device_id,
        device_model=record.get("device_model"),
        sensor_type="pulse_pressure",
        sampling_rate=record.get("sampling_rate"),
        device_meta_json={"source": "structured_pulse_record"},
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_vendor", "source_device_id"],
        set_={
            "device_model": record.get("device_model"),
            "sensor_type": "pulse_pressure",
            "sampling_rate": record.get("sampling_rate"),
            "device_meta_json": {"source": "structured_pulse_record"},
        },
    )
    return session.execute(stmt.returning(Device.device_id)).scalar_one()


def _upsert_feature_variables(session: Session, feature_names: set[str]) -> None:
    for feature_name in sorted(feature_names):
        stmt = insert(FeatureVariable).values(
            feature_name=feature_name,
            display_name=feature_name,
            modality_type="pulse",
            feature_level="measurement",
            source_vendor="standard",
            data_type="numeric",
            category="quality" if feature_name in PULSE_QUALITY_FEATURES else "unknown",
            is_ml_feature=feature_name not in PULSE_QUALITY_FEATURES,
            is_quality_feature=feature_name in PULSE_QUALITY_FEATURES,
            description="Inferred from pulse structured records during parse-only sync.",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["feature_name"],
            set_={
                "modality_type": "pulse",
                "feature_level": "measurement",
                "data_type": "numeric",
                "category": "quality" if feature_name in PULSE_QUALITY_FEATURES else "unknown",
                "is_ml_feature": feature_name not in PULSE_QUALITY_FEATURES,
                "is_quality_feature": feature_name in PULSE_QUALITY_FEATURES,
            },
        )
        session.execute(stmt)


def _pulse_analysis_tables_available(session: Session) -> bool:
    required = [
        "dim_device",
        "dim_feature_variable",
        "fact_pulse_measurement",
        "fact_pulse_waveform_asset",
        "fact_pulse_position_feature",
    ]
    for table_name in required:
        if _scalar(session, select(func.to_regclass(table_name))) is None:
            return False
    return True


def _pulse_online_analysis_tables_available(session: Session) -> bool:
    required = ["analysis_run", "fact_pulse_measurement_quality", "fact_pulse_waveform_asset"]
    for table_name in required:
        if _scalar(session, select(func.to_regclass(table_name))) is None:
            return False
    return True


def _sync_waveform_asset(session: Session, measurement_id: uuid.UUID, record: dict[str, Any]) -> int:
    waveform_preview = record.get("waveform_preview") or []
    waveform_summary = record.get("waveform_summary") or {}
    if not waveform_preview and not waveform_summary:
        return 0

    count = 0
    if isinstance(waveform_preview, list) and waveform_preview:
        for index, item in enumerate(waveform_preview, start=1):
            channel_name = "waveform_preview"
            sample_count = None
            preview_json = item
            if isinstance(item, dict):
                channel_name = str(item.get("name") or channel_name)
                points = item.get("points")
                sample_count = len(points) if isinstance(points, list) else None
            summary = waveform_summary.get(channel_name) if isinstance(waveform_summary, dict) else None
            if isinstance(summary, dict) and summary.get("count"):
                sample_count = summary.get("count")
            waveform_id = _deterministic_uuid(f"pulse-waveform:{measurement_id}:{channel_name}:{index}")
            session.execute(
                insert(PulseWaveformAsset).values(
                    waveform_asset_id=waveform_id,
                    measurement_id=measurement_id,
                    channel_name=channel_name,
                    hand_side=record.get("side") or record.get("hand_side"),
                    pulse_position=record.get("position") or record.get("pulse_position") or "overall",
                    sample_count=sample_count,
                    sampling_rate=record.get("sampling_rate"),
                    data_format="json_preview",
                    preview_json=preview_json,
                    summary_json=summary if isinstance(summary, dict) else {},
                )
            )
            count += 1
        return count

    if isinstance(waveform_summary, dict):
        for channel_name, summary in waveform_summary.items():
            waveform_id = _deterministic_uuid(f"pulse-waveform:{measurement_id}:{channel_name}")
            session.execute(
                insert(PulseWaveformAsset).values(
                    waveform_asset_id=waveform_id,
                    measurement_id=measurement_id,
                    channel_name=str(channel_name),
                    hand_side=record.get("side") or record.get("hand_side"),
                    pulse_position=record.get("position") or record.get("pulse_position") or "overall",
                    sample_count=(summary or {}).get("count") if isinstance(summary, dict) else None,
                    sampling_rate=record.get("sampling_rate"),
                    data_format="summary_only",
                    preview_json=[],
                    summary_json=summary if isinstance(summary, dict) else {},
                )
            )
            count += 1
    return count


def _sync_position_features(session: Session, measurement_id: uuid.UUID, record: dict[str, Any]) -> int:
    count = 0
    for item_index, item in enumerate(record.get("measurements") or [], start=1):
        if not isinstance(item, dict):
            continue
        pulse_position = str(item.get("position") or item.get("pulse_position") or item.get("type") or "unknown")
        hand_side = item.get("side") or item.get("hand_side") or record.get("side")
        for feature_name, value in item.items():
            if feature_name in {"position", "pulse_position", "type", "side", "hand_side"}:
                continue
            if not isinstance(value, (int, float, str)) or isinstance(value, bool):
                continue
            feature_id = _deterministic_uuid(f"pulse-position:{measurement_id}:{item_index}:{pulse_position}:{feature_name}")
            session.execute(
                insert(PulsePositionFeature).values(
                    position_feature_id=feature_id,
                    measurement_id=measurement_id,
                    hand_side=hand_side,
                    pulse_position=pulse_position,
                    feature_name=str(feature_name),
                    feature_value=value if isinstance(value, (int, float)) else None,
                    feature_text=value if isinstance(value, str) else None,
                    source_field=str(feature_name),
                    parser_version=record.get("parser_version"),
                    quality_weight=record.get("stability_score"),
                )
            )
            count += 1
    return count


def _sync_pulse_online_analysis(session: Session, measurement_ids: list[uuid.UUID]) -> int:
    if not measurement_ids or not _pulse_online_analysis_tables_available(session):
        return 0

    measurements = {
        measurement.measurement_id: measurement
        for measurement in _scalars(session, select(PulseMeasurement).where(PulseMeasurement.measurement_id.in_(measurement_ids)))
    }
    waveforms = _scalars(
        session,
        select(PulseWaveformAsset)
        .where(PulseWaveformAsset.measurement_id.in_(measurement_ids))
        .order_by(PulseWaveformAsset.measurement_id, PulseWaveformAsset.channel_name),
    )
    grouped: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for waveform in waveforms:
        measurement = measurements.get(waveform.measurement_id)
        if measurement is None:
            continue
        metrics = analyze_preview_signal(waveform.preview_json, float(measurement.duration_seconds) if measurement.duration_seconds else None)
        row = {
            "measurement_id": str(waveform.measurement_id),
            "waveform_asset_id": str(waveform.waveform_asset_id),
            "channel_name": waveform.channel_name,
            "standard_channel_name": standard_channel_name(waveform.channel_name),
            **{key: value for key, value in metrics.items() if key not in {"values", "template_vector", "normalized_template_vector"}},
        }
        grouped.setdefault(waveform.measurement_id, []).append(row)

    if not grouped:
        return 0

    analysis_run = AnalysisRun(
        analysis_type="pulse_online_ingest_analysis",
        code_version="pulse_analysis_engine_v1",
        parameter_json={"trigger": "parse_structured_data"},
        status="completed",
        result_summary_json={"measurement_count": len(grouped)},
    )
    session.add(analysis_run)
    session.flush()

    inserted = 0
    for measurement_id, rows in grouped.items():
        energies = [float(row["pulse_energy"]) for row in rows if row.get("pulse_energy")]
        median_energy = sorted(energies)[len(energies) // 2] if energies else None
        labelled_rows = []
        for row in rows:
            energy = row.get("pulse_energy")
            energy_ratio = float(energy) / median_energy if energy and median_energy else None
            labelled_rows.append({**row, "channel_energy_ratio_to_median": energy_ratio, **classify_channel(row, energy_ratio)})
        summary = summarize_measurement_quality(
            labelled_rows,
            float(measurements[measurement_id].duration_seconds) if measurements.get(measurement_id) and measurements[measurement_id].duration_seconds else None,
        )
        session.add(
            PulseMeasurementQuality(
                analysis_run_id=analysis_run.analysis_run_id,
                measurement_id=measurement_id,
                stable_segment_ratio=None,
                best_segment_quality_score=summary.get("signal_quality_score"),
                signal_quality_score=summary.get("signal_quality_score"),
                measurement_validity_label=summary.get("measurement_validity_label"),
                result_json={
                    **summary,
                    "channel_rows": labelled_rows,
                },
            )
        )
        inserted += 1
    analysis_run.result_summary_json = {"measurement_count": inserted}
    return inserted


def sync_pulse_analysis_tables(session: Session, visits: list[Visit]) -> dict[str, int | bool]:
    result: dict[str, int | bool] = {
        "pulse_analysis_sync_skipped": False,
        "pulse_measurements_upserted": 0,
        "pulse_waveforms_inserted": 0,
        "pulse_position_features_inserted": 0,
        "pulse_feature_variables_upserted": 0,
        "pulse_online_analysis_rows": 0,
    }
    observed_features: set[str] = set()
    synced_measurement_ids: list[uuid.UUID] = []
    if not _pulse_analysis_tables_available(session):
        result["pulse_analysis_sync_skipped"] = True
        return result
    try:
        for visit in visits:
            pulse_records = _scalars(
                session,
                select(ModalityRecord).where(
                    ModalityRecord.visit_id == visit.visit_id,
                    ModalityRecord.modality_type == "pulse",
                    ModalityRecord.exists_flag.is_(True),
                ),
            )
            for modality_record in pulse_records:
                payload = modality_record.parsed_structured_data_json or {}
                for index, record in enumerate(payload.get("records") or [], start=1):
                    if not isinstance(record, dict):
                        continue
                    source_measurement_id = _source_measurement_id(modality_record, record, index)
                    measurement_id = _deterministic_uuid(f"pulse-measurement:{modality_record.modality_record_id}:{source_measurement_id}")
                    device_id = _upsert_pulse_device(session, visit, record)
                    feature_json = _numeric_items(record)
                    observed_features.update(feature_json)
                    stmt = insert(PulseMeasurement).values(
                        measurement_id=measurement_id,
                        visit_id=visit.visit_id,
                        modality_record_id=modality_record.modality_record_id,
                        user_id=visit.user_id,
                        device_id=device_id,
                        source_vendor=visit.source_vendor,
                        source_measurement_id=source_measurement_id,
                        start_time=visit.visit_time,
                        duration_seconds=record.get("duration_seconds"),
                        visit_slot=visit.visit_slot,
                        collection_hour=(visit.visit_time.hour + visit.visit_time.minute / 60) if visit.visit_time else None,
                        hand_side=record.get("side") or record.get("hand_side"),
                        pulse_position=record.get("position") or record.get("pulse_position") or "overall",
                        sampling_rate=record.get("sampling_rate"),
                        quality_status=visit.quality_status,
                        source_meta_json={
                            "source_asset_id": record.get("source_asset_id"),
                            "asset_file_name": record.get("asset_file_name"),
                            "pulse_type": record.get("pulse_type"),
                            "included": record.get("included"),
                            "parser_version": record.get("parser_version"),
                        },
                        feature_json=feature_json,
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["modality_record_id", "source_measurement_id"],
                        set_={
                            "visit_id": visit.visit_id,
                            "user_id": visit.user_id,
                            "device_id": device_id,
                            "start_time": visit.visit_time,
                            "duration_seconds": record.get("duration_seconds"),
                            "visit_slot": visit.visit_slot,
                            "collection_hour": (visit.visit_time.hour + visit.visit_time.minute / 60) if visit.visit_time else None,
                            "hand_side": record.get("side") or record.get("hand_side"),
                            "pulse_position": record.get("position") or record.get("pulse_position") or "overall",
                            "sampling_rate": record.get("sampling_rate"),
                            "quality_status": visit.quality_status,
                            "source_meta_json": {
                                "source_asset_id": record.get("source_asset_id"),
                                "asset_file_name": record.get("asset_file_name"),
                                "pulse_type": record.get("pulse_type"),
                                "included": record.get("included"),
                                "parser_version": record.get("parser_version"),
                            },
                            "feature_json": feature_json,
                        },
                    )
                    actual_measurement_id = session.execute(stmt.returning(PulseMeasurement.measurement_id)).scalar_one()
                    synced_measurement_ids.append(actual_measurement_id)
                    result["pulse_measurements_upserted"] = int(result["pulse_measurements_upserted"]) + 1
                    session.execute(delete(PulseWaveformAsset).where(PulseWaveformAsset.measurement_id == actual_measurement_id))
                    session.execute(delete(PulsePositionFeature).where(PulsePositionFeature.measurement_id == actual_measurement_id))
                    result["pulse_waveforms_inserted"] = int(result["pulse_waveforms_inserted"]) + _sync_waveform_asset(session, actual_measurement_id, record)
                    result["pulse_position_features_inserted"] = int(result["pulse_position_features_inserted"]) + _sync_position_features(session, actual_measurement_id, record)
        _upsert_feature_variables(session, observed_features)
        result["pulse_feature_variables_upserted"] = len(observed_features)
        result["pulse_online_analysis_rows"] = _sync_pulse_online_analysis(session, synced_measurement_ids)
    except ProgrammingError as exc:
        session.rollback()
        if any(name in str(exc) for name in ("fact_pulse_measurement", "dim_device", "dim_feature_variable")):
            result["pulse_analysis_sync_skipped"] = True
            return result
        raise
    return result


def _visit_query(payload: dict[str, Any]):
    stmt = select(Visit).order_by(Visit.visit_time.desc().nullslast(), Visit.created_at.desc())
    visit_id = payload.get("visit_id")
    if visit_id:
        stmt = stmt.where(Visit.visit_id == uuid.UUID(str(visit_id)))
    source_vendor = payload.get("source_vendor")
    if source_vendor:
        stmt = stmt.where(Visit.source_vendor == str(source_vendor))
    source_visit_id = payload.get("source_visit_id")
    if source_visit_id:
        stmt = stmt.where(Visit.source_visit_id == str(source_visit_id))
    limit = payload.get("limit")
    if limit:
        stmt = stmt.limit(max(1, int(limit)))
    return stmt


def parse_structured_data(session: Session, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    only_missing = _bool_value(payload.get("only_missing"), default=False)
    visits = _scalars(session, _visit_query(payload))

    result = {
        "visits_scanned": len(visits),
        "visits_parsed": 0,
        "modalities_updated": 0,
        "assets_seen": 0,
        "assets_ok": 0,
        "assets_metadata_only": 0,
        "assets_failed": 0,
        "assets_missing_file": 0,
        "feature_wide_rows": 0,
        "pulse_analysis_sync_skipped": False,
        "pulse_measurements_upserted": 0,
        "pulse_waveforms_inserted": 0,
        "pulse_position_features_inserted": 0,
        "pulse_feature_variables_upserted": 0,
        "pulse_online_analysis_rows": 0,
    }

    for visit in visits:
        modality_records = _scalars(
            session,
            select(ModalityRecord).where(ModalityRecord.visit_id == visit.visit_id),
        )
        if only_missing:
            modality_records = [item for item in modality_records if not item.parsed_structured_data_json]
        if not modality_records:
            continue

        assets = _scalars(session, select(FileAsset).where(FileAsset.visit_id == visit.visit_id))
        modality_by_record_id = {
            item.modality_record_id: item.modality_type
            for item in modality_records
        }
        structured_by_modality = build_structured_modalities(visit, assets, modality_by_record_id)
        updated_this_visit = 0

        for modality_record in modality_records:
            modality = str(modality_record.modality_type or "")
            if modality not in MODALITIES:
                continue
            payload_for_modality = _normalize_payload(visit, modality, structured_by_modality.get(modality))
            status_counts = Counter(
                str(item.get("parse_status") or "unknown")
                for item in payload_for_modality.get("assets") or []
            )
            result["assets_seen"] += payload_for_modality["asset_count"]
            result["assets_ok"] += status_counts.get("ok", 0)
            result["assets_metadata_only"] += status_counts.get("metadata_only", 0)
            result["assets_failed"] += status_counts.get("failed", 0)
            result["assets_missing_file"] += status_counts.get("missing_file", 0)

            modality_record.parsed_structured_data_json = payload_for_modality
            modality_record.feature_summary_json = _feature_summary(payload_for_modality)
            updated_this_visit += 1

        if updated_this_visit:
            result["visits_parsed"] += 1
            result["modalities_updated"] += updated_this_visit

    pulse_sync_result = sync_pulse_analysis_tables(session, visits)
    result.update(pulse_sync_result)
    result["feature_wide_rows"] = rebuild_visit_feature_wide(session, visits)
    return result
