"""Tests for scaffold.py — metadata stub generation."""

import pytest
from pathlib import Path
from scripts.generators.flow_xml import generate_flow_xml
from scripts.generators.apex_stub import generate_apex_class, generate_apex_meta_xml, generate_callout_apex_class, generate_soql_apex_class
from scripts.generators.apex_test_stub import generate_apex_test_class
from scripts.generators.permission_set_xml import generate_permission_set_xml
from scripts.generators.remote_site_xml import generate_remote_site_xml, safe_domain_name
from scripts.scaffold import classify_action


class TestFlowXml:
    def test_basic_flow(self):
        xml = generate_flow_xml("Get_Order_Status")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert "<label>Get Order Status</label>" in xml
        assert "<status>Active</status>" in xml
        assert "<processType>AutoLaunchedFlow</processType>" in xml

    def test_flow_with_inputs(self):
        inputs = [{"name": "order_number", "type": "string", "description": "Order number"}]
        xml = generate_flow_xml("Get_Order_Status", inputs=inputs)
        assert "<name>order_number</name>" in xml
        assert "<isInput>true</isInput>" in xml
        assert "<dataType>String</dataType>" in xml

    def test_flow_with_outputs(self):
        outputs = [{"name": "status", "type": "string"}]
        xml = generate_flow_xml("Get_Order_Status", outputs=outputs)
        assert "<name>status</name>" in xml
        assert "<isOutput>true</isOutput>" in xml

    def test_bidirectional_variable(self):
        """Variables in both inputs and outputs should be merged."""
        inputs = [{"name": "order_id", "type": "string"}]
        outputs = [{"name": "order_id", "type": "string"}, {"name": "status", "type": "string"}]
        xml = generate_flow_xml("TestFlow", inputs=inputs, outputs=outputs)
        # order_id should appear once with isInput=true AND isOutput=true
        assert xml.count("<name>order_id</name>") == 1

    def test_boolean_type_mapping(self):
        outputs = [{"name": "is_active", "type": "boolean"}]
        xml = generate_flow_xml("TestFlow", outputs=outputs)
        assert "<dataType>Boolean</dataType>" in xml
        assert "<booleanValue>false</booleanValue>" in xml

    def test_placeholder_variable_when_no_outputs(self):
        xml = generate_flow_xml("TestFlow")
        assert "<name>placeholder_result</name>" in xml

    def test_complex_type_integer(self):
        """complex_data_type_name should map to correct Flow type."""
        inputs = [{"name": "minPrice", "type": "object", "complex_data_type_name": "lightning__integerType"}]
        xml = generate_flow_xml("TestFlow", inputs=inputs)
        assert "<dataType>Number</dataType>" in xml

    def test_complex_type_currency(self):
        """lightning__currencyType should map to Currency."""
        outputs = [{"name": "total", "type": "object", "complex_data_type_name": "lightning__currencyType"}]
        xml = generate_flow_xml("TestFlow", outputs=outputs)
        assert "<dataType>Currency</dataType>" in xml

    def test_complex_type_number_assignment(self):
        """Number outputs should use numberValue in assignment, not stringValue."""
        outputs = [{"name": "count", "type": "object", "complex_data_type_name": "lightning__integerType"}]
        xml = generate_flow_xml("TestFlow", outputs=outputs)
        assert "<numberValue>0</numberValue>" in xml
        assert "TODO" not in xml.split("<assignmentItems>")[1]


class TestApexStub:
    def test_basic_class(self):
        code = generate_apex_class("GetOrderStatus")
        assert "public with sharing class GetOrderStatus" in code
        assert "@InvocableMethod" in code
        assert "public class Request" in code
        assert "public class Response" in code

    def test_class_with_inputs(self):
        inputs = [{"name": "order_number", "type": "string", "required": True}]
        code = generate_apex_class("GetOrderStatus", inputs=inputs)
        assert "public String order_number;" in code
        assert "@InvocableVariable" in code

    def test_class_with_outputs(self):
        outputs = [{"name": "status", "type": "string"}]
        code = generate_apex_class("GetOrderStatus", outputs=outputs)
        assert "public String status;" in code
        assert "res.status = 'TODO';" in code

    def test_number_type_mapping(self):
        outputs = [{"name": "count", "type": "number"}]
        code = generate_apex_class("TestClass", outputs=outputs)
        assert "public Decimal count;" in code

    def test_method_label(self):
        code = generate_apex_class("GetOrderStatus")
        assert "label='Get Order Status'" in code

    def test_meta_xml(self):
        xml = generate_apex_meta_xml()
        assert "<apiVersion>63.0</apiVersion>" in xml
        assert "<status>Active</status>" in xml

    def test_escape_apex_backslash(self):
        """Backslashes in descriptions should be escaped."""
        inputs = [{"name": "query", "type": "string", "description": "Path like C:\\Users\\test"}]
        code = generate_apex_class("TestClass", inputs=inputs)
        assert "C:\\\\Users\\\\test" in code

    def test_complex_type_integer(self):
        """complex_data_type_name should map to correct Apex type."""
        inputs = [{"name": "minPrice", "type": "object", "complex_data_type_name": "lightning__integerType"}]
        code = generate_apex_class("TestClass", inputs=inputs)
        assert "public Integer minPrice;" in code

    def test_complex_type_double(self):
        """lightning__doubleType should map to Double."""
        outputs = [{"name": "score", "type": "object", "complex_data_type_name": "lightning__doubleType"}]
        code = generate_apex_class("TestClass", outputs=outputs)
        assert "public Double score;" in code


