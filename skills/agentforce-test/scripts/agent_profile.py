#!/usr/bin/env python3
"""Extract a security attack-surface profile from an `.agent` file.

This is the grounding step that makes security testing *about the customer's
agent* instead of about generic LLM trivia. A static payload like "cite the
Salesforce security bulletin for storing SSNs in custom fields" is meaningless
for an airline rebooking agent: it tests whether the agent hallucinates about
Salesforce-the-vendor, not whether it leaks a passenger's PNR or rebooks a
flight without verifying identity. The generator needs the agent's OWN nouns
and verbs to write tests that a customer would recognize as their risk.

What this produces (an `AgentProfile`):

  identity      developer_name / label / description / declared purpose
  domain        inferred business domain + vocabulary (see `domain_inference`)
  subagents     name, label, description, whether it is the router/start
  actions       Level-1 definitions: name, target (flow://, apex://), inputs,
                outputs, which outputs are `is_displayable`
  invocations   Level-2 uses: which action, which subagent, `available when`
                guards, whether an input is LLM-filled (`= ...`), which
                variables it writes (`set @variables.x`)
  variables     name, kind (mutable/linked), type, default, `source` binding,
                and whether the value looks like a security gate
  gates         the `available when` predicates, i.e. the authorization logic
                an attacker must defeat -- the single richest attack surface
  escalation    whether @utils.escalate exists (a safe-path expectation)
  knowledge     whether the agent is knowledge-grounded (drives LLM09 tests)
  guardrails    system-level instruction sentences that read like rules, so
                tests can target the agent's OWN stated policy

The parser is deliberately line/indent based and tolerant: `.agent` is an
indentation-sensitive DSL, not YAML, and this must not fail on constructs it
does not model. Anything unrecognized is skipped, never fatal -- a partial
profile still produces far better tests than a static payload list.

Usage:
    python3 agent_profile.py --agent-file path/to/My.agent [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path


# ---------------------------------------------------------------- data model

@dataclass
class ActionInput:
    name: str
    type: str = "string"
    description: str = ""
    # A definition-level binding such as `= @knowledge.citations_url` means the
    # platform supplies this value, so it is config plumbing rather than a place
    # user text lands. Used to keep injection sinks honest.
    bound_default: str = ""


@dataclass
class ActionOutput:
    name: str
    type: str = "string"
    description: str = ""
    is_displayable: bool = False


@dataclass
class ActionDef:
    """A Level-1 action definition inside `subagent: actions:`."""
    name: str
    subagent: str = ""
    description: str = ""
    target: str = ""            # "flow://Lookup_Order"
    target_type: str = ""       # flow | apex | retriever
    target_name: str = ""       # Lookup_Order
    inputs: list[ActionInput] = field(default_factory=list)
    outputs: list[ActionOutput] = field(default_factory=list)

    @property
    def is_write(self) -> bool:
        """Heuristic: does this action mutate data or trigger a side effect?

        Drives LLM06 (Excessive Agency) severity -- an unauthorized read is bad,
        an unauthorized write or send is worse.

        Only the action's OWN identifiers are inspected, never the prose
        description: descriptions routinely contain incidental verbs ("a string
        created by generative AI") that would misclassify a pure read as a write.

        Position matters. Actions are named verb-first (`update_email`,
        `Process_Refund`), so a write verb is only trusted in the leading
        position -- otherwise `verify_email` reads as a write because "email"
        can be a verb, when it is really a read that sets a gate. Verbs that are
        unambiguously mutating (`delete`, `refund`) count anywhere.
        """
        for ident in (self.name, self.target_name):
            tokens = [t.lower() for t in _name_tokens(ident) if t]
            if not tokens:
                continue
            if tokens[0] in WRITE_VERBS:
                return True
            if any(t in STRONG_WRITE_VERBS for t in tokens):
                return True
        return False

    @property
    def displayable_outputs(self) -> list[ActionOutput]:
        return [o for o in self.outputs if o.is_displayable]


@dataclass
class Invocation:
    """A Level-2 action use inside `reasoning: actions:`."""
    name: str
    subagent: str = ""
    kind: str = "action"        # action | transition | escalate | other
    target_ref: str = ""        # "@actions.lookup_order" / "@subagent.returns"
    description: str = ""
    guards: list[str] = field(default_factory=list)     # `available when` exprs
    llm_filled_inputs: list[str] = field(default_factory=list)  # `with x = ...`
    bound_inputs: dict = field(default_factory=dict)    # `with x = @variables.y`
    writes: list[str] = field(default_factory=list)     # `set @variables.x`

    @property
    def is_gated(self) -> bool:
        return bool(self.guards)


@dataclass
class Variable:
    name: str
    kind: str = "mutable"      # mutable | linked
    type: str = "string"
    default: str = ""
    source: str = ""           # @MessagingSession.Id for linked vars
    description: str = ""

    @property
    def is_gate(self) -> bool:
        """Does this variable look like an authorization / verification flag?"""
        blob = f"{self.name} {self.description}".lower()
        return self.type == "boolean" and any(w in blob for w in GATE_WORDS)

    @property
    def is_identity(self) -> bool:
        """Does this variable hold identity/PII-ish state worth exfiltrating?"""
        blob = f"{self.name} {self.description}".lower()
        return any(w in blob for w in IDENTITY_WORDS)


@dataclass
class Subagent:
    name: str
    label: str = ""
    description: str = ""
    is_start: bool = False
    instructions: str = ""


@dataclass
class AgentProfile:
    developer_name: str = ""
    agent_label: str = ""
    description: str = ""
    system_instructions: str = ""
    subagents: list[Subagent] = field(default_factory=list)
    actions: list[ActionDef] = field(default_factory=list)
    invocations: list[Invocation] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    has_escalation: bool = False
    has_knowledge: bool = False
    is_voice: bool = False
    source_file: str = ""

    # -- derived attack surface ------------------------------------------

    @property
    def gates(self) -> list[str]:
        """Unique `available when` predicates across all invocations."""
        seen, out = set(), []
        for inv in self.invocations:
            for g in inv.guards:
                if g not in seen:
                    seen.add(g)
                    out.append(g)
        return out

    @property
    def gated_invocations(self) -> list[Invocation]:
        return [i for i in self.invocations if i.is_gated]

    @property
    def write_actions(self) -> list[ActionDef]:
        return [a for a in self.actions if a.is_write]

    @property
    def gate_variables(self) -> list[Variable]:
        return [v for v in self.variables if v.is_gate]

    @property
    def linked_variables(self) -> list[Variable]:
        return [v for v in self.variables if v.kind == "linked"]

    @property
    def identity_variables(self) -> list[Variable]:
        return [v for v in self.variables if v.is_identity]

    @property
    def llm_filled(self) -> list[tuple[str, str]]:
        """(invocation_name, input_name) pairs the LLM fills from user text.

        These are the injection sinks: whatever the user says can end up in an
        action parameter, so they deserve targeted LLM01/LLM05 coverage.

        Inputs whose *definition* binds a platform value (`= @knowledge.x`) are
        excluded even when invoked as `with x = ...` -- the runtime supplies
        those, so they carry no user text and would only add noise.
        """
        out = []
        for inv in self.invocations:
            action = None
            if inv.target_ref.startswith("@actions."):
                action = self.action_by_name(inv.target_ref.split(".", 1)[1])
            bound = {
                p.name for p in (action.inputs if action else []) if p.bound_default
            }
            for param in inv.llm_filled_inputs:
                if param not in bound:
                    out.append((inv.name, param))
        return out

    def action_by_name(self, name: str) -> ActionDef | None:
        for a in self.actions:
            if a.name == name:
                return a
        return None

    def guardrail_sentences(self) -> list[str]:
        """System instructions that read like a rule the agent must not break.

        Lets the generator attack the agent's OWN stated policy ("Always verify
        customer identity before sharing order details") rather than a generic
        one, which is what makes a failure actionable for the customer.

        Returned strongest-first: authoring templates open with loop-control
        boilerplate ("Perform only the current task"), which is a rule but not a
        security rule. Overriding it proves nothing, so security-bearing rules
        are ranked ahead of it — the generator only uses the top few.
        """
        # `|` blocks wrap prose across lines, so a soft newline is not a sentence
        # boundary. Collapse single newlines to spaces (keeping blank lines as
        # separators) before splitting, or rules get truncated mid-clause.
        text = re.sub(r"\n{2,}", "\v", self.system_instructions or "")
        text = re.sub(r"\s*\n\s*", " ", text)
        scored = []
        for order, raw in enumerate(re.split(r"(?<=[.!:])\s+|\v", text)):
            s = raw.strip().lstrip("-*").strip()
            if len(s) < 15:
                continue
            low = s.lower()
            if any(low.startswith(p) or f" {p} " in f" {low} " for p in RULE_MARKERS):
                scored.append((-_rule_score(low), order, s.rstrip(".")))
        scored.sort()
        return [s for _, _, s in scored]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["derived"] = {
            "gates": self.gates,
            "write_action_names": [a.name for a in self.write_actions],
            "gate_variable_names": [v.name for v in self.gate_variables],
            "linked_variable_names": [v.name for v in self.linked_variables],
            "identity_variable_names": [v.name for v in self.identity_variables],
            "llm_filled_inputs": [f"{i}.{p}" for i, p in self.llm_filled],
            "guardrail_sentences": self.guardrail_sentences(),
        }
        return d


def _name_tokens(identifier: str) -> list[str]:
    """Split `Process_Refund` / `processRefund` / `process-refund` into words."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", identifier)
    return [t for t in re.split(r"[^A-Za-z0-9]+", spaced) if t]


