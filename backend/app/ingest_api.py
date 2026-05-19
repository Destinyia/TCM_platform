from __future__ import annotations

import re
from pathlib import Path

from flask import Blueprint, jsonify, request

from backend.app.database import SessionLocal, get_engine
from backend.app.storage_loader import load_standard_storage
from backend.app.structured_ingest import parse_structured_data

ingest_api = Blueprint("ingest_api", __name__)


def resolve_shared_path(value: str | None) -> Path | None:
    if not value:
        return None
    original = Path(value)
    if original.exists():
        return original

    text = str(value)
    windows_match = re.match(r"^([A-Za-z]):[\\/](.*)$", text)
    if windows_match:
        drive = windows_match.group(1).lower()
        rest = windows_match.group(2).replace("\\", "/")
        wsl_path = Path(f"/mnt/{drive}/{rest}")
        if wsl_path.exists():
            return wsl_path

    wsl_match = re.match(r"^/mnt/([A-Za-z])/(.*)$", text)
    if wsl_match:
        drive = wsl_match.group(1).upper()
        rest = wsl_match.group(2).replace("/", "\\")
        windows_path = Path(f"{drive}:\\{rest}")
        if windows_path.exists():
            return windows_path

    return original


@ingest_api.route("/standard-storage", methods=["POST", "OPTIONS"])
def standard_storage():
    if request.method == "OPTIONS":
        return "", 204
    payload = request.get_json(silent=True) or {}
    records_path = payload.get("records_path")
    assets_path = payload.get("assets_path")
    if not records_path:
        return jsonify({"message": "records_path is required"}), 400
    records = resolve_shared_path(records_path)
    assets = resolve_shared_path(assets_path) if assets_path else None
    if not records.exists():
        return jsonify({"message": f"records_path not found: {records}", "received": records_path}), 400
    if assets and not assets.exists():
        return jsonify({"message": f"assets_path not found: {assets}", "received": assets_path}), 400

    get_engine()
    with SessionLocal() as session:
        result = load_standard_storage(session, records, assets)
        session.commit()
    return jsonify({"status": "ok", "result": result})


@ingest_api.route("/parse-structured-data", methods=["POST", "OPTIONS"])
def parse_structured_data_endpoint():
    if request.method == "OPTIONS":
        return "", 204
    payload = request.get_json(silent=True) or {}
    get_engine()
    try:
        with SessionLocal() as session:
            result = parse_structured_data(session, payload)
            session.commit()
    except (TypeError, ValueError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "ok", "result": result})
