# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
import dataclasses
import json
import os
from pathlib import Path
from typing import Optional

import pytest
from pytest_operator.plugin import OpsTest


def _get_group_number(function) -> Optional[int]:
    """Gets group number from test function marker.

    This example has a group number of 1:
    @pytest.mark.group(1)
    def test_build_and_deploy():
        pass
    """
    group_markers = [marker for marker in function.own_markers if marker.name == "group"]
    if not group_markers:
        return
    assert len(group_markers) == 1
    marker_args = group_markers[0].args
    assert len(marker_args) == 1
    group_number = marker_args[0]
    assert isinstance(group_number, int)
    return group_number


def _collect_groups(items):
    """Collects unique group numbers for each test module."""

    @dataclasses.dataclass(eq=True, order=True, frozen=True)
    class Group:
        path_to_test_file: str
        group_number: int
        job_name: str

    groups: set[Group] = set()
    for function in items:
        if not (group_number := _get_group_number(function)):
            continue
        # Example: "integration.relations.test_database"
        name = function.module.__name__
        assert name.split(".")[0] == "integration"
        # Example: "tests/integration/relations/test_database.py"
        path_to_test_file = f"tests/{name.replace('.', '/')}.py"
        # Example: "relations/test_database.py | group 1"
        job_name = f"{'/'.join(path_to_test_file.split('/')[2:])} | group {group_number}"
        groups.add(Group(path_to_test_file, group_number, job_name))
    sorted_groups: list[dict] = [dataclasses.asdict(group) for group in sorted(list(groups))]
    output = f"groups={json.dumps(sorted_groups)}"
    print(f"\n\n{output}\n")
    output_file = os.environ["GITHUB_OUTPUT"]
    with open(output_file, "a") as file:
        file.write(output)


def pytest_collection_modifyitems(config, items):
    if config.option.collect_groups:
        _collect_groups(items)
    elif selected_group_number := config.option.group:
        # Remove tests that do not match the selected group number
        filtered_items = []
        for function in items:
            group_number = _get_group_number(function)
            if not group_number:
                function.add_marker(pytest.mark.skip("Missing group number"))
                filtered_items.append(function)
            elif group_number == selected_group_number:
                filtered_items.append(function)
        assert (
            len({function.module.__name__ for function in filtered_items}) == 1
        ), "Only 1 test module can be run if --group is specified"
        items[:] = filtered_items


@pytest.fixture(scope="session")
def mysql_charm_series(pytestconfig) -> str:
    return pytestconfig.option.mysql_charm_series


@pytest.fixture(scope="module")
def ops_test(ops_test: OpsTest, pytestconfig) -> OpsTest:
    if os.environ.get("CI") == "true":
        # Running in GitHub Actions; skip build step
        # (GitHub Actions uses a separate, cached build step. See .github/workflows/ci.yaml)
        packed_charms = json.loads(os.environ["CI_PACKED_CHARMS"])

        async def _build_charm(charm_path, bases_index: int = None) -> Path:
            for charm in packed_charms:
                if Path(charm_path) == Path(charm["directory_path"]):
                    if bases_index is None or bases_index == charm["bases_index"]:
                        return charm["file_path"]
            raise ValueError(f"Unable to find .charm file for {bases_index=} at {charm_path=}")

    else:
        _build_charm = ops_test.build_charm

    async def build_charm(charm_path) -> Path:
        if Path(charm_path) == Path("."):
            # Building mysql charm
            return await _build_charm(
                charm_path,
                bases_index=pytestconfig.option.mysql_charm_bases_index,
            )
        else:
            return await _build_charm(charm_path)

    ops_test.build_charm = build_charm
    return ops_test