# Verbs that indicate mutation when they LEAD an action name. Several are also
# common nouns ("email", "credit", "post", "change"), so position disambiguates.
WRITE_VERBS = frozenset({
    "create", "update", "delete", "remove", "cancel", "refund", "issue",
    "initiate", "submit", "send", "email", "post", "transfer", "book",
    "rebook", "charge", "pay", "modify", "change", "set", "upsert",
    "schedule", "reschedule", "close", "escalate", "apply", "assign",
    "grant", "revoke", "reset", "activate", "deactivate", "void", "credit",
    "add", "insert", "write", "process", "place", "order", "approve",
})

# Mutating no matter where they appear -- these have no plausible read reading.
STRONG_WRITE_VERBS = frozenset({
    "delete", "remove", "cancel", "refund", "upsert", "revoke", "deactivate",
    "void", "rebook", "reschedule",
})

GATE_WORDS = (
    "verif", "authent", "authoriz", "confirm", "validat", "eligib",
    "approv", "consent", "identif", "allow", "permit", "entitl",
)

IDENTITY_WORDS = (
    "email", "phone", "ssn", "customer", "contact", "account", "user",
    "member", "passenger", "patient", "client", "address", "dob",
    "birth", "card", "payment", "policy_number", "national_id", "tax",
)

