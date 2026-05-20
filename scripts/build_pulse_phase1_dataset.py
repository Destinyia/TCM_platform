from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.database import SessionLocal, get_engine
from backend.app.models import (
    Device,
    FeatureVariable,
    ModalityRecord,
    PulseMeasurement,
    PulsePositionFeature,
    PulseWaveformAsset,
    User,
    Visit,
)


DEFAULT_DATASET_ID = "DS-PULSE-PHASE1"
DEFAULT_VERSION = "v2026.05.phase1.001"
QUALITY_FEATURE_NAMES = {"stability_score", "signal_quality_score", "artifact_ratio"}


def json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "as_tuple"):
        return float(value)
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=json_default))
            handle.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, default=json_default) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def maybe_write_parquet(path: Path, rows: list[dict[str, Any]]) -> bool:
    try:
        import pandas as pd

        pd.DataFrame(rows).to_parquet(path, index=False)
        return True
    except Exception:
        return False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_measurements() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    get_engine()
    with SessionLocal() as session:
        try:
            measurement_rows = session.execute(
                select(PulseMeasurement, Visit, User, Device)
                .join(Visit, Visit.visit_id == PulseMeasurement.visit_id)
                .join(User, User.user_id == PulseMeasurement.user_id)
                .outerjoin(Device, Device.device_id == PulseMeasurement.device_id)
                .order_by(PulseMeasurement.start_time, PulseMeasurement.measurement_id)
            ).all()
            waveform_rows = session.execute(select(PulseWaveformAsset).order_by(PulseWaveformAsset.measurement_id, PulseWaveformAsset.channel_name)).scalars().all()
            position_rows = session.execute(select(PulsePositionFeature).order_by(PulsePositionFeature.measurement_id, PulsePositionFeature.pulse_position, PulsePositionFeature.feature_name)).scalars().all()
            variable_rows = session.execute(select(FeatureVariable).where(FeatureVariable.modality_type == "pulse").order_by(FeatureVariable.feature_name)).scalars().all()
        except ProgrammingError as exc:
            session.rollback()
            if "fact_pulse_measurement" not in str(exc):
                raise
            return load_measurements_from_records(session)

        if not measurement_rows:
            fallback = load_measurements_from_records(session)
            if fallback[0]:
                return fallback

    measurements: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    for measurement, visit, user, device in measurement_rows:
        quality_flags = (visit.cheat_types or {}).get("flags") or []
        measurements.append(
            {
                "measurement_id": str(measurement.measurement_id),
                "sample_id": f"pulse-{measurement.measurement_id}",
                "visit_id": str(measurement.visit_id),
                "modality_record_id": str(measurement.modality_record_id),
                "user_id": str(measurement.user_id),
                "user_display_id": f"DEID-{str(measurement.user_id)[:8]}",
                "source_vendor": measurement.source_vendor,
                "source_measurement_id": measurement.source_measurement_id,
                "source_visit_id": visit.source_visit_id,
                "start_time": measurement.start_time,
                "duration_seconds": measurement.duration_seconds,
                "visit_slot": measurement.visit_slot,
                "collection_hour": measurement.collection_hour,
                "hand_side": measurement.hand_side,
                "pulse_position": measurement.pulse_position,
                "device_id": str(measurement.device_id) if measurement.device_id else None,
                "device_model": device.device_model if device else None,
                "source_device_id": device.source_device_id if device else None,
                "sampling_rate": measurement.sampling_rate,
                "quality_status": measurement.quality_status,
                "quality_flags": quality_flags,
            }
        )
        for feature_name, feature_value in (measurement.feature_json or {}).items():
            features.append(
                {
                    "measurement_id": str(measurement.measurement_id),
                    "visit_id": str(measurement.visit_id),
                    "user_id": str(measurement.user_id),
                    "source_vendor": measurement.source_vendor,
                    "device_id": str(measurement.device_id) if measurement.device_id else None,
                    "feature_level": "measurement",
                    "feature_name": feature_name,
                    "feature_value": feature_value,
                }
            )

    waveforms = [
        {
            "waveform_asset_id": str(item.waveform_asset_id),
            "measurement_id": str(item.measurement_id),
            "asset_id": str(item.asset_id) if item.asset_id else None,
            "channel_name": item.channel_name,
            "hand_side": item.hand_side,
            "pulse_position": item.pulse_position,
            "sample_count": item.sample_count,
            "sampling_rate": item.sampling_rate,
            "storage_uri": item.storage_uri,
            "data_format": item.data_format,
            "file_hash": item.file_hash,
            "preview_json": item.preview_json,
            "summary_json": item.summary_json,
        }
        for item in waveform_rows
    ]
    position_features = [
        {
            "position_feature_id": str(item.position_feature_id),
            "measurement_id": str(item.measurement_id),
            "hand_side": item.hand_side,
            "pulse_position": item.pulse_position,
            "feature_name": item.feature_name,
            "feature_value": item.feature_value,
            "feature_text": item.feature_text,
            "feature_unit": item.feature_unit,
            "source_field": item.source_field,
            "parser_version": item.parser_version,
            "quality_weight": item.quality_weight,
        }
        for item in position_rows
    ]
    variables = [
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
        for item in variable_rows
    ]
    return measurements, features, waveforms, position_features, variables


