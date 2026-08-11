"""Tests for tools/install.py shipping the vendored scorer CLI (shared/scorer).

The scorer CLI must land at ``<skills_dir>/../shared/scorer`` so the
``../../shared/scorer/...`` reference links inside skill dirs resolve in file-copy
(Cursor/legacy) installs, and be removed on uninstall. Runtime output dirs (runs/,
rendered XML) and caches must NOT be shipped.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent


def _load_install_module():
    spec = importlib.util.spec_from_file_location(
        "adlc_install", str(REPO_ROOT / "tools" / "install.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def install_mod():
    return _load_install_module()


def _make_fake_source(tmp_path: Path) -> Path:
    """Build a minimal source tree resembling the repo's shared/scorer layout."""
    src = tmp_path / "source"
    scorer = src / "shared" / "scorer"
    (scorer / "src").mkdir(parents=True)
    (scorer / "src" / "cli.py").write_text("# cli\n")
    (scorer / "references").mkdir()
    (scorer / "references" / "scorer-authoring.md").write_text("# authoring\n")
    (scorer / "scorer_specs").mkdir()
    (scorer / "scorer_specs" / "sample.yaml").write_text("name: sample\n")
    # Runtime / cache dirs that must be excluded.
    (scorer / "runs" / "old_run").mkdir(parents=True)
    (scorer / "runs" / "old_run" / "results.json").write_text("[]")
    (scorer / "scorer_specs" / "rendered" / "x").mkdir(parents=True)
    (scorer / "scorer_specs" / "rendered" / "x" / "pt.xml").write_text("<xml/>")
    (scorer / "src" / "__pycache__").mkdir()
    (scorer / "src" / "__pycache__" / "cli.cpython-311.pyc").write_text("bytecode")
    return src


def _fake_target(tmp_path: Path) -> dict:
    base = tmp_path / "target"
    skills_dir = base / "skills"
    skills_dir.mkdir(parents=True)
    return {"name": "cursor", "skills_dir": skills_dir}


def test_install_shared_scorer_copies_tree(install_mod, tmp_path):
    src = _make_fake_source(tmp_path)
    tgt = _fake_target(tmp_path)

    ok = install_mod.install_shared_scorer(src, tgt, dry_run=False)
    assert ok is True

    dest = tgt["skills_dir"].parent / "shared" / "scorer"
    # Source files present.
    assert (dest / "src" / "cli.py").exists()
    assert (dest / "references" / "scorer-authoring.md").exists()
    assert (dest / "scorer_specs" / "sample.yaml").exists()


def test_install_shared_scorer_excludes_runtime_and_cache(install_mod, tmp_path):
    src = _make_fake_source(tmp_path)
    tgt = _fake_target(tmp_path)
    install_mod.install_shared_scorer(src, tgt, dry_run=False)

    dest = tgt["skills_dir"].parent / "shared" / "scorer"
    assert not (dest / "runs").exists(), "runs/ must not ship"
    assert not (dest / "scorer_specs" / "rendered").exists(), "rendered XML must not ship"
    assert not (dest / "src" / "__pycache__").exists(), "__pycache__ must not ship"


def test_install_shared_scorer_dry_run_writes_nothing(install_mod, tmp_path):
    src = _make_fake_source(tmp_path)
    tgt = _fake_target(tmp_path)
    ok = install_mod.install_shared_scorer(src, tgt, dry_run=True)
    assert ok is True
    dest = tgt["skills_dir"].parent / "shared" / "scorer"
    assert not dest.exists()


def test_install_shared_scorer_missing_source_returns_false(install_mod, tmp_path):
    empty_src = tmp_path / "empty"
    empty_src.mkdir()
    tgt = _fake_target(tmp_path)
    assert install_mod.install_shared_scorer(empty_src, tgt, dry_run=False) is False


def test_install_shared_scorer_replaces_existing(install_mod, tmp_path):
    """A stale file from a prior install must be gone after reinstall (safe_rmtree)."""
    src = _make_fake_source(tmp_path)
    tgt = _fake_target(tmp_path)
    dest = tgt["skills_dir"].parent / "shared" / "scorer"
    dest.mkdir(parents=True)
    (dest / "STALE.txt").write_text("leftover")

    install_mod.install_shared_scorer(src, tgt, dry_run=False)
    assert not (dest / "STALE.txt").exists()
    assert (dest / "src" / "cli.py").exists()


def test_remove_shared_scorer_deletes_tree(install_mod, tmp_path):
    src = _make_fake_source(tmp_path)
    tgt = _fake_target(tmp_path)
    install_mod.install_shared_scorer(src, tgt, dry_run=False)
    dest = tgt["skills_dir"].parent / "shared" / "scorer"
    assert dest.exists()

    removed = install_mod.remove_shared_scorer(tgt, dry_run=False)
    assert removed == 1
    assert not dest.exists()


def test_remove_shared_scorer_noop_when_absent(install_mod, tmp_path):
    tgt = _fake_target(tmp_path)
    assert install_mod.remove_shared_scorer(tgt, dry_run=False) == 0


def test_remove_shared_scorer_dry_run_keeps_tree(install_mod, tmp_path):
    src = _make_fake_source(tmp_path)
    tgt = _fake_target(tmp_path)
    install_mod.install_shared_scorer(src, tgt, dry_run=False)
    dest = tgt["skills_dir"].parent / "shared" / "scorer"

    install_mod.remove_shared_scorer(tgt, dry_run=True)
    assert dest.exists(), "dry-run must not delete"