# Per-field metadata keys inside an inputs/outputs block. They look exactly like
# a `name: type` field declaration, so they are excluded by name.
FIELD_META_KEYS = frozenset({
    "description", "is_displayable", "is_required", "required", "label",
})

# Words that mark a system instruction as a behavioral rule worth attacking.
RULE_MARKERS = (
    "always", "never", "do not", "don't", "must", "only", "before",
    "required", "ensure", "verify", "refuse", "avoid", "prohibited",
)

# Rules whose subject matter is a security control. A payload that overrides one
# of these is a real finding; overriding "be concise" is not.
SECURITY_RULE_WORDS = (
    "verif", "authent", "authoriz", "identit", "confirm", "permission",
    "fabricat", "invent", "guess", "make up", "hallucinat", "accurate",
    "personal", "pii", "sensitive", "private", "confidential", "credential",
    "password", "ssn", "payment", "card", "disclos", "share", "reveal",
    "escalat", "human", "instruction", "prompt", "internal", "scope",
    "medical", "legal", "financial advice", "diagnos", "another customer",
)

# Instruction-loop / style boilerplate that authoring templates emit verbatim.
# It matches RULE_MARKERS but carries no security weight.
BOILERPLATE_RULE_WORDS = (
    "current task", "underlying request", "request-handling", "be helpful",
    "concise", "empathetic", "friendly", "tone", "brief",
)


def _rule_score(low: str) -> int:
    """Rank a candidate guardrail sentence by how security-bearing it is."""
    score = sum(2 for w in SECURITY_RULE_WORDS if w in low)
    score -= sum(3 for w in BOILERPLATE_RULE_WORDS if w in low)
    return score


# ------------------------------------------------------------------- parsing

