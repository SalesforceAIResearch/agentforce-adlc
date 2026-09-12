"""Tests for the portable coding-agent installer target."""

import json
from pathlib import Path

from tools import install


def _seed_legacy_installation(home: Path, target_name: str):
    """Create artifacts written by an older file-copy installer."""
    target = install.get_target_dirs(target_name)[0]
    target["base_dir"].mkdir(parents=True, exist_ok=True)
    target["install_dir"].mkdir()
    target["meta_file"].write_text(json.dumps({"version": "0.1.0"}))
    target["installer_dest"].write_text("# old installer\n")

    for skill_name in (*install.MANAGED_SKILL_NAMES, install.OLD_SKILL_DIRS[0]):
        skill_dir = target["skills_dir"] / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text("# managed\n")

    unrelated_skill = target["skills_dir"] / "agentforce-architecture-analyze"
    unrelated_skill.mkdir(parents=True)
    (unrelated_skill / "SKILL.md").write_text("# keep\n")

    if target["supports_agents"]:
        target["agents_dir"].mkdir(parents=True)
        (target["agents_dir"] / "adlc-author.md").write_text("# managed\n")
        (target["agents_dir"] / "keep-me.md").write_text("# keep\n")

    if target["supports_hooks"]:
        target["hooks_scripts_dir"].mkdir(parents=True)
        (target["hooks_scripts_dir"] / "adlc-guardrails.py").write_text("# managed\n")
        (target["hooks_scripts_dir"] / "stdin_utils.py").write_text("# managed\n")
        (target["hooks_scripts_dir"] / "keep-me.py").write_text("# keep\n")
        (target["hooks_dir"] / "skills-registry.json").write_text("{}\n")
        target["settings_file"].write_text(json.dumps({
            "theme": "dark",
            "hooks": {
                "PreToolUse": [
                    {"hooks": [{"command": "python adlc-guardrails.py"}]},
                    {"hooks": [{"command": "python keep-me.py"}]},
                ],
                "PostToolUse": [
                    {"hooks": [{"command": "python adlc-agent-validator.py"}]},
                ],
            },
        }))

    return target


def _assert_legacy_installation_removed(target):
    assert not target["install_dir"].exists()
    assert not target["meta_file"].exists()
    assert not target["installer_dest"].exists()
    for skill_name in (*install.MANAGED_SKILL_NAMES, install.OLD_SKILL_DIRS[0]):
        assert not (target["skills_dir"] / skill_name).exists()
    assert (target["skills_dir"] / "agentforce-architecture-analyze" / "SKILL.md").is_file()

    if target["supports_agents"]:
        assert not (target["agents_dir"] / "adlc-author.md").exists()
        assert (target["agents_dir"] / "keep-me.md").is_file()

    if target["supports_hooks"]:
        assert not (target["hooks_scripts_dir"] / "adlc-guardrails.py").exists()
        assert not (target["hooks_scripts_dir"] / "stdin_utils.py").exists()
        assert (target["hooks_scripts_dir"] / "keep-me.py").is_file()
        assert not (target["hooks_dir"] / "skills-registry.json").exists()
        settings = json.loads(target["settings_file"].read_text())
        assert settings["theme"] == "dark"
        assert settings["hooks"] == {
            "PreToolUse": [{"hooks": [{"command": "python keep-me.py"}]}],
        }


def test_codex_target_uses_shared_agent_skills_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    targets = install.get_target_dirs("codex")

    assert len(targets) == 1
    target = targets[0]
    assert target["name"] == "codex"
    assert target["base_dir"] == tmp_path / ".agents"
    assert target["skills_dir"] == tmp_path / ".agents" / "skills"
    assert target["supports_agents"] is False
    assert target["supports_hooks"] is False
    assert target["requires_existing_base"] is False