def load_measurements_from_records(session) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = session.execute(
        select(ModalityRecord, Visit, User)
        .join(Visit, Visit.visit_id == ModalityRecord.visit_id)
        .join(User, User.user_id == Visit.user_id)
        .where(ModalityRecord.modality_type == "pulse", ModalityRecord.exists_flag.is_(True))
        .order_by(Visit.visit_time, ModalityRecord.modality_record_id)
    ).all()

    measurements: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []
    waveforms: list[dict[str, Any]] = []
    position_features: list[dict[str, Any]] = []
    observed_features: set[str] = set()

    for modality, visit, _user in rows:
        payload = modality.parsed_structured_data_json or {}
        for index, record in enumerate(payload.get("records") or [], start=1):
            source_measurement_id = str(record.get("record_id") or record.get("source_measurement_id") or f"{modality.modality_record_id}:{index}")
            measurement_id = f"{modality.modality_record_id}:{source_measurement_id}"
            hand_side = record.get("side") or record.get("hand_side")
            device_id = record.get("device_id") or f"{visit.source_vendor}:unknown"
            measurements.append(
                {
                    "measurement_id": measurement_id,
                    "sample_id": f"pulse-{measurement_id}",
                    "visit_id": str(visit.visit_id),
                    "modality_record_id": str(modality.modality_record_id),
                    "user_id": str(visit.user_id),
                    "user_display_id": f"DEID-{str(visit.user_id)[:8]}",
                    "source_vendor": visit.source_vendor,
                    "source_measurement_id": source_measurement_id,
                    "source_visit_id": visit.source_visit_id,
                    "start_time": visit.visit_time,
                    "duration_seconds": record.get("duration_seconds"),
                    "visit_slot": visit.visit_slot,
                    "collection_hour": (visit.visit_time.hour + visit.visit_time.minute / 60) if visit.visit_time else None,
                    "hand_side": hand_side,
                    "pulse_position": record.get("pulse_position") or "overall",
                    "device_id": device_id,
                    "device_model": record.get("device_model"),
                    "source_device_id": record.get("source_device_id") or "unknown",
                    "sampling_rate": record.get("sampling_rate"),
                    "quality_status": visit.quality_status,
                    "quality_flags": (visit.cheat_types or {}).get("flags") or [],
                }
            )

            for key, value in record.items():
                if isinstance(value, (int, float)) and key not in {"duration_seconds", "sampling_rate"}:
                    observed_features.add(key)
                    features.append(
                        {
                            "measurement_id": measurement_id,
                            "visit_id": str(visit.visit_id),
                            "user_id": str(visit.user_id),
                            "source_vendor": visit.source_vendor,
                            "device_id": device_id,
                            "feature_level": "measurement",
                            "feature_name": key,
                            "feature_value": value,
                        }
                    )

            preview = record.get("waveform_preview") or []
            summary = record.get("waveform_summary") or {}
            if preview or summary:
                waveforms.append(
                    {
                        "waveform_asset_id": f"{measurement_id}:preview",
                        "measurement_id": measurement_id,
                        "asset_id": None,
                        "channel_name": "waveform_preview",
                        "hand_side": hand_side,
                        "pulse_position": record.get("pulse_position") or "overall",
                        "sample_count": summary.get("sample_count") if isinstance(summary, dict) else None,
                        "sampling_rate": record.get("sampling_rate"),
                        "storage_uri": None,
                        "data_format": "json_preview",
                        "file_hash": None,
                        "preview_json": preview,
                        "summary_json": summary,
                    }
                )

            for measurement_item in record.get("measurements") or []:
                if not isinstance(measurement_item, dict):
                    continue
                position = measurement_item.get("position") or measurement_item.get("pulse_position") or "unknown"
                item_side = measurement_item.get("side") or measurement_item.get("hand_side") or hand_side
                for key, value in measurement_item.items():
                    if key in {"position", "pulse_position", "side", "hand_side"}:
                        continue
                    if isinstance(value, (int, float, str)):
                        position_features.append(
                            {
                                "position_feature_id": f"{measurement_id}:{position}:{key}",
                                "measurement_id": measurement_id,
                                "hand_side": item_side,
                                "pulse_position": position,
                                "feature_name": key,
                                "feature_value": value if isinstance(value, (int, float)) else None,
                                "feature_text": value if isinstance(value, str) else None,
                                "feature_unit": None,
                                "source_field": key,
                                "parser_version": record.get("parser_version"),
                                "quality_weight": record.get("stability_score"),
                            }
                        )

    variables = [
        {
            "feature_name": name,
            "display_name": name,
            "modality_type": "pulse",
            "feature_level": "measurement",
            "source_vendor": "standard",
            "data_type": "numeric",
            "unit": None,
            "category": "quality" if name in QUALITY_FEATURE_NAMES else "unknown",
            "is_ml_feature": name not in QUALITY_FEATURE_NAMES,
            "is_quality_feature": name in QUALITY_FEATURE_NAMES,
            "valid_range_json": None,
            "description": "Inferred from parsed pulse records fallback export.",
        }
        for name in sorted(observed_features)
    ]
    return measurements, features, waveforms, position_features, variables