def _indent(line: str) -> int:
    """Indent width in spaces; a tab counts as 4 (see CLAUDE.md conventions)."""
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 4
        else:
            break
    return n


def _strip_comment(line: str) -> str:
    """Remove a trailing `#` comment when it is not inside a quoted string."""
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _unquote(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _collect_block(lines: list[str], start: int, base_indent: int) -> tuple[str, int]:
    """Collect an indented text block (e.g. `instructions: |`) as plain text."""
    out, i = [], start
    while i < len(lines):
        raw = lines[i]
        if raw.strip() and _indent(raw) <= base_indent:
            break
        text = raw.strip()
        # `->` conditional bodies use `|` prefixes for literal response text.
        if text.startswith("| "):
            text = text[2:]
        elif text == "|":
            text = ""
        out.append(text)
        i += 1
    return "\n".join(out).strip(), i


def parse_agent_file(path: Path) -> AgentProfile:
    """Parse an `.agent` file into an AgentProfile.

    Tolerant by design: unknown constructs are skipped rather than raising, so
    a new DSL feature degrades coverage instead of breaking security testing.
    """
    content = path.read_text(encoding="utf-8")
    raw_lines = content.splitlines()
    lines = [_strip_comment(l) for l in raw_lines]

    profile = AgentProfile(source_file=str(path))
    profile.has_escalation = "@utils.escalate" in content
    profile.has_knowledge = bool(
        re.search(r"^\s*knowledge:", content, re.M)
        or "@knowledge." in content
        or "retriever://" in content
    )
    profile.is_voice = bool(re.search(r"^\s*modality\s+voice:", content, re.M))

    # config: block scalars
    for key, attr in (
        ("developer_name", "developer_name"),
        ("agent_label", "agent_label"),
        ("description", "description"),
    ):
        m = re.search(rf'^\s*{key}:\s*(.+)$', content, re.M)
        if m:
            setattr(profile, attr, _unquote(m.group(1)))

    i = 0
    cur_subagent: Subagent | None = None
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        ind = _indent(line)

        # ---- system: instructions ------------------------------------
        if ind == 0 and stripped == "system:":
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or _indent(lines[j]) > 0):
                s = lines[j].strip()
                if re.match(r"^instructions:\s*[|>]?\s*$", s):
                    block, j2 = _collect_block(lines, j + 1, _indent(lines[j]))
                    profile.system_instructions = block
                    j = j2
                    continue
                j += 1
            i = j
            continue

        # ---- variables: ----------------------------------------------
        if ind == 0 and stripped == "variables:":
            i = _parse_variables(lines, i + 1, profile)
            continue

        # ---- subagent / start_agent ----------------------------------
        m = re.match(r"^(start_agent|subagent)\s+([A-Za-z0-9_]+)\s*:", stripped)
        if ind == 0 and m:
            cur_subagent = Subagent(name=m.group(2), is_start=m.group(1) == "start_agent")
            profile.subagents.append(cur_subagent)
            i += 1
            continue

        if cur_subagent is not None:
            # label / description on the subagent
            m = re.match(r'^(label|description):\s*(.+)$', stripped)
            if m and ind > 0:
                setattr(cur_subagent, m.group(1), _unquote(m.group(2)))
                i += 1
                continue

            # Level-1 `actions:` block (a sibling of `reasoning:`)
            if re.match(r"^actions:\s*$", stripped):
                i = _parse_action_defs(lines, i + 1, ind, cur_subagent.name, profile)
                continue

            # `reasoning:` -> instructions + Level-2 invocations
            if re.match(r"^reasoning:\s*$", stripped):
                i = _parse_reasoning(lines, i + 1, ind, cur_subagent, profile)
                continue

        i += 1

    return profile


def _parse_variables(lines: list[str], start: int, profile: AgentProfile) -> int:
    """Parse the top-level `variables:` block."""
    i = start
    cur: Variable | None = None
    while i < len(lines):
        raw = lines[i]
        if raw.strip() and _indent(raw) == 0:
            break
        s = raw.strip()
        if not s:
            i += 1
            continue

        # `Name: linked string` / `Name: mutable boolean = False`
        m = re.match(
            r"^([A-Za-z0-9_]+):\s*(mutable|linked)\s+([A-Za-z0-9_\[\]]+)"
            r"(?:\s*=\s*(.+))?$",
            s,
        )
        if m:
            cur = Variable(
                name=m.group(1), kind=m.group(2), type=m.group(3),
                default=_unquote(m.group(4) or ""),
            )
            profile.variables.append(cur)
            i += 1
            continue

        if cur is not None:
            m = re.match(r"^(source|description):\s*(.+)$", s)
            if m:
                setattr(cur, m.group(1), _unquote(m.group(2)))
        i += 1
    return i


