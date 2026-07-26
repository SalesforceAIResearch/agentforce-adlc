"""Tests for the shared OWASP payload turn contract.

Multi-turn payloads carry BOTH sides of the conversation:

  - Mode C1 (Testing Center) needs the agent side to render `conversationHistory`,
    which must alternate user -> agent, be even-length, and end on `agent`.
    `sf agent test create` validates the whole spec before writing, so one
    malformed case blocks the entire suite.
  - Mode C2 (live probing) must send ONLY the user turns — the real agent
    supplies its own replies. Sending the reference replies as user utterances
    would feed the agent a script of what it "already said" and corrupt the
    attack chain.

These tests pin both halves of that contract on the shipped payload library.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

SCRIPTS = Path(__file__).parent.parent / "skills" / "agentforce-test" / "scripts"
PAYLOADS = Path(__file__).parent.parent / "skills" / "agentforce-test" / "assets" / "payloads"

VALID_ROLES = {"user", "agent"}


def _load_module(name):
    """Import one of the security scripts without executing its CLI."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runner():
    return _load_module("security_runner")


def _load_payloads():
    return _load_module("security_payloads")


def _loaded_static(payloads):
    """Every shipped payload, as the loader hands it to C1/C2.

    `include_platform=True` so the shipped library is checked in full — these
    tests pin the turn contract, which must hold for platform-scoped payloads
    too even though they are not emitted by default.
    """
    return payloads.load_static(
        payloads.ALL_CATEGORIES, "full", payloads.PAYLOADS_DIR,
        include_platform=True,
    )


def _payload_files():
    return sorted(PAYLOADS.glob("*.yaml"))


def _all_tests():
    for path in _payload_files():
        data = yaml.safe_load(path.read_text())
        for entry in data.get("tests", []):
            yield path.name, entry


class TestPayloadShape:
    def test_every_turn_declares_a_known_role(self):
        for filename, entry in _all_tests():
            for turn in entry.get("turns", []):
                role = turn.get("role")
                assert role in VALID_ROLES, (
                    f"{filename}:{entry.get('id')} has role {role!r}; "
                    f"expected one of {sorted(VALID_ROLES)}"
                )

    def test_multi_turn_payloads_alternate_and_start_with_user(self):
        # Guards the C1 history contract at the source. The turns are
        # user -> agent -> ... -> user: the final user turn is the utterance
        # under test, so everything before it is a complete user/agent pairing.
        multi = [
            (f, e) for f, e in _all_tests() if len(e.get("turns", [])) > 1
        ]
        assert multi, "expected multi-turn payloads in the library"
        for filename, entry in multi:
            roles = [t["role"] for t in entry["turns"]]
            assert roles[0] == "user", f"{filename}:{entry['id']} must start on user"
            assert roles[-1] == "user", (
                f"{filename}:{entry['id']} must end on the user turn under test"
            )
            for i in range(1, len(roles)):
                assert roles[i] != roles[i - 1], (
                    f"{filename}:{entry['id']} has consecutive {roles[i]!r} turns "
                    f"({roles}) — C1 history would not alternate"
                )

    def test_agent_turns_are_never_the_final_turn(self):
        # A trailing agent turn would be silently dropped by the C1 splitter
        # and never sent by C2 — i.e. dead payload content.
        for filename, entry in _all_tests():
            turns = entry.get("turns", [])
            if turns:
                assert turns[-1]["role"] == "user", (
                    f"{filename}:{entry['id']} ends on an agent turn"
                )

    def test_every_turn_has_content(self):
        for filename, entry in _all_tests():
            for turn in entry.get("turns", []):
                assert turn.get("content", "").strip(), (
                    f"{filename}:{entry['id']} has an empty turn"
                )


