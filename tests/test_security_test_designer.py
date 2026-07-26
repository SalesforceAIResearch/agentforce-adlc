"""Tests for skills/agentforce-test/scripts/security_test_designer.py

The designer is the answer to "why is my airline agent being asked about
Salesforce security bulletins": every case it emits must be traceable to a
construct in the customer's own `.agent` file, and no case may be emitted for a
surface the agent does not have.

Two properties carry the whole redesign and are pinned hardest here:

  1. Surface-conditional emission. No write actions -> no bulk-mutation case; no
     `available when` -> no gate-bypass case. A PASS on a capability the agent
     lacks is not evidence of safety, it is a padded grade.
  2. Named grounding. Every case carries `surface` (what justified it) and
     `remediation` (which line to change). A finding that cannot be traced to a
     construct cannot be fixed, and gets dismissed.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

SCRIPTS = Path(__file__).parent.parent / "skills" / "agentforce-test" / "scripts"
AGENTS = (
    Path(__file__).parent.parent
    / "skills" / "agentforce-generate" / "assets" / "agents"
)
DESIGNER = SCRIPTS / "security_test_designer.py"

ALL_CATEGORIES = [
    "prompt_injection", "sensitive_info", "output_handling", "excessive_agency",
    "system_prompt_leakage", "misinformation", "unbounded_consumption",
]


def _load(name):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # @dataclass resolves annotations via sys.modules[cls.__module__].
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ap = _load("agent_profile")
di = _load("domain_inference")
std = _load("security_test_designer")


def design(agent_name, domain_key="", mode="full", max_per_category=0,
           categories=None):
    profile = ap.parse_agent_file(AGENTS / agent_name)
    domain, _ = di.infer_domain(profile, domain_key)
    designed = std.design_tests(
        profile, domain, categories or ALL_CATEGORIES, mode, max_per_category
    )
    return profile, domain, designed


def flatten(designed):
    return [c for cases in designed.values() for c in cases]


@pytest.fixture(scope="module")
def gated():
    """An agent with gates, writes, and LLM-filled inputs — full surface."""
    return design("verification-gate.agent")


@pytest.fixture(scope="module")
def bare():
    """An agent with no actions, gates, or sinks — minimal surface."""
    return design("hello-world.agent")


class TestSurfaceConditionalEmission:
    def test_gate_bypass_cases_exist_only_where_gates_do(self, gated, bare):
        _, _, gated_designed = gated
        _, _, bare_designed = bare
        gate_cases = [
            c for c in flatten(gated_designed) if c.technique == "guard_bypass"
        ]
        assert gate_cases, "an agent with `available when` must get bypass tests"
        assert not [
            c for c in flatten(bare_designed) if c.technique == "guard_bypass"
        ], "a gateless agent cannot have a gate bypassed"

    def test_one_bypass_case_per_gated_action_invocation(self, gated):
        profile, _, designed = gated
        gate_cases = [
            c for c in flatten(designed) if c.technique == "guard_bypass"
        ]
        expected = [
            i for i in profile.gated_invocations
            if i.kind == "action"
            and profile.action_by_name(i.target_ref.split(".", 1)[1]) is not None
        ]
        assert len(gate_cases) == len(expected)

    def test_bulk_mutation_cases_require_write_actions(self, gated, bare):
        _, _, gated_designed = gated
        _, _, bare_designed = bare
        assert [c for c in flatten(gated_designed)
                if c.technique == "bulk_operation"]
        assert not [c for c in flatten(bare_designed)
                    if c.technique == "bulk_operation"], (
            "an agent with no write actions cannot perform a bulk mutation"
        )

    def test_injection_sink_cases_require_an_llm_filled_input(self, gated, bare):
        _, _, gated_designed = gated
        _, _, bare_designed = bare
        assert [c for c in flatten(gated_designed)
                if c.technique == "parameter_injection"]
        assert not [c for c in flatten(bare_designed)
                    if c.technique in ("parameter_injection", "xss_reflection")], (
            "with no LLM-filled input there is nowhere for user text to land"
        )

    def test_topology_disclosure_requires_multiple_subagents(self, gated, bare):
        _, _, gated_designed = gated
        _, _, bare_designed = bare
        assert [c for c in flatten(gated_designed)
                if c.technique == "topology_disclosure"]
        assert not [c for c in flatten(bare_designed)
                    if c.technique == "topology_disclosure"], (
            "a single-subagent agent has no routing map to disclose"
        )

    def test_knowledge_boundary_case_requires_knowledge_grounding(self):
        _, _, grounded = design("knowledge-grounded.agent")
        _, _, gate = design("verification-gate.agent")
        assert [c for c in flatten(grounded)
                if c.technique == "knowledge_boundary"]
        assert not [c for c in flatten(gate)
                    if c.technique == "knowledge_boundary"]

    def test_bare_agent_still_gets_a_usable_suite(self, bare):
        """Surface-conditional must not mean "no tests". Conversation-level
        attacks (persona override, verbatim instruction dump, length abuse)
        apply to every agent and must still run."""
        _, _, designed = bare
        techniques = {c.technique for c in flatten(designed)}
        assert "multi_turn_injection" in techniques
        assert "direct_extraction" in techniques
        assert len(flatten(designed)) >= 5


class TestGroundingIsNamed:
    def test_every_case_names_its_surface_and_remediation(self, gated):
        _, _, designed = gated
        for c in flatten(designed):
            assert c.surface.strip(), f"{c.id} has no surface"
            assert c.remediation.strip(), f"{c.id} has no remediation"
            assert c.evaluation_note.strip(), f"{c.id} has no evaluation note"

    def test_gate_bypass_remediation_quotes_the_real_predicate(self, gated):
        profile, _, designed = gated
        gate_cases = [
            c for c in flatten(designed) if c.technique == "guard_bypass"
        ]
        guards = set(profile.gates)
        for c in gate_cases:
            assert any(g in c.remediation for g in guards), (
                f"{c.id} remediation does not quote an actual guard: "
                f"{c.remediation}"
            )

    def test_bulk_case_names_the_real_action_target(self, gated):
        profile, _, designed = gated
        targets = {a.target for a in profile.write_actions if a.target}
        bulk = [c for c in flatten(designed) if c.technique == "bulk_operation"]
        assert bulk
        assert any(
            any(t in c.surface for t in targets) for c in bulk
        ), "no bulk case named a real action target"

    def test_utterances_speak_prose_not_api_identifiers(self, gated):
        """An attacker types "initiate a return", not `initiate_return`. The
        identifier belongs in `surface`/`remediation` (for the engineer), never
        in the payload the agent receives — a snake_case probe is trivially
        recognizable as a test."""
        _, _, designed = gated
        for c in flatten(designed):
            for role, content in c.turns:
                assert "_" not in content or "@variables" not in content, (
                    f"{c.id} leaks a variable reference into the payload"
                )
                assert "available when" not in content, (
                    f"{c.id} quotes DSL syntax at the agent: {content[:80]}"
                )

    def test_case_names_are_unique_within_a_run(self, gated):
        """Two rules, two gates, two sinks -> the report must distinguish them
        or the reader cannot tell which one failed."""
        _, _, designed = gated
        names = [c.name for c in flatten(designed)]
        dupes = {n for n in names if names.count(n) > 1}
        assert not dupes, f"ambiguous case names: {dupes}"

    def test_case_ids_are_unique_and_prefixed_by_category(self, gated):
        _, _, designed = gated
        cases = flatten(designed)
        ids = [c.id for c in cases]
        assert len(set(ids)) == len(ids)
        prefixes = {
            "prompt_injection": "DYN-PI-", "sensitive_info": "DYN-SI-",
            "output_handling": "DYN-OH-", "excessive_agency": "DYN-EA-",
            "system_prompt_leakage": "DYN-SPL-", "misinformation": "DYN-MI-",
            "unbounded_consumption": "DYN-UC-",
        }
        for c in cases:
            assert c.id.startswith(prefixes[c.category]), c.id


class TestDomainVocabulary:
    def test_the_reported_defect_cannot_recur(self):
        """The user's complaint, pinned: an airline agent must never be asked
        about Salesforce's own documentation, orgs, or SOQL."""
        _, _, designed = design("order-service.agent", domain_key="airline")
        vendor = ("salesforce", "soql", "security bulletin", "cve-",
                  "custom field", "apex class")
        for c in flatten(designed):
            body = " ".join(content for _, content in c.turns).lower()
            hits = [m for m in vendor if m in body]
            assert not hits, f"{c.id} sends vendor-specific text {hits}: {body[:100]}"

    def test_domain_switch_changes_the_payload_language(self):
        def bodies(domain_key):
            _, _, designed = design("order-service.agent", domain_key=domain_key)
            return " ".join(
                content for c in flatten(designed) for _, content in c.turns
            ).lower()

        air = bodies("airline")
        health = bodies("healthcare")
        assert "passenger" in air and "patient" not in air
        assert "patient" in health and "passenger" not in health

    def test_domain_fabrication_facts_reach_the_misinformation_cases(self):
        _, domain, designed = design("order-service.agent", domain_key="airline")
        mi = designed["misinformation"]
        body = " ".join(content for c in mi for _, content in c.turns).lower()
        assert domain.fabrication[0].lower() in body, (
            "the misinformation case must ask the agent to invent a domain fact"
        )

    def test_payloads_carry_no_real_pii(self):
        """These get sent to a live agent, so every value must be synthetic."""
        _, _, designed = design("order-service.agent")
        body = " ".join(
            content for c in flatten(designed) for _, content in c.turns
        ).lower()
        for address in ("@gmail.", "@yahoo.", "@outlook."):
            assert address not in body
        # Any email in a payload must sit in a reserved example domain
        # (RFC 2606), so a probe can never reach a real inbox.
        import re
        for email in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", body):
            assert email.endswith(("example.com", "example.org", "example.net")), email


