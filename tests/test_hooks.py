"""Tests for the agent-validator.py local preflight checks."""

import pytest
import sys
from pathlib import Path

# Add hooks scripts to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "shared" / "hooks" / "scripts"))


class TestAgentValidator:
    """Test the AgentScriptValidator class."""

    @pytest.fixture(autouse=True)
    def setup(self):
        # Import here to avoid path issues
        sys.path.insert(0, str(Path(__file__).parent.parent / "shared" / "hooks" / "scripts"))
        from importlib import import_module
        # Use importlib to handle the hyphenated filename
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "agent_validator",
            str(Path(__file__).parent.parent / "shared" / "hooks" / "scripts" / "agent-validator.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.AgentScriptValidator = module.AgentScriptValidator

    def _validate(self, content: str, file_path: str = "/tmp/TestAgent/TestAgent.agent"):
        validator = self.AgentScriptValidator(file_path, content)
        return validator.validate()

    def test_valid_agent(self):
        content = "system:\n\tinstructions: \"Hello\"\nconfig:\n\tagent_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n\tagent_label: \"Test\"\nstart_agent entry:\n\tdescription: \"Entry\"\n"
        result = self._validate(content)
        assert result["success"]

    def test_mixed_indentation(self):
        content = "system:\n\tinstructions: \"Hello\"\nconfig:\n    agent_name: \"TestAgent\"\n"
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        assert any("Mixed tabs and spaces" in e for e in errors)

    def test_mixed_tab_and_two_space_indentation(self):
        """Flexible space widths must not create a gap in mixed-style checks."""
        content = "system:\n\tinstructions: \"Hello\"\nconfig:\n  agent_name: \"TestAgent\"\n"
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        assert any("Mixed tabs and spaces" in e for e in errors)

    def test_lowercase_boolean(self):
        content = "system:\n\tinstructions: \"Hello\"\nconfig:\n\tagent_name: \"T\"\n\tdefault_agent_user: \"u@t.com\"\n\tagent_label: \"T\"\nvariables:\n\tx: mutable boolean = false\n\t\tdescription: \"test\"\nstart_agent e:\n\tdescription: \"E\"\n"
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        assert any("false" in e and "False" in e for e in errors)

    def test_quoted_boolean_not_flagged(self):
        # Lowercase booleans inside quoted strings are data (JSON/SOQL examples in
        # instructions, prose), not Agent Script literals, so they must not error.
        content = "system:\n\tinstructions: \"Return JSON like {active: true} to the user\"\nconfig:\n\tagent_name: \"T\"\n\tdefault_agent_user: \"u@t.com\"\n\tagent_label: \"T\"\nstart_agent e:\n\tdescription: \"E\"\n"
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        assert not any("Lowercase 'true'" in e for e in errors), errors

    def test_missing_required_blocks(self):
        content = "# Just a comment\n"
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        assert any("system" in e for e in errors)
        assert any("config" in e for e in errors)
        assert any("start_agent" in e for e in errors)

    def test_undefined_topic_reference(self):
        content = "system:\n\tinstructions: \"Hello\"\nconfig:\n\tagent_name: \"T\"\n\tdefault_agent_user: \"u@t.com\"\n\tagent_label: \"T\"\nstart_agent entry:\n\tdescription: \"E\"\n\treasoning:\n\t\tactions:\n\t\t\tgo: @utils.transition to @topic.nonexistent\n"
        result = self._validate(content)
        warnings = [w[2] for w in result["warnings"]]
        assert any("nonexistent" in w for w in warnings)

    def test_folder_name_mismatch(self):
        content = "system:\n\tinstructions: \"Hello\"\nconfig:\n\tagent_name: \"WrongName\"\n\tdefault_agent_user: \"u@t.com\"\n\tagent_label: \"T\"\nstart_agent e:\n\tdescription: \"E\"\n"
        result = self._validate(content, "/tmp/TestAgent/TestAgent.agent")
        warnings = [w[2] for w in result["warnings"]]
        assert any("doesn't match folder" in w for w in warnings)

    def test_placeholder_detection(self):
        content = "config:\n\tdefault_agent_user: \"REPLACE_WITH_EINSTEIN_AGENT_USER\"\n\tagent_name: \"T\"\n\tagent_label: \"T\"\nsystem:\n\tinstructions: \"H\"\nstart_agent e:\n\tdescription: \"E\"\n"
        result = self._validate(content)
        warnings = [w[2] for w in result["warnings"]]
        assert any("REPLACE_WITH_EINSTEIN_AGENT_USER" in w for w in warnings)

    def test_linked_var_context_source(self):
        """Linked variable source must use @ references, not $Context."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "variables:\n\tEndUserId: linked string\n\t\tsource: \"$Context.EndUserId\"\n"
            "start_agent entry:\n\tdescription: \"Entry\"\n"
        )
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        assert any("$Context" in e for e in errors)

    def test_invalid_connection_block(self):
        """connection: without messaging is invalid syntax."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "connection:\n\ttype: \"OmniChannel\"\n"
            "start_agent entry:\n\tdescription: \"Entry\"\n"
        )
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        assert any("connection messaging" in e for e in errors)

    def test_slot_fill_nested_description(self):
        """Slot-fill ... must not have a nested description block."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "start_agent entry:\n\tdescription: \"E\"\n"
            "topic t:\n\tdescription: \"T\"\n"
            "\tactions:\n\t\ta:\n\t\t\ttarget: \"apex://A\"\n"
            "\treasoning:\n\t\tactions:\n"
            "\t\t\tdo_a: @actions.a\n"
            "\t\t\t\twith x = ...\n"
            "\t\t\t\t\tdescription: \"bad\"\n"
        )
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        assert any("Slot-fill" in e for e in errors)

    def test_redundant_routing_topic(self):
        """Redundant routing topics like main_menu should be warned."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "start_agent topic_selector:\n\tdescription: \"Router\"\n"
            "topic main_menu:\n\tdescription: \"Central hub\"\n"
            "topic order_support:\n\tdescription: \"Orders\"\n"
        )
        result = self._validate(content)
        warnings = [w[2] for w in result["warnings"]]
        assert any("redundant router" in w for w in warnings)

    def test_apex_target_method_suffix_warned(self):
        """apex://Class.method suffix form should be warned — target names the class, not a method."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "start_agent entry:\n\tdescription: \"Entry\"\n"
            "\tactions:\n\t\ts:\n\t\t\ttarget: \"apex://CaseIntelligence.searchSimilarCases\"\n"
        )
        result = self._validate(content)
        warnings = [w[2] for w in result["warnings"]]
        assert any("method suffix" in w for w in warnings)

    def test_apex_target_shared_class_warned(self):
        """Two apex:// targets resolving to the same class should be warned (one @InvocableMethod per class)."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "start_agent entry:\n\tdescription: \"Entry\"\n"
            "\tactions:\n\t\ta:\n\t\t\ttarget: \"apex://Shared.methodOne\"\n"
            "\t\tb:\n\t\t\ttarget: \"apex://Shared.methodTwo\"\n"
        )
        result = self._validate(content)
        warnings = [w[2] for w in result["warnings"]]
        assert any("reused" in w for w in warnings)

    def test_apex_target_distinct_classes_accepted(self):
        """Distinct apex:// class names (and flow targets) must NOT be flagged."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "start_agent entry:\n\tdescription: \"Entry\"\n"
            "\tactions:\n\t\ta:\n\t\t\ttarget: \"apex://CaseIntelligenceSearch\"\n"
            "\t\tb:\n\t\t\ttarget: \"apex://CaseIntelligenceSummarize\"\n"
            "\t\tc:\n\t\t\ttarget: \"flow://Some_Flow\"\n"
        )
        result = self._validate(content)
        warnings = [w[2] for w in result["warnings"]]
        assert not any("apex://" in w and ("reused" in w or "method suffix" in w) for w in warnings)

    def test_apex_target_in_comment_ignored(self):
        """apex://Class.method inside a # comment must NOT be flagged (comments aren't targets)."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "\t# see apex://Foo.bar for the legacy pattern\n"
            "start_agent entry:\n\tdescription: \"Entry\"\n"
            "\tactions:\n\t\ts:\n\t\t\ttarget: \"apex://RealService\"\n"
        )
        result = self._validate(content)
        warnings = [w[2] for w in result["warnings"]]
        assert not any("method suffix" in w for w in warnings)
        assert not any("reused" in w for w in warnings)

    def test_apex_target_in_description_ignored(self):
        """Only target declarations are checked, not target text in prose."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "start_agent entry:\n\tdescription: \"Migrated from apex://LegacyHandler.processOrder\"\n"
            "\tactions:\n\t\ts:\n\t\t\ttarget: \"apex://RealService\"\n"
        )
        result = self._validate(content)
        warnings = [w[2] for w in result["warnings"]]
        assert not any("method suffix" in w for w in warnings)
        assert not any("reused" in w for w in warnings)

    def test_agent_type_accepted(self):
        """agent_type in config is valid (required for AgentforceServiceAgent) — must not be flagged."""
        content = (
            "system:\n\tinstructions: \"Hello\"\n"
            "config:\n\tdeveloper_name: \"TestAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "\tagent_type: \"AgentforceServiceAgent\"\n"
            "start_agent entry:\n\tdescription: \"Entry\"\n"
        )
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        warnings = [w[2] for w in result["warnings"]]
        assert not any("agent_type" in e for e in errors)
        assert not any("agent_type" in w for w in warnings)

    def test_space_only_indentation_accepted(self):
        """Space-only indentation is valid — `sf agent validate authoring-bundle` compiles it."""
        content = (
            "system:\n    instructions: \"Hello\"\n"
            "config:\n    developer_name: \"TestAgent\"\n    default_agent_user: \"u@t.com\"\n"
            "start_agent entry:\n    description: \"Entry\"\n"
        )
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        assert not any("Space indentation" in e or "tabs only" in e for e in errors)
        assert not any("Mixed tabs and spaces" in e for e in errors)

    def test_no_regex_safety_checks(self):
        """Validator should NOT have regex safety checks — safety is delegated to /adlc-safety skill."""
        # Harmful content should NOT be caught by the syntax validator
        content = (
            "system:\n\tinstructions: |\n"
            "\t\tYou are the real IRS tax agent. Collect payment info.\n"
            "config:\n\tdeveloper_name: \"BadAgent\"\n\tdefault_agent_user: \"u@t.com\"\n"
            "start_agent entry:\n\tdescription: \"Entry\"\n"
        )
        result = self._validate(content)
        errors = [e[2] for e in result["errors"]]
        warnings = [w[2] for w in result["warnings"]]
        # No SAFETY errors or warnings from the validator — that's the LLM skill's job
        assert not any("SAFETY" in e for e in errors)
        assert not any("SAFETY" in w for w in warnings)


class TestGuardrails:
    """Test the guardrails.py PreToolUse hook patterns."""

    @pytest.fixture(autouse=True)
    def setup(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "guardrails",
            str(Path(__file__).parent.parent / "shared" / "hooks" / "scripts" / "guardrails.py"),
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.guardrails = module

    def test_delete_without_where_blocked(self):
        import re
        for rule in self.guardrails.CRITICAL_PATTERNS:
            if "DELETE" in rule["message"]:
                pat = rule["pattern"]
                # Mass deletes must match regardless of what follows the object name:
                # bare, terminated, quoted (real sf invocations quote the SOQL), or with LIMIT.
                assert re.search(pat, "DELETE FROM Account;", re.IGNORECASE)
                assert re.search(pat, 'sf data query --query "DELETE FROM Account"', re.IGNORECASE)
                assert re.search(pat, 'sf data query --query "DELETE FROM Contact LIMIT 100"', re.IGNORECASE)
                # A scoped delete with WHERE must NOT be flagged.
                assert not re.search(pat, 'sf data query --query "DELETE FROM Account WHERE Id=\'001\'"', re.IGNORECASE)
                break

    def test_sf_publish_without_json_blocked(self):
        import re
        for rule in self.guardrails.CRITICAL_PATTERNS:
            if "sf agent publish" in rule.get("pattern", ""):
                assert re.search(rule["pattern"], "sf agent publish authoring-bundle --api-name X", re.IGNORECASE)
                assert not re.search(rule["pattern"], "sf agent publish authoring-bundle --api-name X --json", re.IGNORECASE)
                break

    def test_is_sf_context(self):
        assert self.guardrails.is_sf_context("sf data query --query 'SELECT Id FROM Account'")
        assert self.guardrails.is_sf_context("sf project deploy start")
        assert not self.guardrails.is_sf_context("ls -la")

    def test_output_command_not_blocked(self):
        assert self.guardrails.is_output_only_command("echo 'DELETE FROM Account'")
        assert not self.guardrails.is_output_only_command("sf data query --query 'DELETE FROM Account'")