class TestPermissionSetXml:
    def test_basic(self):
        xml = generate_permission_set_xml("Test_Access", ["MyClass"])
        assert "<label>Test_Access</label>" in xml
        assert "<apexClass>MyClass</apexClass>" in xml
        assert "<enabled>true</enabled>" in xml

    def test_multiple_classes(self):
        xml = generate_permission_set_xml("Access", ["ClassA", "ClassB"])
        assert xml.count("<classAccesses>") == 2
        assert "<apexClass>ClassA</apexClass>" in xml
        assert "<apexClass>ClassB</apexClass>" in xml


class TestApexTestStub:
    def test_basic_test_class(self):
        code = generate_apex_test_class("GetOrderStatus")
        assert "@isTest" in code
        assert "private class GetOrderStatusTest" in code
        assert "GetOrderStatus.Request req" in code
        assert "GetOrderStatus.invoke(" in code
        assert "System.assertNotEquals(null, results" in code
        assert "System.assertEquals(1, results.size()" in code

    def test_with_inputs(self):
        inputs = [
            {"name": "order_number", "type": "string"},
            {"name": "count", "type": "number"},
        ]
        code = generate_apex_test_class("GetOrderStatus", inputs=inputs)
        assert "req.order_number = 'test';" in code
        assert "req.count = 1;" in code

    def test_with_outputs(self):
        outputs = [{"name": "status", "type": "string"}]
        code = generate_apex_test_class("GetOrderStatus", outputs=outputs)
        assert "resp.status" in code

    def test_callout_mock(self):
        code = generate_apex_test_class("ExternalApi", is_callout=True)
        assert "HttpCalloutMock" in code
        assert "MockHttpResponse" in code
        assert "Test.setMock(" in code
        assert "res.setStatusCode(200)" in code

    def test_no_callout_mock(self):
        code = generate_apex_test_class("BasicAction", is_callout=False)
        assert "HttpCalloutMock" not in code
        assert "Test.setMock(" not in code

    def test_boolean_input_placeholder(self):
        inputs = [{"name": "is_active", "type": "boolean"}]
        code = generate_apex_test_class("TestClass", inputs=inputs)
        assert "req.is_active = true;" in code

    def test_complex_type_input(self):
        inputs = [{"name": "amount", "type": "object", "complex_data_type_name": "lightning__integerType"}]
        code = generate_apex_test_class("TestClass", inputs=inputs)
        assert "req.amount = 1;" in code


class TestRemoteSiteXml:
    def test_basic_remote_site(self):
        xml = generate_remote_site_xml("api.example.com")
        assert '<?xml version="1.0" encoding="UTF-8"?>' in xml
        assert "<RemotesiteSetting" in xml
        assert "<url>https://api.example.com</url>" in xml
        assert "<isActive>true</isActive>" in xml

    def test_with_description(self):
        xml = generate_remote_site_xml("api.github.com", "GitHub API access")
        assert "<description>GitHub API access</description>" in xml

    def test_default_description(self):
        xml = generate_remote_site_xml("api.example.com")
        assert "Remote site for api.example.com" in xml

    def test_xml_escaping(self):
        xml = generate_remote_site_xml("api.example.com", 'Test <&> "special"')
        assert "&lt;" in xml
        assert "&amp;" in xml
        assert "&gt;" in xml

    def test_safe_domain_name(self):
        assert safe_domain_name("api.github.com") == "api_github_com"
        assert safe_domain_name("my-api.example.co.uk") == "my_api_example_co_uk"
        assert safe_domain_name("simple") == "simple"