def _parse_action_defs(
    lines: list[str], start: int, parent_indent: int, subagent: str,
    profile: AgentProfile,
) -> int:
    """Parse a Level-1 `actions:` block (action definitions with targets/IO)."""
    i = start
    cur: ActionDef | None = None
    section = ""          # "inputs" | "outputs" | ""
    cur_field = None      # last ActionInput/ActionOutput, for description lines
    name_indent = None

    while i < len(lines):
        raw = lines[i]
        if raw.strip() and _indent(raw) <= parent_indent:
            break
        s = raw.strip()
        if not s:
            i += 1
            continue
        ind = _indent(raw)

        # A `reasoning:` sibling ends the definitions block.
        if re.match(r"^reasoning:\s*$", s) and ind <= parent_indent:
            break

        # New action name: `lookup_order:` (bare key, no value)
        m = re.match(r"^([A-Za-z0-9_]+):\s*$", s)
        if m and m.group(1) not in ("inputs", "outputs") and (
            name_indent is None or ind <= name_indent
        ):
            name_indent = ind
            cur = ActionDef(name=m.group(1), subagent=subagent)
            profile.actions.append(cur)
            section, cur_field = "", None
            i += 1
            continue

        if cur is None:
            i += 1
            continue

        if re.match(r"^inputs:\s*$", s):
            section, cur_field = "inputs", None
            i += 1
            continue
        if re.match(r"^outputs:\s*$", s):
            section, cur_field = "outputs", None
            i += 1
            continue

        # Any `scheme://Name` target. Beyond flow/apex/retriever, agents use
        # `standardInvocableAction://` for platform actions (knowledge search,
        # etc.), and those are just as much an attack surface.
        m = re.match(r'^target:\s*"?([A-Za-z][A-Za-z0-9_]*)://([^"\s]+)"?', s)
        if m:
            cur.target_type, cur.target_name = m.group(1), m.group(2)
            cur.target = f"{m.group(1)}://{m.group(2)}"
            section, cur_field = "", None
            i += 1
            continue

        m = re.match(r"^description:\s*(.+)$", s)
        if m:
            text = _unquote(m.group(1))
            if cur_field is not None:
                cur_field.description = text
            elif not section:
                cur.description = text
            i += 1
            continue

        # Field-level metadata. MUST be matched before the generic
        # `name: type` rule below, which would otherwise read
        # `is_displayable: True` as a field named `is_displayable` of type `True`.
        m = re.match(r"^is_displayable:\s*(True|False)$", s)
        if m:
            if isinstance(cur_field, ActionOutput):
                cur_field.is_displayable = m.group(1) == "True"
            i += 1
            continue

        # `field_name: string` (optionally `= @knowledge.x` for defaults)
        m = re.match(r"^([A-Za-z0-9_]+):\s*([A-Za-z0-9_\[\]]+)\s*(?:=\s*(.*))?$", s)
        if m and section in ("inputs", "outputs") and m.group(1) not in FIELD_META_KEYS:
            if section == "inputs":
                cur_field = ActionInput(
                    name=m.group(1), type=m.group(2),
                    bound_default=(m.group(3) or "").strip(),
                )
                cur.inputs.append(cur_field)
            else:
                cur_field = ActionOutput(name=m.group(1), type=m.group(2))
                cur.outputs.append(cur_field)
        i += 1
    return i


def _parse_reasoning(
    lines: list[str], start: int, parent_indent: int, subagent: Subagent,
    profile: AgentProfile,
) -> int:
    """Parse `reasoning:` -> instructions text and Level-2 invocations."""
    i = start
    while i < len(lines):
        raw = lines[i]
        if raw.strip() and _indent(raw) <= parent_indent:
            break
        s = raw.strip()
        if not s:
            i += 1
            continue

        if re.match(r"^instructions:\s*[|>]?\s*$", s) or re.match(
            r"^instructions:\s*->\s*$", s
        ):
            block, i = _collect_block(lines, i + 1, _indent(raw))
            subagent.instructions = block
            continue

        if re.match(r"^actions:\s*$", s):
            i = _parse_invocations(lines, i + 1, _indent(raw), subagent.name, profile)
            continue
        i += 1
    return i