def test_installer_reads_version_from_plugin_manifest(tmp_path):
    repo_root = Path(install.__file__).resolve().parent.parent
    plugin_version = json.loads(
        (repo_root / ".claude-plugin" / "plugin.json").read_text()
    )["version"]
    marketplace_version = json.loads(
        (repo_root / ".claude-plugin" / "marketplace.json").read_text()
    )["plugins"][0]["version"]

    assert install.read_plugin_version(repo_root) == plugin_version
    assert marketplace_version == plugin_version

    (tmp_path / "VERSION").write_text("99.0.0\n")
    assert install.read_plugin_version(tmp_path) is None


def test_default_target_is_codex_even_when_legacy_clients_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()

    assert install.auto_detect_target() == "codex"


def test_all_target_includes_every_layout_and_both_keeps_legacy_behavior(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert [target["name"] for target in install.get_target_dirs("all")] == [
        "codex", "claude", "cursor",
    ]
    assert [target["name"] for target in install.get_target_dirs("both")] == [
        "claude", "cursor",
    ]
    assert install.parse_target("all") == "all"
    assert install.parse_target("both") == "both"


def test_all_install_completes_missing_client_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()
    assert install.cmd_install(force=True, target="codex") == 0

    assert install.cmd_install(target="all") == 0

    assert (tmp_path / ".agents" / ".adlc.json").is_file()
    assert (tmp_path / ".claude" / ".adlc.json").is_file()
    assert (tmp_path / ".cursor" / ".adlc.json").is_file()


def test_all_update_completes_missing_client_targets(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()
    assert install.cmd_install(force=True, target="codex") == 0

    assert install.cmd_update(target="all") == 0

    assert (tmp_path / ".agents" / ".adlc.json").is_file()
    assert (tmp_path / ".claude" / ".adlc.json").is_file()


def test_codex_dry_run_does_not_create_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    assert install.cmd_install(dry_run=True, force=True, target="codex") == 0
    assert not (tmp_path / ".agents").exists()


def test_codex_install_and_uninstall(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    agents_home = tmp_path / ".agents"

    assert install.cmd_install(force=True, target="codex") == 0

    for skill_name in install.MANAGED_SKILL_NAMES:
        assert (agents_home / "skills" / skill_name / "SKILL.md").is_file()
    assert (agents_home / "agentforce-adlc" / "tools" / "install.py").is_file()
    assert (agents_home / "adlc-install.py").is_file()
    assert not (agents_home / "agents").exists()
    assert not (agents_home / "hooks").exists()

    metadata = json.loads((agents_home / ".adlc.json").read_text())
    assert metadata["target"] == "codex"
    assert set(metadata["skills"]) == install.MANAGED_SKILL_NAMES
    assert metadata["agents"] == []
    assert metadata["hooks"] == []

    assert install.cmd_uninstall(force=True, target="codex") == 0

    for skill_name in install.MANAGED_SKILL_NAMES:
        assert not (agents_home / "skills" / skill_name).exists()
    assert not (agents_home / "agentforce-adlc").exists()
    assert not (agents_home / ".adlc.json").exists()

    # The updater itself is part of the managed installation.
    assert not (agents_home / "adlc-install.py").exists()


def test_codex_uninstall_cleans_all_previous_installations(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    claude_target = _seed_legacy_installation(tmp_path, "claude")
    cursor_target = _seed_legacy_installation(tmp_path, "cursor")

    assert install.cmd_uninstall(force=True, target="codex") == 0

    _assert_legacy_installation_removed(claude_target)
    _assert_legacy_installation_removed(cursor_target)


def test_explicit_legacy_target_remains_supported(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude").mkdir()

    assert install.cmd_install(force=True, target="claude") == 0
    assert (tmp_path / ".claude" / "skills" / "agentforce-generate" / "SKILL.md").is_file()
    assert (tmp_path / ".claude" / "agents" / "adlc-author.md").is_file()
    assert (tmp_path / ".claude" / "hooks" / "scripts" / "adlc-guardrails.py").is_file()

    assert install.cmd_uninstall(force=True, target="claude") == 0
    assert not (tmp_path / ".claude" / ".adlc.json").exists()
