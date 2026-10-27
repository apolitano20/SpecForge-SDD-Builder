"""Tests for ard.schemas: the Architect's strict structured-output SDD schema."""

import json

import pytest
from pydantic import ValidationError

from ard.schemas import SDD


class TestSDDSchema:
    def test_valid_response_parses(self, valid_sdd_dict):
        sdd = SDD.model_validate(valid_sdd_dict)
        assert sdd.project_name == "todo-api"

    def test_dump_by_alias_keeps_from_key(self, valid_sdd_dict):
        dumped = SDD.model_validate(valid_sdd_dict).model_dump(by_alias=True)
        flow = dumped["context"]["information_flows"][0]
        assert flow["from"] == "EndUser"
        assert "from_" not in flow

    def test_dump_round_trips_to_input(self, valid_sdd_dict):
        dumped = SDD.model_validate(valid_sdd_dict).model_dump(by_alias=True)
        assert json.loads(json.dumps(dumped)) == valid_sdd_dict

    def test_invalid_component_type_rejected(self, valid_sdd_dict):
        valid_sdd_dict["components"][0]["type"] = "Interface"
        with pytest.raises(ValidationError):
            SDD.model_validate(valid_sdd_dict)

    def test_invalid_actor_type_rejected(self, valid_sdd_dict):
        valid_sdd_dict["context"]["external_actors"][0]["type"] = "robot"
        with pytest.raises(ValidationError):
            SDD.model_validate(valid_sdd_dict)

    def test_invalid_http_method_rejected(self, valid_sdd_dict):
        valid_sdd_dict["api_endpoints"][0]["method"] = "FETCH"
        with pytest.raises(ValidationError):
            SDD.model_validate(valid_sdd_dict)

    def test_extra_field_rejected(self, valid_sdd_dict):
        valid_sdd_dict["components"][0]["owner"] = "team-a"
        with pytest.raises(ValidationError):
            SDD.model_validate(valid_sdd_dict)

    def test_missing_field_rejected(self, valid_sdd_dict):
        del valid_sdd_dict["components"][0]["file_path"]
        with pytest.raises(ValidationError):
            SDD.model_validate(valid_sdd_dict)

    def test_json_schema_is_strict_compatible(self):
        """Every object forbids extra keys and requires all of its properties."""
        schema = SDD.model_json_schema(by_alias=True)

        def check(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    assert node.get("additionalProperties") is False
                    assert set(node["required"]) == set(node["properties"])
                for value in node.values():
                    check(value)
            elif isinstance(node, list):
                for value in node:
                    check(value)

        check(schema)
