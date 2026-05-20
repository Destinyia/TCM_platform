from __future__ import annotations

from flask import Flask

from backend.app.demo_api import demo_api
from backend.app.ingest_api import ingest_api
from backend.app.pulse_api import pulse_api


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(demo_api, url_prefix="/api/demo")
    app.register_blueprint(ingest_api, url_prefix="/api/ingest")
    app.register_blueprint(pulse_api, url_prefix="/api/pulse")

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.route("/api/health", methods=["GET"])
    def health():
        return {"status": "ok"}

    return app
