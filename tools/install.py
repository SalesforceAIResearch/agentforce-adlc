#!/usr/bin/env python3
"""
agentforce-adlc Installer

Usage:
    curl -sSL https://raw.githubusercontent.com/SalesforceAIResearch/agentforce-adlc/main/tools/install.py | python3

    # Or with options:
    python3 install.py                # Install
    python3 install.py --update       # Check for updates and apply if available
    python3 install.py --force-update # Force reinstall even if up-to-date
    python3 install.py --uninstall    # Remove agentforce-adlc
    python3 install.py --status       # Show installation status
    python3 install.py --dry-run      # Preview changes without writing
    python3 install.py --force        # Skip confirmations
    python3 install.py --target cursor  # Install for Cursor instead of Claude Code

Requirements:
    - Python 3.9+ (standard library only)
    - Claude Code (~/.claude/) or Cursor (~/.cursor/) installed
"""

import platform
import sys

if sys.version_info < (3, 9):
    v = f"{sys.version_info.major}.{sys.version_info.minor}"
    print(f"\n  \033[0;31m✗\033[0m Python {v} found, but 3.9+ required\n")
    os_name = platform.system()
    print("  \033[1mHow to install Python 3.9+:\033[0m\n")
    if os_name == "Darwin":
        print("    # macOS — using Homebrew (recommended):")
        print("    brew install python@3.13\n")
        print("    # Or download from python.org:")
        print("    open https://www.python.org/downloads/macos/")
    elif os_name == "Linux":
        print("    # Ubuntu / Debian:")
        print("    sudo apt-get update && sudo apt-get install -y python3.13 python3.13-venv\n")
        print("    # Fedora / RHEL:")
        print("    sudo dnf install -y python3.13")
    elif os_name == "Windows":
        print("    # Windows — download the installer:")
        print("    https://www.python.org/downloads/windows/\n")
        print("    # Or using winget:")
        print("    winget install Python.Python.3.13")
    else:
        print("    https://www.python.org/downloads/")
    print("\n  After installing, restart your terminal and run this installer again.\n")
    sys.exit(1)

import argparse
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# CONFIGURATION
# ============================================================================

INSTALLER_VERSION = "0.1.0"

# GitHub repository
GITHUB_OWNER = "SalesforceAIResearch"
GITHUB_REPO = "agentforce-adlc"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main"

# Legacy module-level constants (for backward compat with self-updater)
CLAUDE_DIR = Path.home() / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
AGENTS_DIR = CLAUDE_DIR / "agents"
HOOKS_DIR = CLAUDE_DIR / "hooks"
HOOKS_SCRIPTS_DIR = HOOKS_DIR / "scripts"
INSTALL_DIR = CLAUDE_DIR / "adlc"
META_FILE = CLAUDE_DIR / ".adlc.json"
INSTALLER_DEST = CLAUDE_DIR / "adlc-install.py"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"

# Suffixes/prefixes for detecting ADLC-managed skills during orphan cleanup
SKILL_SUFFIX = "-agentforce"
OLD_SKILL_PREFIXES = ("adlc-", "agentforce-")

# Skills to install (relative to repo root)
SKILL_DIRS = [
    "skills/developing-agentforce",
    "skills/testing-agentforce",
    "skills/observing-agentforce",
]

# Old skill dirs to clean up during install
OLD_SKILL_DIRS = [
    # v0.1.x names
    "adlc-author",
    "adlc-discover",
    "adlc-scaffold",
    "adlc-deploy",
    "adlc-run",
    "adlc-test",
    "adlc-optimize",
    "adlc-feedback",
    "adlc-safety",
    # v0.2.0–v0.4.x names
    "agentforce-development",
    "agentforce-testing",
    "agentforce-observability",
]

# Agent definitions to install
AGENT_FILES = [
    "agents/adlc-orchestrator.md",
    "agents/adlc-author.md",
    "agents/adlc-engineer.md",
    "agents/adlc-qa.md",
]

# Hook scripts to install
HOOK_SCRIPTS = [
    "shared/hooks/scripts/guardrails.py",
    "shared/hooks/scripts/agent-validator.py",
    "shared/hooks/scripts/session-init.py",
    "shared/hooks/scripts/stdin_utils.py",
]

HOOK_REGISTRY = "shared/hooks/skills-registry.json"

# Supported installation targets
TARGETS = ["claude", "cursor", "both"]

# Agent definition prefix
AGENT_PREFIX = "adlc-"


def _is_adlc_skill(name: str) -> bool:
    """Check if a directory name is an ADLC-managed skill."""
    if name in OLD_SKILL_DIRS:
        return True
    # Current naming: {verb}-agentforce (e.g., developing-agentforce)
    # Exclude unrelated skills like sf-ai-agentforce
    return name.endswith(SKILL_SUFFIX) and name.count("-") == 1


def _is_adlc_agent(name: str) -> bool:
    """Check if a file is an ADLC-managed agent definition."""
    return name.startswith(AGENT_PREFIX) and name.endswith(".md")


