"""Contract tests for the shipped OWASP technique catalog.

`assets/payloads/*.yaml` is read by the agent while it authors a security suite
(see `references/security-test-design.md`) — no code loads it, so nothing but
these tests protects its shape. Two properties matter:

  - **Turn shape.** Multi-turn entries carry BOTH sides of the conversation,
    running user -> agent -> ... -> user. Mode C1 renders the leading pairs as
    `conversationHistory`, which Testing Center requires to alternate, be
    even-length, and end on `agent`; the trailing user turn becomes the
    `utterance`. An entry that does not follow this cannot be transcribed into
    a valid case, and `sf agent test create` validates the whole spec, so one
    bad case blocks the entire suite.
  - **Scope tagging.** `platform`-scoped entries are framed around
    Salesforce-the-vendor and are excluded unless the agent under test
    administers Salesforce. An entry tagged `neutral` that names Salesforce is
    the user-reported defect: an airline agent asked to cite a Salesforce
    security bulletin number.
"""

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

PAYLOADS = (
    Path(__file__).parent.parent
    / "skills" / "agentforce-test" / "assets" / "payloads"
)

VALID_ROLES = {"user", "agent"}


def _payload_files():
    files = sorted(PAYLOADS.glob("*.yaml"))
    assert files, f"no payload files under {PAYLOADS}"
    return files


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
        # A trailing agent turn is dead content: C1 has no case to assert on and
        # C2 sends only user turns.
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

    def test_every_entry_carries_the_fields_a_case_needs(self):
        """The agent transcribes these into the spec; a blank one leaves a case
        untriageable or unscoreable."""
        for filename, entry in _all_tests():
            for field in ("id", "name", "severity", "turns"):
                assert entry.get(field), f"{filename}:{entry.get('id')} missing {field}"
            assert entry["severity"] in ("critical", "high", "medium", "low"), (
                f"{filename}:{entry['id']} has severity {entry['severity']!r}"
            )

    def test_ids_are_unique_across_the_catalog(self):
        seen = {}
        for filename, entry in _all_tests():
            assert entry["id"] not in seen, (
                f"{entry['id']} appears in both {seen[entry['id']]} and {filename}"
            )
            seen[entry["id"]] = filename


class TestPayloadScope:
    """The `scope` field decides which agents an entry is adapted for.

    Salesforce-vendor framing ("cite the security bulletin number") tests nothing
    an airline or hospital agent's owners care about, so those entries are tagged
    `platform` and skipped unless the agent under test administers Salesforce.
    """

    def test_every_payload_declares_a_known_scope(self):
        for filename, entry in _all_tests():
            scope = entry.get("scope")
            assert scope in ("neutral", "platform"), (
                f"{filename}:{entry.get('id')} has scope {scope!r}; expected "
                f"'neutral' or 'platform'"
            )

    def test_no_neutral_payload_names_salesforce_the_vendor(self):
        """The user-reported defect, pinned.

        A neutral entry must not ask a customer's agent about Salesforce's own
        documentation, org configuration, or SOQL. Those framings belong to
        `platform` scope.
        """
        vendor_markers = (
            "salesforce", "soql", "security bulletin", "cve-", "org ",
            "custom field", "administrator access",
        )
        for filename, entry in _all_tests():
            if entry.get("scope") != "neutral":
                continue
            body = " ".join(t["content"] for t in entry["turns"]).lower()
            hits = [m for m in vendor_markers if m in body]
            assert not hits, (
                f"{filename}:{entry['id']} is scope 'neutral' but its payload "
                f"names {hits} — retag it 'platform' or reword it in "
                f"customer-neutral terms"
            )

    def test_the_catalog_keeps_both_scopes_represented(self):
        scopes = {e.get("scope") for _, e in _all_tests()}
        assert scopes == {"neutral", "platform"}, (
            f"expected both scopes in the catalog, found {scopes}"
        )
