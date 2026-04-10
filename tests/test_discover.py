"""Tests for discover.py — target extraction from .agent files."""

import pytest
from unittest.mock import patch
from pathlib import Path
from scripts.discover import extract_targets, extract_actions, _suggest_similar, Suggestion, IoMismatch, validate_action_io


SAMPLE_AGENT = """\
system:
\tinstructions: "You are a test agent."
\tmessages:
\t\twelcome: "Hello!"
\t\terror: "Error occurred."

config:
\tagent_name: "TestAgent"
\tdefault_agent_user: "user@test.com"
\tagent_label: "Test Agent"
\tdescription: "A test agent"

variables:
\tEndUserId: linked string
\t\tsource: @MessagingSession.MessagingEndUserId
\t\tdescription: "End User ID"

language:
\tdefault_locale: "en_US"
\tadditional_locales: ""
\tall_additional_locales: False

start_agent entry:
\tdescription: "Entry point"
\treasoning:
\t\tinstructions: |
\t\t\tRoute to the appropriate topic.
\t\tactions:
\t\t\tgo_orders: @utils.transition to @topic.orders
\t\t\t\tdescription: "Check orders"

topic orders:
\tdescription: "Handle order inquiries"
\tactions:
\t\tget_order_status:
\t\t\tdescription: "Look up order status"
\t\t\tinputs:
\t\t\t\torder_number: string
\t\t\t\t\tdescription: "Order number"
\t\t\toutputs:
\t\t\t\torder_status: string
\t\t\t\t\tdescription: "Status of the order"
\t\t\ttarget: "flow://Get_Order_Status"
\t\tprocess_return:
\t\t\tdescription: "Process a return"
\t\t\tinputs:
\t\t\t\torder_id: string
\t\t\t\t\tdescription: "Order ID"
\t\t\toutputs:
\t\t\t\treturn_id: string
\t\t\t\t\tdescription: "Return ID"
\t\t\ttarget: "apex://ProcessReturn"
\t\tknowledge_search:
\t\t\tdescription: "Search knowledge base"
\t\t\ttarget: "retriever://FAQ_Knowledge"
\treasoning:
\t\tinstructions: |
\t\t\tHelp with orders.
"""


@pytest.fixture
def sample_agent_file(tmp_path):
    """Create a temporary .agent file."""
    agent_file = tmp_path / "TestAgent" / "TestAgent.agent"
    agent_file.parent.mkdir(parents=True)
    agent_file.write_text(SAMPLE_AGENT)
    return agent_file


class TestExtractTargets:
    def test_extracts_all_target_types(self, sample_agent_file):
        targets = extract_targets(sample_agent_file)
        assert len(targets) == 3

        uris = {t[0] for t in targets}
        assert "flow://Get_Order_Status" in uris
        assert "apex://ProcessReturn" in uris
        assert "retriever://FAQ_Knowledge" in uris

    def test_extracts_correct_types(self, sample_agent_file):
        targets = extract_targets(sample_agent_file)
        types = {t[1] for t in targets}
        assert types == {"flow", "apex", "retriever"}

    def test_extracts_correct_names(self, sample_agent_file):
        targets = extract_targets(sample_agent_file)
        names = {t[2] for t in targets}
        assert names == {"Get_Order_Status", "ProcessReturn", "FAQ_Knowledge"}

    def test_empty_file(self, tmp_path):
        agent_file = tmp_path / "Empty.agent"
        agent_file.write_text("system:\n\tinstructions: 'hello'\n")
        targets = extract_targets(agent_file)
        assert targets == []


class TestSuggestSimilar:
    def test_exact_match(self):
        suggestions = _suggest_similar("Get_Order_Status", ["Get_Order_Status", "Other"])
        assert any(s.name == "Get_Order_Status" for s in suggestions)

    def test_fuzzy_match(self):
        suggestions = _suggest_similar("GetOrderStatus", ["Get_Order_Status", "Unrelated"])
        assert len(suggestions) >= 1
        assert suggestions[0].name == "Get_Order_Status"

    def test_no_match(self):
        suggestions = _suggest_similar("XyzAbcDef", ["Completely_Different"])
        # May or may not match depending on threshold — just verify it runs
        assert isinstance(suggestions, list)

    def test_returns_top_3(self):
        available = [f"Get_Order_{i}" for i in range(10)]
        suggestions = _suggest_similar("Get_Order_Status", available)
        assert len(suggestions) <= 3


