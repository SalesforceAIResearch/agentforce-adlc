"""Round-trip test for NGT YAML → AiTestingDefinition XML via sf CLI.

Pins the public seam W-22513811 cuts over to:
  - sf agent test create --test-runner agentforce-studio --preview --spec <yaml>
  - emits XML with root element <AiTestingDefinition>
  - written to a file ending in .xml under aiTestingDefinitions/
  - byte-for-byte stable against tests/fixtures/ngt/canonical-spec.expected.xml

Skipped when the sf CLI isn't available or no NGT-enabled org alias is
configured. The skill's runtime behavior depends on this exact contract; if
this test fails, the skill's docs / CLI invocations need to be re-examined.

Set ADLC_NGT_TEST_ORG=<sf-alias> to run live. Without it, the round-trip
test self-skips so local devs without an NGT org get a green suite.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "ngt"
SPEC_YAML = FIXTURE_DIR / "canonical-spec.yaml"
EXPECTED_XML = FIXTURE_DIR / "canonical-spec.expected.xml"
ASSET_YAML = REPO_ROOT / "skills" / "testing-agentforce" / "assets" / "ngt-test-spec.yaml"


def _have_sf_cli() -> bool:
    return shutil.which("sf") is not None


def _ngt_org_alias() -> str | None:
    return os.environ.get("ADLC_NGT_TEST_ORG")


def _normalize_xml(xml: str) -> str:
    """Collapse insignificant whitespace so XMLBuilder formatting drift doesn't break the diff."""
    xml = xml.lstrip("﻿").replace("\r\n", "\n")
    xml = re.sub(r">\s+<", "><", xml)
    return xml.strip()


def test_canonical_yaml_in_assets_matches_fixture():
    """The shipped asset and the test fixture are the same file. If they drift,
    we're testing one shape and shipping another — fail loud."""
    assert ASSET_YAML.read_text() == SPEC_YAML.read_text(), (
        "canonical NGT YAML in assets/ has drifted from tests/fixtures/ngt/. "
        "Both files should contain the byte-for-byte fixture from "
        "salesforcecli/plugin-agent#430's ngtTestSpec.yaml."
    )


def test_expected_xml_committed():
    """The golden XML must exist and be non-empty. Captured via Phase 0b."""
    assert EXPECTED_XML.exists(), (
        f"missing golden fixture at {EXPECTED_XML}. Capture via:\n"
        f"  sf agent test create --spec {SPEC_YAML} --api-name X "
        f"--test-runner agentforce-studio --target-org $ADLC_NGT_TEST_ORG "
        f"--preview --json | python3 -c 'import json,sys; "
        f'print(json.load(sys.stdin)["result"]["contents"])\' > {EXPECTED_XML}'
    )
    contents = EXPECTED_XML.read_text()
    assert "<AiTestingDefinition" in contents, "golden XML has wrong root element"
    assert len(contents) > 100, "golden XML suspiciously short"


@pytest.mark.skipif(not _have_sf_cli(), reason="sf CLI not installed")
@pytest.mark.skipif(_ngt_org_alias() is None, reason="ADLC_NGT_TEST_ORG not set")
def test_ngt_round_trip_via_cli(tmp_path):
    """Run sf agent test create --preview against the canonical fixture and assert
    the produced XML matches the committed golden byte-for-byte (after whitespace
    normalization)."""
    org = _ngt_org_alias()
    api_name = "AdlcNgtRoundTrip"

    proc = subprocess.run(
        [
            "sf", "agent", "test", "create",
            "--spec", str(SPEC_YAML),
            "--api-name", api_name,
            "--test-runner", "agentforce-studio",
            "--target-org", org,
            "--preview",
            "--json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
    )
    assert proc.returncode == 0, (
        f"sf agent test create failed (exit {proc.returncode}):\n"
        f"stdout: {proc.stdout[:1000]}\n"
        f"stderr: {proc.stderr[:1000]}"
    )

    payload = json.loads(proc.stdout)
    assert payload.get("status") == 0, payload

    result = payload["result"]

    # Contract 1: the file path the CLI reports must end in .xml and follow the
    # `--preview` filename convention (`<api-name>-preview-<ISO>.xml`). When
    # NOT in --preview mode, the CLI writes under
    # force-app/main/default/aiTestingDefinitions/ (NGT) vs aiEvaluationDefinitions/
    # (legacy) — but --preview drops the file in cwd without that prefix.
    written_path = Path(result["path"])
    assert written_path.suffix == ".xml", f"unexpected path suffix: {written_path}"
    assert "-preview-" in written_path.name, (
        f"--preview filename convention missing: {written_path}"
    )

    # Contract 2: XML contents must have the NGT root element.
    contents = result["contents"]
    assert "<AiTestingDefinition" in contents, (
        "wrong root element — likely defaulted to AiEvaluationDefinition (legacy)"
    )
    assert "<scorer>" in contents, "scorer elements missing from XML"

    # Contract 3: byte-for-byte against the golden fixture (after whitespace
    # normalization for any incidental indentation/newline drift in XMLBuilder).
    expected = _normalize_xml(EXPECTED_XML.read_text())
    actual = _normalize_xml(contents)
    assert actual == expected, (
        "NGT XML drift detected. The CLI changed its serialization or the "
        "canonical YAML changed.\n"
        "  - If the CLI changed: regenerate the golden via Phase 0b in "
        "docs/spikes/2026-05-28-ngt-integration/07-impl-plan-skill-cutover.md\n"
        "  - If the YAML changed: confirm the change is intended and update the "
        "golden.\n"
        f"\n--- expected (normalized, first 500 chars) ---\n{expected[:500]}\n"
        f"\n--- actual (normalized, first 500 chars) ---\n{actual[:500]}"
    )