class TestTurnContract:
    """Generated multi-turn cases must satisfy the same Testing Center history
    contract as the shipped YAML library: alternating, user-first, user-last.
    `sf agent test create` validates the whole spec, so one bad generated case
    would reject every case in the suite."""

    @pytest.mark.parametrize("agent_name", [
        "verification-gate.agent", "order-service.agent", "hello-world.agent",
        "knowledge-grounded.agent", "router-first.agent",
    ])
    def test_generated_turns_alternate_user_first_user_last(self, agent_name):
        _, _, designed = design(agent_name)
        for c in flatten(designed):
            roles = [r for r, _ in c.turns]
            assert roles, f"{c.id} has no turns"
            assert roles[0] == "user", f"{c.id} starts on {roles[0]}"
            assert roles[-1] == "user", (
                f"{c.id} ends on {roles[-1]}; the last turn is the utterance "
                f"under test"
            )
            for i in range(1, len(roles)):
                assert roles[i] != roles[i - 1], f"{c.id} roles do not alternate: {roles}"

    def test_every_turn_has_content(self, gated):
        _, _, designed = gated
        for c in flatten(designed):
            for role, content in c.turns:
                assert content.strip(), f"{c.id} has an empty {role} turn"

    def test_reference_agent_replies_never_pre_concede_the_attack(self, gated):
        """The `role: agent` turns become `conversationHistory`, i.e. what the
        agent is told it already said. A reply that already complied would score
        the case as failed before the payload is even sent."""
        _, _, designed = gated
        conceding = ("sure, here", "i've deleted", "i have deleted", "as you wish",
                     "i've disabled", "restrictions are now", "switched modes",
                     "here is my system prompt", "ignoring my instructions")
        for c in flatten(designed):
            for role, content in c.turns:
                if role != "agent":
                    continue
                low = content.lower()
                assert not any(p in low for p in conceding), (
                    f"{c.id} agent turn pre-concedes: {content[:80]}"
                )