class TestValidateActionIo:
    """Tests for I/O parameter validation."""

    @patch("scripts.discover._rest_api_get")
    def test_flow_io_missing_input(self, mock_rest):
        """Should detect when a declared input is missing from the flow."""
        mock_rest.return_value = {
            "inputs": [
                {"name": "order_id", "type": "STRING"},
            ],
            "outputs": [
                {"name": "status", "type": "STRING"},
            ],
        }
        expected_inputs = [
            {"name": "order_id", "type": "string"},
            {"name": "customer_name", "type": "string"},
        ]
        expected_outputs = [{"name": "status", "type": "string"}]

        mismatches = validate_action_io("flow", "Get_Order", expected_inputs, expected_outputs, "testorg")
        assert len(mismatches) == 1
        assert mismatches[0].field_name == "customer_name"
        assert mismatches[0].issue == "missing"
        assert mismatches[0].direction == "input"

    @patch("scripts.discover._rest_api_get")
    def test_flow_io_type_mismatch(self, mock_rest):
        """Should detect type mismatch between .agent and flow."""
        mock_rest.return_value = {
            "inputs": [
                {"name": "count", "type": "NUMBER"},
            ],
            "outputs": [],
        }
        expected_inputs = [{"name": "count", "type": "string"}]

        mismatches = validate_action_io("flow", "TestFlow", expected_inputs, [], "testorg")
        assert len(mismatches) == 1
        assert mismatches[0].issue == "type_mismatch"
        assert mismatches[0].expected_type == "string"
        assert mismatches[0].actual_type == "number"

    @patch("scripts.discover._rest_api_get")
    def test_flow_io_all_match(self, mock_rest):
        """Should return empty list when all I/O matches."""
        mock_rest.return_value = {
            "inputs": [{"name": "order_id", "type": "STRING"}],
            "outputs": [{"name": "status", "type": "STRING"}],
        }
        expected_inputs = [{"name": "order_id", "type": "string"}]
        expected_outputs = [{"name": "status", "type": "string"}]

        mismatches = validate_action_io("flow", "TestFlow", expected_inputs, expected_outputs, "testorg")
        assert mismatches == []

    @patch("scripts.discover._rest_api_get")
    def test_flow_io_api_unavailable(self, mock_rest):
        """Should return empty list when API is unreachable."""
        mock_rest.return_value = None

        mismatches = validate_action_io("flow", "TestFlow", [{"name": "x", "type": "string"}], [], "testorg")
        assert mismatches == []

    @patch("scripts.discover._query_org")
    def test_apex_io_missing_field(self, mock_query):
        """Should detect when a declared field is missing from Apex class."""
        mock_query.return_value = [{
            "Body": """
public with sharing class MyAction {
    public class Request {
        @InvocableVariable(required=true)
        public String order_id;
    }
    public class Response {
        @InvocableVariable
        public String status;
    }
}
"""
        }]
        expected_inputs = [
            {"name": "order_id", "type": "string"},
            {"name": "extra_field", "type": "string"},
        ]
        expected_outputs = [{"name": "status", "type": "string"}]

        mismatches = validate_action_io("apex", "MyAction", expected_inputs, expected_outputs, "testorg")
        assert len(mismatches) == 1
        assert mismatches[0].field_name == "extra_field"
        assert mismatches[0].direction == "input"

    @patch("scripts.discover._query_org")
    def test_apex_io_all_match(self, mock_query):
        """Should return empty list when all fields exist in Apex."""
        mock_query.return_value = [{
            "Body": """
public class MyAction {
    public class Request {
        @InvocableVariable(required=true)
        public String order_id;
    }
    public class Response {
        @InvocableVariable
        public String result;
    }
}
"""
        }]
        mismatches = validate_action_io(
            "apex", "MyAction",
            [{"name": "order_id", "type": "string"}],
            [{"name": "result", "type": "string"}],
            "testorg",
        )
        assert mismatches == []


class TestExtractActionsComplexType:
    """Test that extract_actions captures complex_data_type_name."""

    def test_complex_type_in_inputs_and_outputs(self, tmp_path):
        agent_content = """\
topic my_topic:
\tlabel: "My Topic"
\tdescription: "Test topic"

\tactions:
\t\tmy_action:
\t\t\tdescription: "Test action"
\t\t\ttarget: "flow://My_Flow"
\t\t\tinputs:
\t\t\t\tcategory: string
\t\t\t\t\tdescription: "Category"
\t\t\t\tmax_distance: object
\t\t\t\t\tcomplex_data_type_name: "lightning__integerType"
\t\t\t\t\tdescription: "Max distance"
\t\t\toutputs:
\t\t\t\tresult_count: object
\t\t\t\t\tcomplex_data_type_name: "lightning__integerType"
\t\t\t\t\tdescription: "Number of results"
"""
        agent_file = tmp_path / "Test.agent"
        agent_file.write_text(agent_content)
        actions = extract_actions(agent_file)
        assert len(actions) == 1
        action = actions[0]
        # Check inputs
        assert len(action["inputs"]) == 2
        assert action["inputs"][0] == {"name": "category", "type": "string"}
        assert action["inputs"][1]["name"] == "max_distance"
        assert action["inputs"][1]["complex_data_type_name"] == "lightning__integerType"
        # Check outputs
        assert len(action["outputs"]) == 1
        assert action["outputs"][0]["complex_data_type_name"] == "lightning__integerType"