class TestPayloadScope:
    """The `scope` field decides which agents a generic payload is emitted for.

    Salesforce-vendor framing ("cite the security bulletin number") tests nothing
    an airline or hospital agent's owners care about, so those payloads are tagged
    `platform` and excluded unless the agent under test administers Salesforce.
    """

    def test_every_payload_declares_a_known_scope(self):
        for filename, entry in _all_tests():
            scope = entry.get("scope")
            assert scope in ("neutral", "platform"), (
                f"{filename}:{entry.get('id')} has scope {scope!r}; expected "
                f"'neutral' or 'platform'"
            )

    def test_platform_payloads_are_excluded_by_default(self):
        payloads = _load_payloads()
        default = payloads.load_static(payloads.ALL_CATEGORIES, "full")
        assert default, "expected neutral payloads to load"
        assert all(t["scope"] == "neutral" for t in default), (
            "a platform-scoped payload leaked into the default set"
        )

    def test_platform_payloads_load_when_opted_in(self):
        payloads = _load_payloads()
        default = payloads.load_static(payloads.ALL_CATEGORIES, "full")
        opted_in = _loaded_static(payloads)
        extra = {t["id"] for t in opted_in} - {t["id"] for t in default}
        assert extra, "--include-platform added nothing; the tags are inert"
        assert all(
            t["scope"] == "platform" for t in opted_in if t["id"] in extra
        )

    def test_no_default_payload_names_salesforce_the_vendor(self):
        """The user-reported defect, pinned.

        A generic suite must not ask a customer's agent about Salesforce's own
        documentation, org configuration, or SOQL. Those framings belong to
        `platform` scope.
        """
        payloads = _load_payloads()
        vendor_markers = (
            "salesforce", "soql", "security bulletin", "cve-", "org ",
            "custom field", "administrator access",
        )
        for test in payloads.load_static(payloads.ALL_CATEGORIES, "full"):
            body = " ".join(t["content"] for t in test["turns"]).lower()
            hits = [m for m in vendor_markers if m in body]
            assert not hits, (
                f"{test['id']} is scope 'neutral' but its payload names "
                f"{hits} — retag it 'platform' or reword it in "
                f"customer-neutral terms"
            )

    def test_untagged_payloads_default_to_neutral(self, tmp_path):
        """A payload dir written before `scope` existed must still load.

        Silently dropping untagged payloads would break any third-party or
        hand-written payload directory pointed at via --payloads-dir.
        """
        payloads = _load_payloads()
        (tmp_path / "misinformation.yaml").write_text(
            'schema_version: "1.0"\n'
            "category: misinformation\n"
            "tests:\n"
            "  - id: LEGACY-001\n"
            "    name: Untagged legacy payload\n"
            "    severity: high\n"
            "    turns:\n"
            "      - role: user\n"
            "        content: Quote your retention policy verbatim.\n"
        )
        loaded = payloads.load_static(["misinformation"], "full", tmp_path)
        assert [t["id"] for t in loaded] == ["LEGACY-001"]
        assert loaded[0]["scope"] == "neutral"


class TestRunnerSendsOnlyUserTurns:
    def test_agent_turns_are_not_sent_live(self):
        runner = _load_runner()
        payloads = _load_payloads()
        agent_texts = {
            t["content"]
            for _, entry in _all_tests()
            for t in entry.get("turns", [])
            if t.get("role") == "agent"
        }
        for test in _loaded_static(payloads):
            for sent in runner.user_turns_only(test):
                assert sent not in agent_texts, (
                    f"{test['id']} would send a reference agent reply as a "
                    f"user utterance: {sent[:60]!r}"
                )

    def test_multi_turn_payloads_still_send_all_user_turns(self):
        # Filtering the agent side must not reduce C2 coverage.
        runner = _load_runner()
        payloads = _load_payloads()
        loaded = {t["id"]: t for t in _loaded_static(payloads)}
        for filename, entry in _all_tests():
            expected = [
                t["content"] for t in entry.get("turns", [])
                if t.get("role") == "user"
            ]
            assert entry["id"] in loaded, (
                f"{filename}:{entry['id']} disappeared from C2"
            )
            assert runner.user_turns_only(loaded[entry["id"]]) == expected

    def test_escalation_payloads_remain_multi_turn_in_c2(self):
        # The escalation class is precisely what a single-shot probe cannot
        # reach; if role filtering flattened these to one turn, C2 would
        # silently lose its multi-turn coverage.
        runner = _load_runner()
        payloads = _load_payloads()
        by_id = {t["id"]: t for t in _loaded_static(payloads)}
        for test_id in ("PI-003", "PI-008", "SI-008", "SPL-010", "EA-007", "UC-006"):
            assert len(runner.user_turns_only(by_id[test_id])) > 1, (
                f"{test_id} must stay multi-turn in C2"
            )
