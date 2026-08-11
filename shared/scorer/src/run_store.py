"""Persist scoring runs to disk so the UI can browse and diff iterations.

Layout:
    runs/<scorer_name>/<ISO-timestamp>-<spechash8>/
        manifest.json       {timestamp, scorer_name, org, session_ids[],
                             spec_sha256, agent_filter}
        spec.yaml           verbatim copy of the YAML at run time
        prompt.xml          rendered GenAiPromptTemplate XML
        sessions.json       [{session_id, start_time, channel}, ...]
        stdm/<sid>.json     full STDM per session
        results.json        [{session_id, label, reason, raw_response_text}]
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .scorer_spec import ScorerSpec
from .xml_render import render as render_template

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"

_SAFE_SID_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe_sid(session_id: str) -> str:
    return _SAFE_SID_RE.sub("_", session_id)


def _now_iso_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    scorer_name: str
    timestamp: str
    org: str
    session_count: int
    spec_sha256: str
    agent_filter: str | None


def save_run(
    *,
    spec: ScorerSpec,
    spec_source_path: Path | str,
    org: str,
    sessions: list[dict],
    stdms: dict[str, dict],
    results: list[dict],
    agent_filter: str | None = None,
) -> str:
    """Persist a scoring run to disk and return the run_id.

    `results` items are plain dicts with keys: session_id, label, reason, raw_response_text.
    `stdms` maps session_id -> STDM dict.
    """
    spec_path = Path(spec_source_path)
    raw_yaml_bytes = spec_path.read_bytes()
    spec_sha = _sha256_bytes(raw_yaml_bytes)
    timestamp = _now_iso_compact()
    run_id = f"{timestamp}-{spec_sha[:8]}"

    run_dir = RUNS_DIR / spec.name / run_id
    stdm_dir = run_dir / "stdm"
    stdm_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "spec.yaml").write_bytes(raw_yaml_bytes)
    (run_dir / "prompt.xml").write_text(render_template(spec), encoding="utf-8")
    (run_dir / "sessions.json").write_text(
        json.dumps(sessions, indent=2), encoding="utf-8"
    )
    (run_dir / "results.json").write_text(
        json.dumps(results, indent=2), encoding="utf-8"
    )
    for sid, stdm in stdms.items():
        (stdm_dir / f"{_safe_sid(sid)}.json").write_text(
            json.dumps(stdm, indent=2), encoding="utf-8"
        )

    manifest = {
        "timestamp": timestamp,
        "run_id": run_id,
        "scorer_name": spec.name,
        "org": org,
        "session_ids": [s.get("session_id") for s in sessions],
        "spec_sha256": spec_sha,
        "agent_filter": agent_filter,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return run_id


def list_scorers_with_runs() -> list[str]:
    """Names of scorers that have at least one run on disk."""
    if not RUNS_DIR.exists():
        return []
    return sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir())


def list_runs(scorer_name: str) -> list[RunSummary]:
    """List live-session runs for a scorer, newest first.

    Skips test-suite snapshots (manifest `kind == "test-suite"`); those are
    listed by `list_test_runs()`. Both kinds share the same on-disk layout
    under `runs/<scorer>/`, distinguished only by manifest content.
    """
    scorer_dir = RUNS_DIR / scorer_name
    if not scorer_dir.exists():
        return []
    out: list[RunSummary] = []
    for run_dir in scorer_dir.iterdir():
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("kind") == "test-suite":
            continue
        out.append(
            RunSummary(
                run_id=m.get("run_id", run_dir.name),
                scorer_name=m.get("scorer_name", scorer_name),
                timestamp=m.get("timestamp", ""),
                org=m.get("org", ""),
                session_count=len(m.get("session_ids") or []),
                spec_sha256=m.get("spec_sha256", ""),
                agent_filter=m.get("agent_filter"),
            )
        )
    out.sort(key=lambda r: r.timestamp, reverse=True)
    return out


def list_test_runs(scorer_name: str) -> list[dict]:
    """List AI Testing Center snapshots for a scorer, newest first.

    Each entry mirrors the manifest.json the bash runner writes
    (`kind: test-suite`). The companion UI's Tests tab consumes this list.
    """
    scorer_dir = RUNS_DIR / scorer_name
    if not scorer_dir.exists():
        return []
    out: list[dict] = []
    for run_dir in scorer_dir.iterdir():
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("kind") != "test-suite":
            continue
        out.append({
            "run_id": m.get("run_id", run_dir.name),
            "scorer_name": m.get("scorer_name", scorer_name),
            "agent_name": m.get("agent_name"),
            "test_def_name": m.get("test_def_name"),
            "ai_testing_run_id": m.get("ai_testing_run_id"),
            "started_at": m.get("started_at"),
            "completed_at": m.get("completed_at"),
            "case_count": m.get("case_count", 0),
        })
    out.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return out


def load_test_run(scorer_name: str, run_id: str) -> dict:
    """Load a test-suite snapshot — manifest + per-utterance summary.

    The full Connect API payload remains on disk at `test_results.json` for
    drill-down; the UI displays the distilled `summary.json` by default.
    """
    path = _run_dir(scorer_name, run_id)
    manifest_path = path / "manifest.json"
    summary_path = path / "summary.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Test run manifest missing: {scorer_name}/{run_id}")
    if not summary_path.exists():
        raise FileNotFoundError(f"Test run summary missing: {scorer_name}/{run_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {"manifest": manifest, "summary": summary}


def _run_dir(scorer_name: str, run_id: str) -> Path:
    path = RUNS_DIR / scorer_name / run_id
    if not path.exists():
        raise FileNotFoundError(f"Run not found: {scorer_name}/{run_id}")
    return path


def load_run(scorer_name: str, run_id: str) -> dict:
    """Read a run's manifest + results + sessions + spec.yaml + prompt.xml.

    Does NOT inline STDM dicts (those are large; callers fetch via load_stdm()).
    """
    path = _run_dir(scorer_name, run_id)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    results = json.loads((path / "results.json").read_text(encoding="utf-8"))
    sessions = json.loads((path / "sessions.json").read_text(encoding="utf-8"))
    raw_yaml = (path / "spec.yaml").read_text(encoding="utf-8")
    prompt_xml = (path / "prompt.xml").read_text(encoding="utf-8")
    stdm_dir = path / "stdm"
    stdm_available = (
        sorted(p.stem for p in stdm_dir.glob("*.json")) if stdm_dir.exists() else []
    )
    return {
        "manifest": manifest,
        "sessions": sessions,
        "results": results,
        "raw_yaml": raw_yaml,
        "prompt_xml": prompt_xml,
        "stdm_available": stdm_available,
    }


def load_stdm(scorer_name: str, run_id: str, session_id: str) -> dict:
    path = _run_dir(scorer_name, run_id) / "stdm" / f"{_safe_sid(session_id)}.json"
    if not path.exists():
        raise FileNotFoundError(f"STDM not found for session {session_id} in run {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _distribution(results: Iterable[dict]) -> dict[str, int]:
    tally: dict[str, int] = {}
    for r in results:
        key = r.get("label") or "(unparseable)"
        tally[key] = tally.get(key, 0) + 1
    return tally


def _unified_diff(a: str, b: str, a_label: str, b_label: str) -> str:
    a_lines = a.splitlines(keepends=True)
    b_lines = b.splitlines(keepends=True)
    return "".join(difflib.unified_diff(a_lines, b_lines, a_label, b_label, n=3))


def diff_runs(scorer_name: str, a_id: str, b_id: str) -> dict:
    """Compute a full comparison payload between two runs of the same scorer."""
    a = load_run(scorer_name, a_id)
    b = load_run(scorer_name, b_id)

    yaml_diff = _unified_diff(
        a["raw_yaml"], b["raw_yaml"],
        f"a/{a_id}/spec.yaml", f"b/{b_id}/spec.yaml",
    )
    xml_diff = _unified_diff(
        a["prompt_xml"], b["prompt_xml"],
        f"a/{a_id}/prompt.xml", f"b/{b_id}/prompt.xml",
    )

    a_by_sid = {r["session_id"]: r for r in a["results"]}
    b_by_sid = {r["session_id"]: r for r in b["results"]}
    all_sids = list(a_by_sid.keys()) + [s for s in b_by_sid if s not in a_by_sid]
    per_session = []
    for sid in all_sids:
        ra = a_by_sid.get(sid)
        rb = b_by_sid.get(sid)
        label_a = ra.get("label") if ra else None
        label_b = rb.get("label") if rb else None
        per_session.append({
            "session_id": sid,
            "a": {"label": label_a, "reason": ra.get("reason") if ra else None}
                 if ra else None,
            "b": {"label": label_b, "reason": rb.get("reason") if rb else None}
                 if rb else None,
            "changed": label_a != label_b,
        })

    return {
        "a": {
            "run_id": a_id,
            "timestamp": a["manifest"].get("timestamp"),
            "spec_sha256": a["manifest"].get("spec_sha256"),
            "scorer_name": scorer_name,
        },
        "b": {
            "run_id": b_id,
            "timestamp": b["manifest"].get("timestamp"),
            "spec_sha256": b["manifest"].get("spec_sha256"),
            "scorer_name": scorer_name,
        },
        "yaml_diff": yaml_diff,
        "xml_diff": xml_diff,
        "per_session": per_session,
        "distribution": {
            "a": _distribution(a["results"]),
            "b": _distribution(b["results"]),
        },
    }


def summary_to_dict(s: RunSummary) -> dict:
    return asdict(s)