def get_target_dirs(target: str) -> list:
    """Return list of target config dicts per target."""
    configs = []
    if target in ("claude", "both"):
        base = Path.home() / ".claude"
        configs.append({
            "name": "claude",
            "base_dir": base,
            "skills_dir": base / "skills",
            "agents_dir": base / "agents",
            "hooks_dir": base / "hooks",
            "hooks_scripts_dir": base / "hooks" / "scripts",
            "install_dir": base / "adlc",
            "meta_file": base / ".adlc.json",
            "installer_dest": base / "adlc-install.py",
            "settings_file": base / "settings.json",
            "supports_agents": True,
            "supports_hooks": True,
        })
    if target in ("cursor", "both"):
        base = Path.home() / ".cursor"
        configs.append({
            "name": "cursor",
            "base_dir": base,
            "skills_dir": base / "skills",
            "agents_dir": None,
            "hooks_dir": None,
            "hooks_scripts_dir": None,
            "install_dir": base / "adlc",
            "meta_file": base / ".adlc.json",
            "installer_dest": base / "adlc-install.py",
            "settings_file": None,
            "supports_agents": False,
            "supports_hooks": False,
        })
    return configs


def auto_detect_target() -> str:
    """Auto-detect target based on which IDE directories exist."""
    claude_exists = (Path.home() / ".claude").exists()
    cursor_exists = (Path.home() / ".cursor").exists()
    if claude_exists and cursor_exists:
        return "both"
    if cursor_exists:
        return "cursor"
    if claude_exists:
        return "claude"
    # Neither exists — default to claude (will error later on prereq check)
    return "claude"


# ============================================================================
# OUTPUT HELPERS
# ============================================================================

class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{Colors.RESET}"


def print_step(msg: str):
    print(f"\n{c('▸', Colors.BLUE)} {c(msg, Colors.BOLD)}")


def print_substep(msg: str):
    print(f"  {c('✓', Colors.GREEN)} {msg}")


def print_info(msg: str):
    print(f"  {c('ℹ', Colors.BLUE)} {msg}")


def print_warn(msg: str):
    print(f"  {c('⚠', Colors.YELLOW)} {msg}")


def print_error(msg: str):
    print(f"  {c('✗', Colors.RED)} {msg}")


# ============================================================================
# FILESYSTEM HELPERS
# ============================================================================

def safe_rmtree(path: Path):
    """Remove a directory tree, handling symlinks safely."""
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _find_python3() -> str:
    """Find the python3 executable path reliably.

    sys.executable can be empty or wrong when piped via curl | python3.
    Falls back to searching PATH. On Windows, searches for 'python' as well
    since 'python3' is not always available.
    """
    exe = sys.executable
    if exe and os.path.isfile(exe):
        return exe

    # On Windows, python3 may not exist — try python first
    names = ["python3", "python"] if os.name != "nt" else ["python", "python3"]
    for name in names:
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = os.path.join(directory, name)
            if os.name == "nt":
                candidate += ".exe"
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

    return "python3" if os.name != "nt" else "python"


# ============================================================================
# SSL HELPERS
# ============================================================================

_SSL_CONTEXT_CACHE: Optional[ssl.SSLContext] = None
_SSL_ERROR_SHOWN = False


def _build_ssl_context() -> ssl.SSLContext:
    """Build best available SSL context for urllib."""
    cert_file = os.environ.get("SSL_CERT_FILE")
    if cert_file and os.path.isfile(cert_file):
        return ssl.create_default_context(cafile=cert_file)

    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass

    return ssl.create_default_context()


def _get_ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT_CACHE
    if _SSL_CONTEXT_CACHE is None:
        _SSL_CONTEXT_CACHE = _build_ssl_context()
    return _SSL_CONTEXT_CACHE


def _handle_ssl_error(e: Exception) -> bool:
    global _SSL_ERROR_SHOWN
    is_ssl = False
    if isinstance(e, urllib.error.URLError) and hasattr(e, "reason"):
        if isinstance(e.reason, (ssl.SSLCertVerificationError, ssl.SSLError)):
            is_ssl = True
    elif isinstance(e, (ssl.SSLCertVerificationError, ssl.SSLError)):
        is_ssl = True

    if is_ssl and not _SSL_ERROR_SHOWN:
        _SSL_ERROR_SHOWN = True
        print()
        print_error("SSL certificate verification failed")
        print_info("This is common with python.org installs on macOS.")
        print()
        print(c("  Fix options (try in order):", Colors.BOLD))
        print()
        print("  1. Run the macOS certificate installer:")
        print("     /Applications/Python\\ 3.*/Install\\ Certificates.command")
        print()
        print("  2. Install certifi and set SSL_CERT_FILE:")
        print("     pip3 install certifi")
        print('     export SSL_CERT_FILE="$(python3 -c \'import certifi; print(certifi.where())\')"')
        print()

    return is_ssl


# ============================================================================
# METADATA
# ============================================================================

def write_metadata(tgt: Dict, version: str, skills: List[str], agents: List[str],
                   hooks: List[str], commit_sha: Optional[str] = None):
    """Write install metadata to the target's meta file."""
    meta_file = tgt["meta_file"]
    meta_file.write_text(json.dumps({
        "method": "unified",
        "version": version,
        "commit_sha": commit_sha,
        "installed_at": datetime.now().isoformat(),
        "installer_version": INSTALLER_VERSION,
        "install_dir": str(tgt["install_dir"]),
        "target": tgt["name"],
        "skills": skills,
        "agents": agents,
        "hooks": hooks,
    }, indent=2) + "\n")


def read_metadata(tgt: Dict) -> Optional[Dict[str, Any]]:
    """Read install metadata for a target."""
    meta_file = tgt["meta_file"]
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text())
        except (json.JSONDecodeError, IOError):
            return None
    return None


# ============================================================================
# DOWNLOAD & VERSION
# ============================================================================