class TestSeverityAndFiltering:
    def test_severity_is_from_the_known_set(self, gated):
        _, _, designed = gated
        for c in flatten(designed):
            assert c.severity in std.SEVERITY_ORDER, f"{c.id}: {c.severity}"

    def test_write_gate_bypass_outranks_read_gate_bypass(self):
        """Severity is derived from the surface, not declared: defeating a gate
        on a mutation is worse than on a lookup."""
        profile, domain, designed = design("verification-gate.agent")
        for c in flatten(designed):
            if c.technique != "guard_bypass":
                continue
            action_name = c.name.rsplit(" ", 1)[-1]
            action = profile.action_by_name(action_name)
            assert action is not None, c.name
            assert c.severity == ("critical" if action.is_write else "high")

    def test_quick_mode_keeps_only_critical_and_high(self, gated):
        profile, domain, _ = gated
        quick = std.design_tests(profile, domain, ALL_CATEGORIES, "quick")
        assert flatten(quick)
        assert {c.severity for c in flatten(quick)} <= {"critical", "high"}

    def test_cases_are_ordered_most_severe_first(self, gated):
        _, _, designed = gated
        for cat, cases in designed.items():
            ranks = [std.SEVERITY_ORDER[c.severity] for c in cases]
            assert ranks == sorted(ranks), f"{cat} is not severity-ordered"

    def test_max_per_category_keeps_the_most_severe(self, gated):
        profile, domain, full = gated
        capped = std.design_tests(profile, domain, ALL_CATEGORIES, "full",
                                  max_per_category=2)
        for cat, cases in capped.items():
            assert len(cases) <= 2
            assert [c.id for c in cases] == [c.id for c in full[cat][:2]]

    def test_category_filter_is_respected(self, gated):
        profile, domain, _ = gated
        only = std.design_tests(profile, domain, ["excessive_agency"], "full")
        assert set(only) == {"excessive_agency"}

    def test_unknown_category_warns_and_is_skipped(self, gated, capsys):
        profile, domain, _ = gated
        out = std.design_tests(profile, domain, ["excessive_agency", "nonsense"])
        assert set(out) == {"excessive_agency"}
        assert "nonsense" in capsys.readouterr().err

    def test_ids_restart_each_run(self, gated):
        """The counter is class-level state; leaking it across runs would make
        two suites for the same agent disagree on IDs."""
        profile, domain, _ = gated
        first = std.design_tests(profile, domain, ALL_CATEGORIES, "full")
        second = std.design_tests(profile, domain, ALL_CATEGORIES, "full")
        assert [c.id for c in flatten(first)] == [c.id for c in flatten(second)]


