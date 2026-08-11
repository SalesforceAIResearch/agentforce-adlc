"""Flask app that serves the single-page scorer UI and backing JSON API.

Designed to run bound to 127.0.0.1 only; the org alias is configured at
launch (via `scorer-cli ui --org`) and is never accepted over the wire.
"""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from . import run_store, scorer_spec
from .scorer_spec import BUNDLED_DIR, ScorerSpecError
from .xml_render import render as render_template
from .xml_render import render_scorer_definition

REPO_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = REPO_ROOT / "web"


def create_app(*, org: str) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["ORG"] = org

    # ---- static page ------------------------------------------------------
    @app.route("/")
    def index():  # type: ignore[unused-ignore]
        return send_from_directory(WEB_DIR, "index.html")

    @app.route("/healthz")
    def healthz():
        return "ok", 200

    @app.route("/api/config")
    def api_config():
        return jsonify({"org": app.config["ORG"]})

    # ---- scorers (source YAML on disk) -----------------------------------
    @app.route("/api/scorers")
    def api_scorers():
        out = []
        for path in sorted(BUNDLED_DIR.glob("*.yaml")):
            try:
                spec = scorer_spec.load(path.stem)
            except ScorerSpecError:
                continue
            out.append({
                "name": spec.name,
                "description": spec.description,
                "data_type": spec.data_type,
                "labels": list(spec.allowed_labels),
                "fallback_label": spec.fallback_label,
                "path": str(path.relative_to(REPO_ROOT)),
            })
        return jsonify(out)

    @app.route("/api/scorers/<name>")
    def api_scorer(name: str):
        try:
            spec = scorer_spec.load(name)
        except ScorerSpecError as e:
            return jsonify({"error": str(e)}), 404
        path = scorer_spec._resolve_path(name)
        try:
            pt_xml = render_template(spec)
        except Exception as e:
            pt_xml = f"<!-- prompt-template render error: {e} -->"
        # The scorer-definition XML only makes sense when an agent is bound.
        # Otherwise, render it with a placeholder agent so users still see the
        # shape they'll get once they bind and deploy.
        if spec.agent_api_name:
            def_spec = spec
        else:
            from dataclasses import replace
            def_spec = replace(spec, agent_api_name="<agent_api_name>")
        try:
            scorer_def_xml = render_scorer_definition(def_spec)
        except Exception as e:
            scorer_def_xml = f"<!-- scorer-definition render error: {e} -->"
        return jsonify({
            "spec": _spec_to_dict(spec),
            "raw_yaml": path.read_text(encoding="utf-8"),
            "rendered_xml": pt_xml,
            "scorer_definition_xml": scorer_def_xml,
        })

    # ---- runs (snapshot history on disk) ---------------------------------
    @app.route("/api/runs")
    def api_runs():
        scorer = request.args.get("scorer")
        if scorer:
            summaries = run_store.list_runs(scorer)
            return jsonify([run_store.summary_to_dict(s) for s in summaries])
        # No scorer param: list scorers that have runs at all.
        return jsonify({"scorers_with_runs": run_store.list_scorers_with_runs()})

    @app.route("/api/runs/diff")
    def api_runs_diff():
        scorer = request.args.get("scorer")
        a = request.args.get("a")
        b = request.args.get("b")
        if not scorer or not a or not b:
            return jsonify({"error": "scorer, a, b required"}), 400
        try:
            return jsonify(run_store.diff_runs(scorer, a, b))
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404

    @app.route("/api/runs/<scorer>/<run_id>")
    def api_run(scorer: str, run_id: str):
        try:
            return jsonify(run_store.load_run(scorer, run_id))
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404

    @app.route("/api/runs/<scorer>/<run_id>/stdm/<path:session_id>")
    def api_run_stdm(scorer: str, run_id: str, session_id: str):
        try:
            return jsonify(run_store.load_stdm(scorer, run_id, session_id))
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404

    # ---- test-suite runs (AI Testing Center snapshots) -------------------
    @app.route("/api/test-runs")
    def api_test_runs():
        scorer = request.args.get("scorer")
        if not scorer:
            return jsonify({"error": "scorer required"}), 400
        return jsonify(run_store.list_test_runs(scorer))

    @app.route("/api/test-runs/<scorer>/<run_id>")
    def api_test_run(scorer: str, run_id: str):
        try:
            return jsonify(run_store.load_test_run(scorer, run_id))
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404

    return app


def _spec_to_dict(spec) -> dict:
    """Convert ScorerSpec (frozen dataclass with tuple) to a JSON-friendly dict."""
    d = asdict(spec)
    # allowed_labels is a tuple; asdict converts to list already.
    return d