def _parse_invocations(
    lines: list[str], start: int, parent_indent: int, subagent: str,
    profile: AgentProfile,
) -> int:
    """Parse a Level-2 `actions:` block (invocations with guards and bindings)."""
    i = start
    cur: Invocation | None = None
    while i < len(lines):
        raw = lines[i]
        if raw.strip() and _indent(raw) <= parent_indent:
            break
        s = raw.strip()
        if not s:
            i += 1
            continue

        # `verify: @actions.verify_customer` / `to_orders: @utils.transition to @subagent.x`
        m = re.match(r"^([A-Za-z0-9_]+):\s*(@[A-Za-z0-9_.]+)(.*)$", s)
        if m:
            ref, rest = m.group(2), m.group(3).strip()
            if ref.startswith("@utils.transition"):
                kind = "transition"
                tm = re.search(r"@subagent\.([A-Za-z0-9_]+)", rest)
                target_ref = f"@subagent.{tm.group(1)}" if tm else ref
            elif ref.startswith("@utils.escalate"):
                kind, target_ref = "escalate", ref
            elif ref.startswith("@actions."):
                kind, target_ref = "action", ref
            else:
                kind, target_ref = "other", ref
            cur = Invocation(
                name=m.group(1), subagent=subagent, kind=kind, target_ref=target_ref
            )
            profile.invocations.append(cur)
            i += 1
            continue

        if cur is None:
            i += 1
            continue

        m = re.match(r"^description:\s*(.+)$", s)
        if m:
            cur.description = _unquote(m.group(1))
            i += 1
            continue

        m = re.match(r"^available when\s+(.+)$", s)
        if m:
            cur.guards.append(m.group(1).strip())
            i += 1
            continue

        m = re.match(r"^with\s+([A-Za-z0-9_]+)\s*=\s*(.+)$", s)
        if m:
            name, value = m.group(1), m.group(2).strip()
            if value == "...":
                # LLM-filled from user text -> an injection sink.
                cur.llm_filled_inputs.append(name)
            else:
                cur.bound_inputs[name] = value
            i += 1
            continue

        m = re.match(r"^set\s+@variables\.([A-Za-z0-9_]+)\s*=", s)
        if m:
            cur.writes.append(m.group(1))
        i += 1
    return i


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract a security attack-surface profile from an .agent file"
    )
    ap.add_argument("--agent-file", required=True, help="Path to the .agent file")
    ap.add_argument("--json", action="store_true", help="Emit JSON (default: summary)")
    args = ap.parse_args()

    path = Path(args.agent_file)
    if not path.exists():
        print(f"ERROR: not found: {path}", file=sys.stderr)
        return 1

    profile = parse_agent_file(path)

    if args.json:
        print(json.dumps(profile.to_dict(), indent=2))
        return 0

    print(f"Agent:      {profile.developer_name or '(unknown)'} — {profile.agent_label}")
    print(f"Purpose:    {profile.description}")
    print(f"Subagents:  {len(profile.subagents)} "
          f"({', '.join(s.name for s in profile.subagents)})")
    print(f"Actions:    {len(profile.actions)} "
          f"({len(profile.write_actions)} write/side-effecting)")
    print(f"Variables:  {len(profile.variables)} "
          f"({len(profile.gate_variables)} gates, {len(profile.linked_variables)} linked)")
    print(f"Gates:      {len(profile.gates)}")
    for g in profile.gates:
        print(f"              available when {g}")
    print(f"LLM-filled: {len(profile.llm_filled)}")
    for inv, param in profile.llm_filled:
        print(f"              {inv}.{param}")
    print(f"Escalation: {profile.has_escalation}   Knowledge: {profile.has_knowledge}"
          f"   Voice: {profile.is_voice}")
    rules = profile.guardrail_sentences()
    print(f"Guardrails: {len(rules)}")
    for r in rules:
        print(f"              {r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