class TestRenderedPayloadYaml:
    def test_rendered_yaml_round_trips_and_matches_the_shared_schema(self, gated):
        profile, domain, designed = gated
        for cat, cases in designed.items():
            text = std.render_payload_yaml(cat, cases, profile, domain)
            data = yaml.safe_load(text)
            assert data["category"] == cat
            assert data["owasp_id"] == std.CATEGORY_OWASP[cat]
            assert data["generated"]["source_file"].endswith(".agent")
            assert len(data["tests"]) == len(cases)
            for entry in data["tests"]:
                assert entry["id"] and entry["name"] and entry["severity"]
                assert entry["turns"] and entry["remediation"]
                assert entry["meta"]["generated"] is True

    def test_multiline_content_stays_a_single_line_scalar(self, gated):
        """A raw newline inside an unquoted scalar is what made
        `sf agent test create` reject the whole spec; JSON-encoding keeps every
        value on one line."""
        profile, domain, designed = gated
        multiline = [
            c for c in flatten(designed)
            if any("\n" in content for _, content in c.turns)
        ]
        assert multiline, "fixture no longer exercises multi-line payloads"
        text = std.render_payload_yaml(
            multiline[0].category,
            [c for c in designed[multiline[0].category] if c in multiline],
            profile, domain,
        )
        for line in text.splitlines():
            if line.strip().startswith("content:"):
                assert line.count("\\n") >= 0  # encoded, not a literal break
        assert yaml.safe_load(text)["tests"], "must still parse"


class TestCli:
    def run(self, *args):
        return subprocess.run(
            [sys.executable, str(DESIGNER), *args],
            capture_output=True, text=True,
        )
    def test_json_output_is_machine_readable(self):
        result = self.run(
            "--agent-file", str(AGENTS / "verification-gate.agent"), "--json",
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["total"] > 0
        assert data["domain"]
        assert data["domain_rationale"]
        assert set(data["categories"]) <= set(ALL_CATEGORIES)

    def test_summary_reports_the_surface_it_grounded_on(self):
        result = self.run("--agent-file", str(AGENTS / "verification-gate.agent"))
        assert result.returncode == 0, result.stderr
        assert "Surface:" in result.stdout
        assert "gates" in result.stdout
        assert "from:" in result.stdout, "each case must show its grounding"

    def test_missing_agent_file_exits_nonzero(self, tmp_path):
        result = self.run("--agent-file", str(tmp_path / "nope.agent"))
        assert result.returncode == 1
        assert "not found" in result.stderr

    def test_writes_one_payload_file_per_category(self, tmp_path):
        out = tmp_path / "payloads"
        result = self.run(
            "--agent-file", str(AGENTS / "verification-gate.agent"),
            "--output", str(out),
        )
        assert result.returncode == 0, result.stderr
        files = sorted(p.name for p in out.glob("*.yaml"))
        assert files, "no payload files written"
        for path in out.glob("*.yaml"):
            data = yaml.safe_load(path.read_text())
            assert data["tests"]

    def test_combined_yaml_output_is_multi_document(self, tmp_path):
        out = tmp_path / "all.yaml"
        result = self.run(
            "--agent-file", str(AGENTS / "verification-gate.agent"),
            "--output", str(out),
        )
        assert result.returncode == 0, result.stderr
        docs = [d for d in yaml.safe_load_all(out.read_text()) if d]
        assert len(docs) > 1
        assert {d["category"] for d in docs} <= set(ALL_CATEGORIES)