def download_repo_zip(target_dir: Path, ref: str = "main") -> bool:
    """Download repo zip from GitHub and extract to target_dir."""
    zip_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/archive/refs/heads/{ref}.zip"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            print_info(f"Downloading from {zip_url}...")
            with urllib.request.urlopen(zip_url, timeout=60, context=_get_ssl_context()) as resp:
                tmp_file.write(resp.read())

        with zipfile.ZipFile(tmp_path, "r") as zf:
            top_dirs = {name.split("/")[0] for name in zf.namelist() if "/" in name}
            if len(top_dirs) != 1:
                print_error("Unexpected zip structure")
                return False
            top_dir = top_dirs.pop()

            with tempfile.TemporaryDirectory() as extract_tmp:
                zf.extractall(extract_tmp)
                extracted = Path(extract_tmp) / top_dir

                safe_rmtree(target_dir)
                shutil.copytree(extracted, target_dir)

        return True

    except (urllib.error.URLError, zipfile.BadZipFile, IOError) as e:
        if not _handle_ssl_error(e):
            print_error(f"Download failed: {e}")
        return False
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


def fetch_remote_version(ref: str = "main") -> Optional[str]:
    """Fetch the VERSION file from the remote repo."""
    url = f"{GITHUB_RAW_URL}/VERSION"
    try:
        with urllib.request.urlopen(url, timeout=15, context=_get_ssl_context()) as resp:
            return resp.read().decode().strip()
    except (urllib.error.URLError, IOError) as e:
        if not _handle_ssl_error(e):
            print_error(f"Failed to check remote version: {e}")
        return None


def fetch_remote_commit_sha(ref: str = "main") -> Optional[str]:
    """Fetch the latest commit SHA from the GitHub API."""
    url = f"{GITHUB_API_URL}/commits/{ref}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
        with urllib.request.urlopen(req, timeout=15, context=_get_ssl_context()) as resp:
            data = json.loads(resp.read().decode())
            return data.get("sha", "")[:12]
    except (urllib.error.URLError, IOError, json.JSONDecodeError, KeyError):
        return None