class TestCalloutApex:
    def test_callout_class(self):
        code = generate_callout_apex_class("ExternalApi")
        assert "HttpRequest httpReq" in code
        assert "Http http = new Http();" in code
        assert "HttpResponse httpRes" in code
        assert "httpReq.setMethod('GET')" in code
        assert "JSON.deserializeUntyped" in code

    def test_callout_with_endpoint(self):
        code = generate_callout_apex_class("ExternalApi", endpoint_url="https://api.example.com/v1")
        assert "https://api.example.com/v1" in code

    def test_callout_with_inputs_outputs(self):
        inputs = [{"name": "query", "type": "string"}]
        outputs = [{"name": "result", "type": "string"}]
        code = generate_callout_apex_class("SearchApi", inputs=inputs, outputs=outputs)
        assert "public String query;" in code
        assert "public String result;" in code
        assert "res.result = 'TODO';" in code


class TestClassifyAction:
    def test_callout_from_api_keyword(self):
        action = {"name": "fetch_weather", "description": "Call external REST API for weather data"}
        assert classify_action(action) == "callout"

    def test_callout_from_url(self):
        action = {"name": "get_data", "description": "Fetch from https://api.example.com/data"}
        assert classify_action(action) == "callout"

    def test_callout_from_http_keyword(self):
        action = {"name": "http_request", "description": "Make HTTP request to external service"}
        assert classify_action(action) == "callout"

    def test_soql_from_query_keyword(self):
        action = {"name": "get_accounts", "description": "Query Account records"}
        assert classify_action(action) == "soql"

    def test_soql_from_sobject_keyword(self):
        action = {"name": "find_cases", "description": "Look up Case SObject records"}
        assert classify_action(action) == "soql"

    def test_basic_default(self):
        action = {"name": "process_data", "description": "Process the input data"}
        assert classify_action(action) == "basic"

    def test_callout_takes_priority(self):
        """Callout should win over SOQL when both signals present."""
        action = {"name": "get_external", "description": "Query external API for records"}
        assert classify_action(action) == "callout"

    def test_empty_description(self):
        action = {"name": "do_something", "description": ""}
        assert classify_action(action) == "basic"


class TestSoqlApex:
    def test_soql_class_has_query(self):
        inputs = [{"name": "customer_id", "type": "string"}]
        outputs = [{"name": "history_json", "type": "string"}]
        code = generate_soql_apex_class("GetHistory", inputs, outputs,
            description="Query Contact records for history")
        assert "SELECT Id" in code
        assert "FROM Contact" in code
        assert "WHERE Id != null" in code
        assert "Suggested WHERE: customer_id = :req.customer_id" in code
        assert "WITH USER_MODE" in code
        assert "LIMIT 100" in code

    def test_soql_class_infers_sobject(self):
        code = generate_soql_apex_class("GetOrders",
            description="Query Order and OrderItem records")
        assert "FROM Order" in code

    def test_soql_class_fallback_sobject(self):
        code = generate_soql_apex_class("DoSomething",
            description="Do something generic")
        assert "FROM SObject" in code

    def test_soql_class_custom_object(self):
        code = generate_soql_apex_class("GetWidgets",
            description="Query Widget__c records")
        assert "FROM Widget__c" in code

    def test_soql_with_multiple_inputs(self):
        inputs = [
            {"name": "part_number", "type": "string"},
            {"name": "dealer_code", "type": "string"},
        ]
        code = generate_soql_apex_class("LookupParts", inputs,
            description="Query Product2 for parts")
        assert "Suggested WHERE: part_number = :req.part_number AND dealer_code = :req.dealer_code" in code

    def test_soql_has_invocable_method(self):
        code = generate_soql_apex_class("GetHistory",
            description="Query Case records")
        assert "@InvocableMethod" in code
        assert "public class Request" in code
        assert "public class Response" in code


class TestDescriptionPassthrough:
    def test_basic_class_with_description(self):
        code = generate_apex_class("MyAction", description="Do the thing")
        assert "description='Do the thing'" in code

    def test_basic_class_no_description(self):
        code = generate_apex_class("MyAction")
        assert "description='TODO: Add description'" in code

    def test_callout_class_with_description(self):
        code = generate_callout_apex_class("MyCallout", description="Call the API")
        assert "description='Call the API'" in code

    def test_soql_class_with_description(self):
        code = generate_soql_apex_class("MyQuery", description="Query Account records")
        assert "description='Query Account records'" in code
