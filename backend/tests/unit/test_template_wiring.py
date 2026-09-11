from pathlib import Path

import pytest
import yaml


ROOT_DIR = Path(__file__).resolve().parents[3]
TEMPLATE_PATH = ROOT_DIR / "infrastructure" / "template.yaml"


class CloudFormationLoader(yaml.SafeLoader):
    pass

def construct_cloudformation_tag(loader, tag_suffix, node):
    key = "Ref" if tag_suffix == "Ref" else f"Fn::{tag_suffix}"

    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)

    return {key: value}

CloudFormationLoader.add_multi_constructor("!", construct_cloudformation_tag)


@pytest.fixture(scope="module")
def template():
    with TEMPLATE_PATH.open() as file:
        return yaml.load(file, Loader=CloudFormationLoader)

def function_properties(template, logical_id):
    return template["Resources"][logical_id]["Properties"]

def test_local_bucket_defaults_are_distinct(template):
    parameters = template["Parameters"]

    assert parameters["SnapshotBucketName"]["Default"] == "commandlog-local-snapshots"
    assert parameters["RawBucketName"]["Default"] == "commandlog-local-raw"
    assert parameters["GeneratedBucketName"]["Default"] == "commandlog-local-generated"

def test_scryfall_functions_use_raw_bucket(template):
    for logical_id in ("ScryfallLoadFunction", "ScryfallDownloadFunction"):
        properties = function_properties(template, logical_id)

        variables = properties["Environment"]["Variables"]

        assert variables["RAW_BUCKET"] == { "Ref": "RawBucketName" }

def test_scryfall_permissions_use_raw_bucket(template):
    for logical_id in ("ScryfallLoadFunction", "ScryfallDownloadFunction"):
        properties = function_properties(template, logical_id)

        statements = properties["Policies"][0]["Statement"]

        s3_resources = [
            resource["Fn::Sub"]
            for statement in statements
            for resource in statement.get("Resource", [])
            if isinstance(resource, dict)
            and "Fn::Sub" in resource
            and ":s3:::" in resource["Fn::Sub"]
        ]

        assert any(
            "${RawBucketName}/scryfall/oracle_cards/*"
            in resource
            for resource in s3_resources
        )

def test_commanders_index_path_matches_iam_permission(template):
    properties = function_properties(template, "BuildCommandersIndexFunction")

    key = properties["Environment"]["Variables"]["COMMANDERS_INDEX_KEY"]

    statements = properties["Policies"][0]["Statement"]

    resources = [
        resource["Fn::Sub"]
        for statement in statements
        for resource in statement.get("Resource", [])
        if isinstance(resource, dict)
        and "Fn::Sub" in resource
    ]

    assert key == "data/commanders_index.json"

    assert (
        "arn:${AWS::Partition}:s3:::"
        "${GeneratedBucketName}/data/commanders_index.json"
        in resources
    )

def test_background_automation_state_controls_all_triggers(template):
    parameter = template["Parameters"]["BackgroundAutomationState"]

    assert parameter["Default"] == "ENABLED"
    assert parameter["AllowedValues"] == [
        "ENABLED",
        "DISABLED"
    ]

    load_events = function_properties(template, "ScryfallLoadFunction")["Events"]

    download_events = function_properties(template, "ScryfallDownloadFunction")["Events"]

    commander_events = function_properties(template, "BuildCommandersIndexFunction")["Events"]

    expected_state = {
        "Ref": "BackgroundAutomationState"
    }

    assert (load_events["LatestOracleCardsCreated"]["Properties"]["State"] == expected_state)

    assert (download_events["ScryfallSync"]["Properties"]["State"] == expected_state)

    assert (commander_events["CommandersIndex"]["Properties"]["State"] == expected_state)

def test_data_heavy_functions_have_reasonable_timeout(template):
    for logical_id in (
        "StatsSummaryFunction", 
        "StatsVersionFunction",
        "GetRandomDecksFunction"
    ):
        properties = function_properties(template, logical_id)

        assert properties["Timeout"] >= 10