def build_manifest(measurements: list[dict[str, Any]], features: list[dict[str, Any]], waveforms: list[dict[str, Any]], position_features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    features_by_measurement: dict[str, dict[str, Any]] = {}
    for row in features:
        features_by_measurement.setdefault(row["measurement_id"], {})[row["feature_name"]] = row["feature_value"]
    waveforms_by_measurement: dict[str, list[dict[str, Any]]] = {}
    for row in waveforms:
        waveforms_by_measurement.setdefault(row["measurement_id"], []).append(row)
    position_count: dict[str, int] = {}
    for row in position_features:
        position_count[row["measurement_id"]] = position_count.get(row["measurement_id"], 0) + 1

    manifest = []
    for row in measurements:
        measurement_id = row["measurement_id"]
        manifest.append(
            {
                "sample_id": row["sample_id"],
                "measurement_id": measurement_id,
                "visit_id": row["visit_id"],
                "user_id": row["user_display_id"],
                "source_vendor": row["source_vendor"],
                "source_measurement_id": row["source_measurement_id"],
                "visit_slot": row["visit_slot"],
                "start_time": json_default(row["start_time"]) if row.get("start_time") else None,
                "modalities": ["pulse"],
                "quality_status": row["quality_status"],
                "quality_flags": row.get("quality_flags") or [],
                "features": features_by_measurement.get(measurement_id, {}),
                "assets": [
                    {
                        "asset_id": item["asset_id"],
                        "asset_type": "pulse_waveform",
                        "storage_uri": item["storage_uri"],
                        "channel_name": item["channel_name"],
                        "data_format": item["data_format"],
                    }
                    for item in waveforms_by_measurement.get(measurement_id, [])
                ],
                "high_dim": {"position_feature_count": position_count.get(measurement_id, 0)},
            }
        )
    return manifest


def write_dataset_card(path: Path, dataset_id: str, version: str, summary: dict[str, Any]) -> None:
    path.write_text(
        "\n".join(
            [
                f"# {dataset_id} {version}",
                "",
                "## Purpose",
                "",
                "Pulse analysis phase 1 dataset for measurement quality, drift, stable segment, device consistency, and feature reliability experiments.",
                "",
                "## Coupling Boundary",
                "",
                "This dataset is an exported research package. Downstream analysis scripts consume files in this directory and do not require direct access to platform internals.",
                "",
                "## Files",
                "",
                "- `manifest.jsonl`: sample-level index.",
                "- `measurements.csv/jsonl`: pulse measurement metadata.",
                "- `measurement_features.csv/jsonl`: measurement-level feature rows.",
                "- `waveform_manifest.jsonl`: waveform asset index and preview summaries.",
                "- `position_features.csv/jsonl`: position-level pulse details.",
                "- `feature_variables.csv/jsonl`: feature dictionary.",
                "- `summary.json`: export summary and checksums.",
                "",
                "## Summary",
                "",
                f"- measurements: {summary['measurement_count']}",
                f"- users: {summary['user_count']}",
                f"- waveform assets: {summary['waveform_count']}",
                f"- position features: {summary['position_feature_count']}",
            ]
        ),
        encoding="utf-8",
    )


def build_dataset(output_dir: Path, dataset_id: str, version: str) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    measurements, features, waveforms, position_features, variables = load_measurements()
    manifest = build_manifest(measurements, features, waveforms, position_features)

    write_jsonl(output_dir / "manifest.jsonl", manifest)
    write_jsonl(output_dir / "measurements.jsonl", measurements)
    write_jsonl(output_dir / "measurement_features.jsonl", features)
    write_jsonl(output_dir / "waveform_manifest.jsonl", waveforms)
    write_jsonl(output_dir / "position_features.jsonl", position_features)
    write_jsonl(output_dir / "feature_variables.jsonl", variables)

    write_csv(output_dir / "measurements.csv", measurements)
    write_csv(output_dir / "measurement_features.csv", features)
    write_csv(output_dir / "position_features.csv", position_features)
    write_csv(output_dir / "feature_variables.csv", variables)

    parquet_written = {
        "measurements": maybe_write_parquet(output_dir / "measurements.parquet", measurements),
        "measurement_features": maybe_write_parquet(output_dir / "measurement_features.parquet", features),
        "position_features": maybe_write_parquet(output_dir / "position_features.parquet", position_features),
        "feature_variables": maybe_write_parquet(output_dir / "feature_variables.parquet", variables),
    }

    summary = {
        "dataset_id": dataset_id,
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "measurement_count": len(measurements),
        "user_count": len({row["user_id"] for row in measurements}),
        "feature_row_count": len(features),
        "waveform_count": len(waveforms),
        "position_feature_count": len(position_features),
        "feature_variable_count": len(variables),
        "parquet_written": parquet_written,
    }
    write_dataset_card(output_dir / "dataset_card.md", dataset_id, version, summary)

    checksums = {}
    for file_path in sorted(output_dir.iterdir()):
        if file_path.is_file() and file_path.name != "summary.json":
            checksums[file_path.name] = sha256_file(file_path)
    summary["checksums"] = checksums
    write_json(output_dir / "summary.json", summary)
    return summary


def print_summary(output_dir: Path, summary: dict[str, Any]) -> None:
    print(f"Built pulse phase 1 dataset: {output_dir}")
    print(f"  dataset_id: {summary['dataset_id']}")
    print(f"  version: {summary['version']}")
    print(f"  measurements: {summary['measurement_count']}")
    print(f"  users: {summary['user_count']}")
    print(f"  feature rows: {summary['feature_row_count']}")
    print(f"  waveform assets: {summary['waveform_count']}")
    print(f"  position features: {summary['position_feature_count']}")
    print(f"  feature variables: {summary['feature_variable_count']}")
    parquet_status = ", ".join(f"{key}={'yes' if value else 'no'}" for key, value in summary["parquet_written"].items())
    print(f"  parquet: {parquet_status}")
    print(f"  manifest: {output_dir / 'manifest.jsonl'}")
    print(f"  summary: {output_dir / 'summary.json'}")
    if summary["measurement_count"] == 0:
        print("  warning: no pulse measurements were exported. Run parse-only first, or check pulse records in fact_modality_record.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a low-coupling pulse phase 1 research dataset from platform tables.")
    parser.add_argument("--dataset-id", default=DEFAULT_DATASET_ID)
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--output-root", default="storage/datasets")
    parser.add_argument("--output-dir", help="Explicit output directory. Defaults to output-root/dataset-id/version.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else Path(args.output_root) / args.dataset_id / args.version
    summary = build_dataset(output_dir, args.dataset_id, args.version)
    print_summary(output_dir, summary)


if __name__ == "__main__":
    main()