def get_local_commit_sha(repo_root: Path) -> Optional[str]:
    """Get the current commit SHA from a local git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            capture_output=True, text=True, cwd=str(repo_root),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


# ============================================================================
# SKILL INSTALLATION
# ============================================================================

def install_skills(source_dir: Path, tgt: Dict, dry_run: bool = False) -> List[str]:
    """Copy skills from source to target skills dir."""
    installed = []
    skills_dir = tgt["skills_dir"]
    skills_dir.mkdir(parents=True, exist_ok=True)

    for skill_rel in SKILL_DIRS:
        src = source_dir / skill_rel
        skill_name = Path(skill_rel).name

        if not src.exists():
            print_warn(f"Skill not found: {skill_rel}")
            continue

        target = skills_dir / skill_name
        if dry_run:
            print_info(f"Would install skill: {skill_name}")
        else:
            safe_rmtree(target)
            shutil.copytree(src, target)
            print_substep(f"Skill: {skill_name}")

        installed.append(skill_name)

    return installed


def install_agents(source_dir: Path, tgt: Dict, dry_run: bool = False) -> List[str]:
    """Copy agent definitions to target agents dir."""
    if not tgt["supports_agents"]:
        return []

    installed = []
    agents_dir = tgt["agents_dir"]
    agents_dir.mkdir(parents=True, exist_ok=True)

    for agent_rel in AGENT_FILES:
        src = source_dir / agent_rel
        if not src.exists():
            print_warn(f"Agent not found: {agent_rel}")
            continue

        target = agents_dir / src.name
        if dry_run:
            print_info(f"Would install agent: {src.name}")
        else:
            shutil.copy2(src, target)
            print_substep(f"Agent: {src.name}")

        installed.append(src.name)

    return installed


def install_hooks(source_dir: Path, tgt: Dict, dry_run: bool = False) -> List[str]:
    """Copy hook scripts to target hooks dir."""
    if not tgt["supports_hooks"]:
        return []

    installed = []
    hooks_scripts_dir = tgt["hooks_scripts_dir"]
    hooks_scripts_dir.mkdir(parents=True, exist_ok=True)

    for hook_rel in HOOK_SCRIPTS:
        src = source_dir / hook_rel
        if not src.exists():
            print_warn(f"Hook not found: {hook_rel}")
            continue

        # Prefix hook scripts with adlc- to avoid conflicts (except stdin_utils)
        dest_name = src.name
        if not dest_name.startswith("adlc-") and not dest_name.startswith("stdin_"):
            dest_name = f"adlc-{dest_name}"

        target = hooks_scripts_dir / dest_name
        if dry_run:
            print_info(f"Would install hook: {dest_name}")
        else:
            shutil.copy2(src, target)
            print_substep(f"Hook: {dest_name}")

        installed.append(dest_name)

    # Copy skills registry
    hooks_dir = tgt["hooks_dir"]
    registry_src = source_dir / HOOK_REGISTRY
    if registry_src.exists():
        registry_dest = hooks_dir / "skills-registry.json"
        if dry_run:
            print_info("Would install skills-registry.json")
        else:
            shutil.copy2(registry_src, registry_dest)
            print_substep("Hook: skills-registry.json")
        installed.append("skills-registry.json")

    return installed


def prune_orphan_skills(tgt: Dict, current_skills: List[str], dry_run: bool = False) -> int:
    """Remove old adlc-* and orphan agentforce-* skills that are no longer in the repo."""
    pruned = 0
    skills_dir = tgt["skills_dir"]
    if not skills_dir.exists():
        return pruned

    current_set = set(current_skills)
    for item in sorted(skills_dir.iterdir()):
        if not item.is_dir():
            continue
        # Remove explicitly listed old skill dirs
        if item.name in OLD_SKILL_DIRS:
            if dry_run:
                print_info(f"Would remove old skill: {item.name}")
            else:
                safe_rmtree(item)
                print_substep(f"Removed old skill: {item.name}")
            pruned += 1
        # Remove orphan *-agentforce skills not in current list
        elif item.name.endswith(SKILL_SUFFIX) and item.name not in current_set:
            if dry_run:
                print_info(f"Would remove orphan skill: {item.name}")
            else:
                safe_rmtree(item)
                print_substep(f"Removed orphan skill: {item.name}")
            pruned += 1

    return pruned


# ============================================================================
# HOOK CONFIGURATION IN settings.json
# ============================================================================

def _find_adlc_hook_index(hooks_list: list, marker: str) -> int:
    """Find the index of an existing ADLC hook entry by checking command strings."""
    for i, entry in enumerate(hooks_list):
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if marker in cmd:
                return i
    return -1


def configure_hooks(tgt: Dict, dry_run: bool = False) -> bool:
    """Merge ADLC hook config into settings.json."""
    if not tgt["supports_hooks"]:
        return True

    hooks_scripts_dir = tgt["hooks_scripts_dir"]
    settings_file = tgt["settings_file"]

    py_cmd = "python" if os.name == "nt" else "python3"
    guardrail_cmd = f"{py_cmd} {hooks_scripts_dir / 'adlc-guardrails.py'}"
    validator_cmd = f"{py_cmd} {hooks_scripts_dir / 'adlc-agent-validator.py'}"

    adlc_pre_hook = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": guardrail_cmd, "timeout": 5000}],
    }
    adlc_post_hook = {
        "matcher": "Write|Edit",
        "hooks": [{"type": "command", "command": validator_cmd, "timeout": 10000}],
    }

    if dry_run:
        print_info("Would configure hooks in settings.json")
        return True

    # Read existing settings
    settings: Dict[str, Any] = {}
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text())
        except (json.JSONDecodeError, IOError):
            settings = {}

    hooks = settings.setdefault("hooks", {})

    # Configure PreToolUse
    pre_hooks = hooks.setdefault("PreToolUse", [])
    idx = _find_adlc_hook_index(pre_hooks, "adlc-guardrails")
    if idx >= 0:
        pre_hooks[idx] = adlc_pre_hook
    else:
        pre_hooks.append(adlc_pre_hook)

    # Configure PostToolUse
    post_hooks = hooks.setdefault("PostToolUse", [])
    idx = _find_adlc_hook_index(post_hooks, "adlc-agent-validator")
    if idx >= 0:
        post_hooks[idx] = adlc_post_hook
    else:
        post_hooks.append(adlc_post_hook)

    settings_file.write_text(json.dumps(settings, indent=2) + "\n")
    return True


def remove_hooks_from_settings(tgt: Dict, dry_run: bool = False) -> bool:
    """Remove ADLC hooks from settings.json."""
    if not tgt["supports_hooks"]:
        return True

    settings_file = tgt["settings_file"]
    if not settings_file.exists():
        return True

    if dry_run:
        print_info("Would remove ADLC hooks from settings.json")
        return True

    try:
        settings = json.loads(settings_file.read_text())
    except (json.JSONDecodeError, IOError):
        return True

    hooks = settings.get("hooks", {})
    changed = False

    for key in ("PreToolUse", "PostToolUse"):
        hook_list = hooks.get(key, [])
        filtered = [
            entry for entry in hook_list
            if not any("adlc-" in h.get("command", "") for h in entry.get("hooks", []))
        ]
        if len(filtered) != len(hook_list):
            hooks[key] = filtered
            changed = True

    # Clean up empty lists/dicts
    for key in list(hooks.keys()):
        if not hooks[key]:
            del hooks[key]
    if not hooks and "hooks" in settings:
        del settings["hooks"]

    if changed:
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    return True


# ============================================================================
# VALIDATION
# ============================================================================

def validate_installation(tgt: Dict) -> List[str]:
    """Validate that installation completed correctly. Returns list of issues."""
    issues = []
    install_dir = tgt["install_dir"]
    skills_dir = tgt["skills_dir"]
    meta_file = tgt["meta_file"]

    # Check install dir
    if not install_dir.exists():
        issues.append(f"Install directory missing: {install_dir}")
        return issues

    # Check skills
    if skills_dir.exists():
        for skill_rel in SKILL_DIRS:
            skill_name = Path(skill_rel).name
            skill_md = skills_dir / skill_name / "SKILL.md"
            if not skill_md.exists():
                issues.append(f"SKILL.md missing: {skill_name}")
    else:
        issues.append(f"Skills directory missing: {skills_dir}")

    # Check agents (Claude Code only)
    if tgt["supports_agents"]:
        agents_dir = tgt["agents_dir"]
        for agent_rel in AGENT_FILES:
            agent_name = Path(agent_rel).name
            if not (agents_dir / agent_name).exists():
                issues.append(f"Agent missing: {agent_name}")

    # Check hooks (Claude Code only)
    if tgt["supports_hooks"]:
        hooks_scripts_dir = tgt["hooks_scripts_dir"]
        for hook_rel in HOOK_SCRIPTS:
            hook_name = Path(hook_rel).name
            dest_name = hook_name
            if not dest_name.startswith("adlc-") and not dest_name.startswith("stdin_"):
                dest_name = f"adlc-{dest_name}"
            if not (hooks_scripts_dir / dest_name).exists():
                issues.append(f"Hook missing: {dest_name}")

        # Check hooks in settings.json
        settings_file = tgt["settings_file"]
        if settings_file.exists():
            try:
                settings = json.loads(settings_file.read_text())
                hooks = settings.get("hooks", {})
                pre = hooks.get("PreToolUse", [])
                post = hooks.get("PostToolUse", [])
                has_guardrail = any(
                    "adlc-guardrails" in h.get("command", "")
                    for entry in pre for h in entry.get("hooks", [])
                )
                has_validator = any(
                    "adlc-agent-validator" in h.get("command", "")
                    for entry in post for h in entry.get("hooks", [])
                )
                if not has_guardrail:
                    issues.append("Guardrail hook not configured in settings.json")
                if not has_validator:
                    issues.append("Validator hook not configured in settings.json")
            except (json.JSONDecodeError, IOError):
                issues.append("Could not read settings.json for hook validation")

    # Check metadata
    if not meta_file.exists():
        issues.append(f"Metadata file missing: {meta_file}")

    return issues


# ============================================================================
# REMOVE HELPERS
# ============================================================================

def remove_skills(tgt: Dict, dry_run: bool = False) -> int:
    """Remove all installed adlc-* skills."""
    removed = 0
    skills_dir = tgt["skills_dir"]
    if not skills_dir.exists():
        return removed

    for item in sorted(skills_dir.iterdir()):
        if item.is_dir() and _is_adlc_skill(item.name):
            if dry_run:
                print_info(f"Would remove skill: {item.name}")
            else:
                safe_rmtree(item)
                print_substep(f"Removed skill: {item.name}")
            removed += 1

    return removed


def remove_agents(tgt: Dict, dry_run: bool = False) -> int:
    """Remove all installed adlc-* agents."""
    if not tgt["supports_agents"]:
        return 0

    removed = 0
    agents_dir = tgt["agents_dir"]
    if not agents_dir.exists():
        return removed

    for item in sorted(agents_dir.iterdir()):
        if item.is_file() and _is_adlc_agent(item.name):
            if dry_run:
                print_info(f"Would remove agent: {item.name}")
            else:
                item.unlink()
                print_substep(f"Removed agent: {item.name}")
            removed += 1

    return removed


def remove_hooks(tgt: Dict, dry_run: bool = False) -> int:
    """Remove ADLC hook scripts."""
    if not tgt["supports_hooks"]:
        return 0

    removed = 0
    hooks_scripts_dir = tgt["hooks_scripts_dir"]
    hooks_dir = tgt["hooks_dir"]

    # Remove scripts
    if hooks_scripts_dir.exists():
        for item in sorted(hooks_scripts_dir.iterdir()):
            if item.is_file() and item.name.startswith("adlc-"):
                if dry_run:
                    print_info(f"Would remove hook: {item.name}")
                else:
                    item.unlink()
                    print_substep(f"Removed hook: {item.name}")
                removed += 1

        # Remove stdin_utils.py (shared helper)
        stdin_utils = hooks_scripts_dir / "stdin_utils.py"
        if stdin_utils.exists():
            if dry_run:
                print_info("Would remove hook: stdin_utils.py")
            else:
                stdin_utils.unlink()
                print_substep("Removed hook: stdin_utils.py")
            removed += 1

    # Remove registry
    registry = hooks_dir / "skills-registry.json"
    if registry.exists():
        if dry_run:
            print_info("Would remove skills-registry.json")
        else:
            registry.unlink()
            print_substep("Removed: skills-registry.json")
        removed += 1

    return removed


# ============================================================================
# COMMANDS
# ============================================================================

def _install_for_target(tgt: Dict, source_dir: Path, version: str,
                        commit_sha: Optional[str], dry_run: bool) -> Dict:
    """Install for a single target. Returns summary dict."""
    tgt_name = tgt["name"]
    install_dir = tgt["install_dir"]

    print_step(f"Installing for {tgt_name}")

    # Copy repo to install dir
    if dry_run:
        print_info(f"Would copy repo to {install_dir}")
    else:
        safe_rmtree(install_dir)
        shutil.copytree(source_dir, install_dir, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc", ".venv", "force-app",
        ))
        print_substep(f"Copied to {install_dir}")

    # Install skills (always)
    skills = install_skills(install_dir if not dry_run else source_dir, tgt, dry_run)
    if skills:
        print_substep(f"{len(skills)} skill(s) installed")
    else:
        print_warn("No skills found to install")

    pruned = prune_orphan_skills(tgt, skills, dry_run)
    if pruned:
        print_substep(f"{pruned} old skill(s) cleaned up (consolidated into {len(skills)} skills)")

    # Agents (Claude Code only)
    agents = []
    if tgt["supports_agents"]:
        agents = install_agents(install_dir if not dry_run else source_dir, tgt, dry_run)
        if agents:
            print_substep(f"{len(agents)} agent(s) installed")

    # Hooks (Claude Code only)
    hooks = []
    if tgt["supports_hooks"]:
        hooks = install_hooks(install_dir if not dry_run else source_dir, tgt, dry_run)
        if hooks:
            print_substep(f"{len(hooks)} hook(s) installed")

        if configure_hooks(tgt, dry_run):
            if not dry_run:
                print_substep("Hooks configured in settings.json")
        else:
            print_warn("Could not configure hooks in settings.json")

    # Copy installer for self-update
    installer_src = (install_dir if not dry_run else source_dir) / "tools" / "install.py"
    installer_dest = tgt["installer_dest"]
    if installer_src.exists():
        if dry_run:
            print_info(f"Would copy installer to {installer_dest}")
        else:
            shutil.copy2(installer_src, installer_dest)
            print_substep(f"Installer copied to {installer_dest}")
    else:
        print_warn("Installer source not found; self-update won't work")

    # Write metadata
    write_metadata(tgt, version, skills, agents, hooks, commit_sha=commit_sha)
    if not dry_run:
        print_substep(f"Metadata written to {tgt['meta_file']}")
    else:
        print_info(f"Would write metadata to {tgt['meta_file']}")

    # Validate
    if not dry_run:
        issues = validate_installation(tgt)
        if issues:
            for issue in issues:
                print_warn(issue)
        else:
            print_substep("All checks passed")

    return {"skills": skills, "agents": agents, "hooks": hooks}


def cmd_install(dry_run: bool = False, force: bool = False,
                called_from_bash: bool = False, target: str = "claude",
                _is_update: bool = False) -> int:
    """Install agentforce-adlc."""
    _download_tmp = None  # Set if remote install uses a temp dir
    if not called_from_bash:
        print(f"\n{c('agentforce-adlc installer', Colors.BOLD)}")
        if not _is_update:
            print()
            print(f"  {c('Prerequisites:', Colors.BOLD)} Python 3.9+, Claude Code or Cursor")
            print(f"  {c('Optional:', Colors.BOLD)}      Salesforce CLI (sf)")
            print()

    targets = get_target_dirs(target)

    # Check prerequisites — at least one target dir must exist
    valid_targets = [t for t in targets if t["base_dir"].exists()]
    if not valid_targets:
        names = [t["name"] for t in targets]
        dirs = [str(t["base_dir"]) for t in targets]
        print_error(f"No supported IDE found for target '{target}'")
        for name, d in zip(names, dirs):
            print_info(f"  {name}: {d} not found")
        if "claude" in names:
            print_info("Install Claude Code: https://docs.anthropic.com/en/docs/claude-code")
        if "cursor" in names:
            print_info("Install Cursor: https://www.cursor.com/")
        return 1

    # Warn about missing targets when using "both"
    for t in targets:
        if not t["base_dir"].exists():
            print_warn(f"{t['name']} not found ({t['base_dir']}), skipping")

    # Check existing installation (check first valid target)
    meta = read_metadata(valid_targets[0])
    if meta and not force:
        version = meta.get("version", "unknown")
        print_info(f"agentforce-adlc v{version} is already installed.")
        print_info("Use --force to reinstall, or --update to check for updates.")
        return 0

    # Detect local clone vs remote install
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    local_version_file = repo_root / "VERSION"
    commit_sha = None

    if local_version_file.exists():
        # Installing from local clone
        print_step("Installing from local clone")
        version = local_version_file.read_text().strip()
        commit_sha = get_local_commit_sha(repo_root)
        source_dir = repo_root

        if dry_run:
            print_info(f"Version: {version}" + (f" ({commit_sha})" if commit_sha else ""))
            for t in valid_targets:
                _install_for_target(t, source_dir, version, commit_sha, dry_run=True)
            print(f"\n{c('Dry run complete — no changes made.', Colors.DIM)}")
            return 0

        print_info(f"Version: {version}" + (f" ({commit_sha})" if commit_sha else ""))

    else:
        # Remote install (curl | python3)
        print_step("Downloading agentforce-adlc")
        version_str = fetch_remote_version()
        if not version_str:
            print_error("Could not determine remote version")
            return 1
        version = version_str
        commit_sha = fetch_remote_commit_sha()

        if dry_run:
            print_info(f"Version: {version}" + (f" ({commit_sha})" if commit_sha else ""))
            for t in valid_targets:
                print_info(f"Would download repo to {t['install_dir']}")
                print_info(f"Would install skills to {t['skills_dir']}")
                if t["supports_agents"]:
                    print_info(f"Would install agents to {t['agents_dir']}")
                if t["supports_hooks"]:
                    print_info(f"Would install hooks to {t['hooks_scripts_dir']}")
                    print_info("Would configure hooks in settings.json")
                print_info(f"Would copy installer to {t['installer_dest']}")
                print_info(f"Would write metadata to {t['meta_file']}")
            print(f"\n{c('Dry run complete — no changes made.', Colors.DIM)}")
            return 0

        print_info(f"Version: {version}" + (f" ({commit_sha})" if commit_sha else ""))

        # Download to a temp directory, then copy to each target
        _download_tmp = tempfile.mkdtemp(prefix="adlc-download-")
        _download_dir = Path(_download_tmp) / "adlc"
        if not download_repo_zip(_download_dir):
            shutil.rmtree(_download_tmp, ignore_errors=True)
            return 1
        print_substep(f"Downloaded to temp dir")
        source_dir = _download_dir

    # Install for each valid target
    all_skills = []
    all_agents = []
    all_hooks = []
    for t in valid_targets:
        result = _install_for_target(t, source_dir, version, commit_sha, dry_run=False)
        all_skills = result["skills"]  # Same for all targets
        if result["agents"]:
            all_agents = result["agents"]
        if result["hooks"]:
            all_hooks = result["hooks"]

    # Clean up temp download directory (remote install only)
    if _download_tmp and Path(_download_tmp).exists():
        shutil.rmtree(_download_tmp, ignore_errors=True)

    # Summary
    target_names = [t["name"] for t in valid_targets]
    print(f"\n{c('Installation complete!', Colors.GREEN)}")
    print()
    print(f"  Version:  {version}" + (f" ({commit_sha})" if commit_sha else ""))
    print(f"  Targets:  {', '.join(target_names)}")
    print(f"  Skills:   {', '.join(all_skills) if all_skills else 'none'}")
    if all_agents:
        print(f"  Agents:   {', '.join(all_agents)}")
    if all_hooks:
        print(f"  Hooks:    {len(all_hooks)} script(s) + settings.json configured")
    print()
    first_dest = valid_targets[0]["installer_dest"]
    py = "python" if os.name == "nt" else "python3"
    print(f"  Update:   {py} {first_dest} --update")
    print(f"  Status:   {py} {first_dest} --status")
    print(f"  Remove:   {py} {first_dest} --uninstall")
    print()
    print_info("Restart your IDE for skills to take effect.")
    print()

    return 0


def cmd_update(dry_run: bool = False, force_update: bool = False,
               target: str = "claude") -> int:
    """Check for updates and apply if available."""
    print(f"\n{c('agentforce-adlc updater', Colors.BOLD)}")

    targets = get_target_dirs(target)
    valid_targets = [t for t in targets if t["base_dir"].exists()]

    if not valid_targets:
        print_info("agentforce-adlc is not installed. Running install...")
        return cmd_install(dry_run=dry_run, target=target)

    meta = read_metadata(valid_targets[0])
    if not meta:
        print_info("agentforce-adlc is not installed. Running install...")
        return cmd_install(dry_run=dry_run, target=target)

    local_version = meta.get("version", "unknown")
    local_sha = meta.get("commit_sha")
    print_info(f"Installed version: {local_version}" + (f" ({local_sha})" if local_sha else ""))

    # Fetch remote version + commit SHA
    print_step("Checking for updates")
    remote_version = fetch_remote_version()
    if not remote_version:
        print_error("Could not check remote version")
        return 1

    remote_sha = fetch_remote_commit_sha()
    print_info(f"Remote version: {remote_version}" + (f" ({remote_sha})" if remote_sha else ""))

    # Detect changes
    version_changed = remote_version != local_version
    content_changed = (
        remote_sha and local_sha
        and remote_sha != local_sha
        and not version_changed
    )

    if not version_changed and not content_changed and not force_update:
        print(f"\n{c('Already up to date.', Colors.GREEN)}")
        return 0

    if force_update:
        print_info("Force update requested")
    elif version_changed:
        print_info(f"Version update available: {local_version} -> {remote_version}")
    elif content_changed:
        print_info(f"Content update available: {local_sha} -> {remote_sha}")

    return cmd_install(dry_run=dry_run, force=True, target=target, _is_update=True)


def cmd_uninstall(dry_run: bool = False, force: bool = False,
                  target: str = "claude") -> int:
    """Remove agentforce-adlc installation."""
    print(f"\n{c('agentforce-adlc uninstaller', Colors.BOLD)}")

    targets = get_target_dirs(target)
    valid_targets = [t for t in targets if t["base_dir"].exists()]

    if not valid_targets:
        print_info("agentforce-adlc is not installed.")
        return 0

    # Check if anything is actually installed
    any_installed = False
    for t in valid_targets:
        if read_metadata(t) or t["install_dir"].exists():
            any_installed = True
            break
    if not any_installed:
        print_info("agentforce-adlc is not installed.")
        return 0

    if not force:
        print()
        print("  This will remove:")
        for t in valid_targets:
            print(f"    [{t['name']}]")
            print(f"    - {t['install_dir']}")
            print(f"    - {t['skills_dir']}/adlc-* skills")
            if t["supports_agents"]:
                print(f"    - {t['agents_dir']}/adlc-* agents")
            if t["supports_hooks"]:
                print(f"    - Hook scripts + settings.json entries")
            print(f"    - {t['meta_file']}")
            print(f"    - {t['installer_dest']}")
        print()
        try:
            answer = input("  Proceed? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
        if answer not in ("y", "yes"):
            print_info("Cancelled.")
            return 0

    for t in valid_targets:
        tgt_name = t["name"]
        install_dir = t["install_dir"]
        meta_file = t["meta_file"]
        installer_dest = t["installer_dest"]

        if not read_metadata(t) and not install_dir.exists():
            continue

        print_step(f"Uninstalling from {tgt_name}")

        # Remove install dir
        if install_dir.exists():
            if dry_run:
                print_info(f"Would remove {install_dir}")
            else:
                safe_rmtree(install_dir)
                print_substep(f"Removed {install_dir}")

        # Remove skills
        removed_skills = remove_skills(t, dry_run=dry_run)
        if removed_skills:
            print_substep(f"Removed {removed_skills} skill(s)")

        # Remove agents
        removed_agents = remove_agents(t, dry_run=dry_run)
        if removed_agents:
            print_substep(f"Removed {removed_agents} agent(s)")

        # Remove hooks
        removed_hooks = remove_hooks(t, dry_run=dry_run)
        if removed_hooks:
            print_substep(f"Removed {removed_hooks} hook(s)")

        # Remove hooks from settings.json
        remove_hooks_from_settings(t, dry_run=dry_run)
        if not dry_run and t["supports_hooks"]:
            print_substep("Removed ADLC hooks from settings.json")

        # Remove metadata
        if meta_file.exists():
            if dry_run:
                print_info(f"Would remove {meta_file}")
            else:
                meta_file.unlink()
                print_substep(f"Removed {meta_file}")

        # Remove self-updater (but not if we're running from it)
        if installer_dest.exists():
            running_from_dest = Path(__file__).resolve() == installer_dest.resolve()
            if dry_run:
                print_info(f"Would remove {installer_dest}")
            elif not running_from_dest:
                installer_dest.unlink()
                print_substep(f"Removed {installer_dest}")
            else:
                print_info(f"Skipping removal of running installer: {installer_dest}")
                print_info("You can delete it manually.")

    if dry_run:
        print(f"\n{c('Dry run complete — no changes made.', Colors.DIM)}")
    else:
        print(f"\n{c('Uninstall complete.', Colors.GREEN)}")

    return 0


def cmd_status(target: str = "claude") -> int:
    """Show installation status."""
    print(f"\n{c('agentforce-adlc status', Colors.BOLD)}")

    targets = get_target_dirs(target)
    valid_targets = [t for t in targets if t["base_dir"].exists()]

    if not valid_targets:
        print_info("No supported IDE directories found.")
        return 1

    any_installed = False

    for t in valid_targets:
        tgt_name = t["name"]
        meta = read_metadata(t)

        print_step(f"{tgt_name}")

        if not meta:
            print_info(f"agentforce-adlc is not installed for {tgt_name}.")
            continue

        any_installed = True
        commit_sha = meta.get("commit_sha")
        print()
        print(f"  Version:      {meta.get('version', 'unknown')}" +
              (f" ({commit_sha})" if commit_sha else ""))
        print(f"  Installed at: {meta.get('installed_at', 'unknown')}")
        print(f"  Install dir:  {t['install_dir']}")
        print(f"  Metadata:     {t['meta_file']}")

        # List installed skills
        skills_dir = t["skills_dir"]
        print()
        print(f"  {c('Skills:', Colors.BOLD)}")
        if skills_dir.exists():
            found = False
            for item in sorted(skills_dir.iterdir()):
                if item.is_dir() and _is_adlc_skill(item.name):
                    skill_md = item / "SKILL.md"
                    status = "ok" if skill_md.exists() else "MISSING SKILL.md"
                    print(f"    - {item.name} ({status})")
                    found = True
            if not found:
                print("    (none)")
        else:
            print("    (skills directory not found)")

        # List installed agents (Claude Code only)
        if t["supports_agents"]:
            agents_dir = t["agents_dir"]
            print()
            print(f"  {c('Agents:', Colors.BOLD)}")
            if agents_dir.exists():
                found = False
                for item in sorted(agents_dir.iterdir()):
                    if item.is_file() and _is_adlc_agent(item.name):
                        print(f"    - {item.name}")
                        found = True
                if not found:
                    print("    (none)")
            else:
                print("    (agents directory not found)")

        # List hooks (Claude Code only)
        if t["supports_hooks"]:
            hooks_scripts_dir = t["hooks_scripts_dir"]
            print()
            print(f"  {c('Hooks:', Colors.BOLD)}")
            if hooks_scripts_dir.exists():
                found = False
                for item in sorted(hooks_scripts_dir.iterdir()):
                    if item.is_file() and item.name.startswith("adlc-"):
                        print(f"    - {item.name}")
                        found = True
                if not found:
                    print("    (none)")
            else:
                print("    (hooks directory not found)")

            # Check settings.json hooks
            settings_file = t["settings_file"]
            print()
            print(f"  {c('Hook configuration:', Colors.BOLD)}")
            if settings_file.exists():
                try:
                    settings = json.loads(settings_file.read_text())
                    hooks = settings.get("hooks", {})
                    pre = hooks.get("PreToolUse", [])
                    post = hooks.get("PostToolUse", [])
                    has_guardrail = any(
                        "adlc-guardrails" in h.get("command", "")
                        for entry in pre for h in entry.get("hooks", [])
                    )
                    has_validator = any(
                        "adlc-agent-validator" in h.get("command", "")
                        for entry in post for h in entry.get("hooks", [])
                    )
                    print(f"    PreToolUse (guardrails):  {'configured' if has_guardrail else 'NOT configured'}")
                    print(f"    PostToolUse (validator):  {'configured' if has_validator else 'NOT configured'}")
                except (json.JSONDecodeError, IOError):
                    print("    Could not read settings.json")
            else:
                print("    settings.json not found")

    # Check for coexistence
    claude_dir = Path.home() / ".claude"
    sf_meta = claude_dir / ".sf-skills.json"
    md_meta = claude_dir / ".agentforce-md.json"
    coexist = []
    if sf_meta.exists():
        coexist.append("sf-skills")
    if md_meta.exists():
        coexist.append("agentforce-md")
    if coexist:
        print()
        print_info(f"Also installed: {', '.join(coexist)} (no conflicts expected)")

    print()
    return 0 if any_installed else 1


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="agentforce-adlc installer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--update", action="store_true",
                        help="Check for updates and apply if available")
    parser.add_argument("--force-update", action="store_true",
                        help="Force reinstall even if up-to-date")
    parser.add_argument("--uninstall", action="store_true",
                        help="Remove agentforce-adlc")
    parser.add_argument("--status", action="store_true",
                        help="Show installation status")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    parser.add_argument("--force", action="store_true",
                        help="Skip confirmations")
    parser.add_argument("--target", choices=TARGETS, default=None,
                        help="Install target: claude, cursor, or both (default: auto-detect)")
    parser.add_argument("--called-from-bash", action="store_true",
                        help=argparse.SUPPRESS)

    args = parser.parse_args()

    # Resolve target
    target = args.target if args.target else auto_detect_target()

    if args.status:
        sys.exit(cmd_status(target=target))
    elif args.uninstall:
        sys.exit(cmd_uninstall(dry_run=args.dry_run, force=args.force, target=target))
    elif args.update or args.force_update:
        sys.exit(cmd_update(dry_run=args.dry_run, force_update=args.force_update, target=target))
    else:
        sys.exit(cmd_install(dry_run=args.dry_run, force=args.force,
                             called_from_bash=args.called_from_bash, target=target))


if __name__ == "__main__":
    main()
