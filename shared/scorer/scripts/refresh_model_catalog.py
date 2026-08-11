#!/usr/bin/env python3
"""Maintenance script: refresh src/model_catalog.py from the Agentforce docs.

Usage:
    python scripts/refresh_model_catalog.py            # diff only
    python scripts/refresh_model_catalog.py --write    # rewrite the catalog

Source: https://developer.salesforce.com/docs/ai/agentforce/guide/supported-models.html

Diff-only is the default because the heuristics that classify each row
(provider, modality, flags) are simple and a human glance after a doc
update may catch misclassifications. `--write` is opt-in.

The script does NOT preserve manual edits to the catalog. If maintainers
add local notes, they need to re-apply them after a refresh.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import html as _html
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = REPO_ROOT / "src" / "model_catalog.py"
DOC_URL = "https://developer.salesforce.com/docs/ai/agentforce/guide/supported-models.html"
USER_AGENT = "Mozilla/5.0 (compatible; scorer-cli refresh_model_catalog)"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@dataclass(frozen=True, order=True)
class ParsedRow:
    identifier: str
    label: str
    provider: str
    modality: str
    flags: tuple[str, ...]
    notes: str


def fetch_html(url: str = DOC_URL) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def extract_first_table(html: str) -> str:
    """Return the first <table>...</table> block from the doc.

    The page has two tables: the Supported list (first) and a "Rerouted To"
    / legacy table (second). We only ingest the first.
    """
    m = re.search(r"<table[^>]*>.*?</table>", html, re.DOTALL)
    if not m:
        raise SystemExit("Could not find a <table> in the doc HTML")
    return m.group(0)


def parse_table(table_html: str) -> list[ParsedRow]:
    """Parse the Supported Models table into ParsedRow records.

    Expected columns: Model | API Name | Notes
    """
    rows: list[ParsedRow] = []
    # tbody body, then iterate <tr>
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", table_html, re.DOTALL)
    if not body:
        raise SystemExit("Could not find <tbody> in the table")
    for tr_match in re.finditer(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", tr_match.group(1), re.DOTALL)
        if len(cells) < 3:
            continue
        raw_label = _strip_tags(cells[0])
        identifier = _strip_tags(cells[1])
        raw_notes = _strip_tags(cells[2])
        if not identifier.startswith("sfdc_ai__"):
            continue
        rows.append(_classify(raw_label, identifier, raw_notes))
    if not rows:
        raise SystemExit("Parsed 0 rows from the table — page format may have changed")
    rows.sort()
    return rows


def _strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = _html.unescape(s)
    return " ".join(s.split()).strip()


def _classify(raw_label: str, identifier: str, raw_notes: str) -> ParsedRow:
    """Apply heuristics to derive (label, provider, modality, flags, notes).

    Heuristics:
      - "(Beta)" suffix in the Model column → beta flag, stripped from label.
      - Notes lines starting with "*" are bullets; "Salesforce Trust Boundary"
        and "Geo-aware" become flags, anything else stays in `notes`.
      - Provider inferred from label patterns or identifier prefix.
      - modality = "embeddings" if label/identifier mentions embeddings,
        else "chat".
    """
    label = raw_label
    flags: list[str] = []

    # Beta suffix
    if "(Beta)" in label:
        label = label.replace("(Beta)", "").strip()
        flags.append("beta")

    # Notes bullets
    bullets = [b.strip() for b in re.split(r"[*•]", raw_notes) if b.strip()]
    note_remainders: list[str] = []
    for bullet in bullets:
        low = bullet.lower()
        if "salesforce trust boundary" in low:
            flags.append("trust-boundary")
        elif low == "geo-aware" or low.startswith("geo-aware"):
            flags.append("geo-aware")
        else:
            note_remainders.append(bullet)
    notes = "; ".join(note_remainders)

    modality = (
        "embeddings"
        if ("embedding" in label.lower() or "ada" in label.lower()
            or "embedding" in identifier.lower())
        else "chat"
    )
    provider = _infer_provider(label, identifier)
    return ParsedRow(
        identifier=identifier,
        label=label,
        provider=provider,
        modality=modality,
        flags=tuple(sorted(set(flags))),
        notes=notes,
    )


def _infer_provider(label: str, identifier: str) -> str:
    low = label.lower()
    if "on amazon bedrock" in low:
        if "anthropic" in low:
            return "Anthropic / Bedrock"
        return "Amazon Bedrock"
    if "vertex ai" in low or "vertexai" in identifier.lower():
        return "Google Vertex AI"
    if "openai / azure openai" in low:
        return "OpenAI / Azure OpenAI"
    if "azure openai" in low:
        return "Azure OpenAI"
    if "openai only" in low or identifier.startswith("sfdc_ai__DefaultOpenAI"):
        return "OpenAI"
    if identifier.startswith("sfdc_ai__DefaultGPT") or identifier.startswith("sfdc_ai__DefaultO"):
        return "OpenAI / Azure OpenAI"
    return "Unknown"


# ---------------------------------------------------------------------------
# Diff against current catalog
# ---------------------------------------------------------------------------

def load_current_catalog() -> dict[str, "ParsedRow"]:
    """Read src/model_catalog.py and return its CATALOG entries as a dict."""
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from src import model_catalog as mc  # type: ignore
    finally:
        sys.path.pop(0)
    out: dict[str, ParsedRow] = {}
    for m in mc.CATALOG:
        out[m.identifier] = ParsedRow(
            identifier=m.identifier,
            label=m.label,
            provider=m.provider,
            modality=m.modality,
            flags=tuple(sorted(m.flags)),
            notes=m.notes,
        )
    return out


def diff_catalogs(current: dict[str, ParsedRow], parsed: list[ParsedRow]) -> dict:
    parsed_by_id = {p.identifier: p for p in parsed}
    added = [p for p in parsed if p.identifier not in current]
    removed = [current[i] for i in current if i not in parsed_by_id]
    changed: list[tuple[ParsedRow, ParsedRow]] = []
    for ident, new in parsed_by_id.items():
        old = current.get(ident)
        if old and old != new:
            changed.append((old, new))
    return {"added": added, "removed": removed, "changed": changed}


def print_diff(d: dict) -> bool:
    """Print the diff. Return True if there are any changes."""
    any_changes = False
    if d["added"]:
        any_changes = True
        print(f"\nAdded ({len(d['added'])}):")
        for r in d["added"]:
            print(f"  + {r.identifier}  ({r.label})")
    if d["removed"]:
        any_changes = True
        print(f"\nRemoved ({len(d['removed'])}):")
        for r in d["removed"]:
            print(f"  - {r.identifier}  ({r.label})")
    if d["changed"]:
        any_changes = True
        print(f"\nChanged ({len(d['changed'])}):")
        for old, new in d["changed"]:
            print(f"  ~ {new.identifier}")
            for field in ("label", "provider", "modality", "flags", "notes"):
                ov = getattr(old, field)
                nv = getattr(new, field)
                if ov != nv:
                    print(f"      {field}: {ov!r} → {nv!r}")
    if not any_changes:
        print("\nNo changes — catalog is up to date.")
    return any_changes


# ---------------------------------------------------------------------------
# Codegen
# ---------------------------------------------------------------------------

def render_catalog_block(rows: list[ParsedRow]) -> str:
    """Render the CATALOG = (...) tuple literal as a Python source block."""
    grouped: dict[str, list[ParsedRow]] = {}
    for r in rows:
        grouped.setdefault(r.provider, []).append(r)

    lines: list[str] = ["CATALOG: tuple[Model, ...] = ("]
    for provider in sorted(grouped):
        lines.append(f"    # {provider}")
        for r in sorted(grouped[provider]):
            lines.append(_render_model_call(r))
        lines.append("")
    if lines[-1] == "":
        lines.pop()
    lines.append(")")
    return "\n".join(lines)


def _render_model_call(r: ParsedRow) -> str:
    label = r.label.replace('"', '\\"')
    notes = r.notes.replace('"', '\\"')
    if r.flags:
        flags_repr = "frozenset({" + ", ".join(f'"{f}"' for f in r.flags) + "})"
    else:
        flags_repr = None

    parts = [
        f'    Model("{r.identifier}",',
        f'          "{label}",',
        f'          "{r.provider}",',
        f'          "{r.modality}"',
    ]
    if flags_repr and notes:
        parts[-1] += ","
        parts.append(f'          {flags_repr},')
        parts.append(f'          notes="{notes}"),')
    elif flags_repr:
        parts[-1] += ","
        parts.append(f'          {flags_repr}),')
    elif notes:
        parts[-1] += ","
        parts.append(f'          notes="{notes}"),')
    else:
        parts[-1] += "),"
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# In-place rewrite
# ---------------------------------------------------------------------------

CATALOG_BLOCK_RE = re.compile(
    r"^CATALOG:\s*tuple\[Model,\s*\.\.\.\]\s*=\s*\(\s*\n.*?\n\)$",
    re.DOTALL | re.MULTILINE,
)
SNAPSHOT_DATE_RE = re.compile(r"^Snapshot date:\s*\d{4}-\d{2}-\d{2}", re.MULTILINE)


def rewrite_catalog_file(rows: list[ParsedRow]) -> None:
    src = CATALOG_PATH.read_text(encoding="utf-8")
    new_block = render_catalog_block(rows)
    if not CATALOG_BLOCK_RE.search(src):
        raise SystemExit(
            "Could not find the existing CATALOG = (...) block to replace. "
            "Has the file structure changed?"
        )
    src = CATALOG_BLOCK_RE.sub(new_block, src)
    today = _dt.date.today().isoformat()
    if SNAPSHOT_DATE_RE.search(src):
        src = SNAPSHOT_DATE_RE.sub(f"Snapshot date: {today}", src)
    CATALOG_PATH.write_text(src, encoding="utf-8")
    print(f"\nRewrote {CATALOG_PATH.relative_to(REPO_ROOT)}")
    print(f"Snapshot date set to {today}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    description = (__doc__ or "Refresh model catalog from the Agentforce docs.").splitlines()[0]
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--write", action="store_true",
        help="Rewrite src/model_catalog.py in place. Without this, only print the diff.",
    )
    parser.add_argument(
        "--url", default=DOC_URL,
        help=f"Override the source URL (default: {DOC_URL})",
    )
    args = parser.parse_args()

    print(f"Fetching {args.url} …")
    html = fetch_html(args.url)
    table_html = extract_first_table(html)
    parsed = parse_table(table_html)
    print(f"Parsed {len(parsed)} model rows.")

    current = load_current_catalog()
    print(f"Current catalog has {len(current)} entries.")

    diff = diff_catalogs(current, parsed)
    has_changes = print_diff(diff)

    if not args.write:
        if has_changes:
            print(
                "\nRun with --write to rewrite src/model_catalog.py with the parsed "
                "catalog. Inspect the diff first."
            )
        return 0
    if not has_changes:
        return 0
    rewrite_catalog_file(parsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
