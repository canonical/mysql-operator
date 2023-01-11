# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Read charmcraft.yaml and metadata.yaml file(s)."""

import json
import os
from pathlib import Path

import yaml

from tests.integration.integration_constants import SERIES_TO_VERSION


def get_base_versions(path_to_charmcraft_yaml: Path) -> list[str]:
    """Reads Ubuntu versions of bases from charmcraft.yaml.

    Args:
        path_to_charmcraft_yaml: Path to charmcraft.yaml file

    Returns:
        List of Ubuntu versions (e.g. ["20.04", "22.04"])
    """
    bases = yaml.safe_load(path_to_charmcraft_yaml.read_text())["bases"]
    # Handle multiple bases formats
    # See https://discourse.charmhub.io/t/charmcraft-bases-provider-support/4713
    versions = [base.get("build-on", [base])[0]["channel"] for base in bases]
    return versions


def get_charm_name(path_to_metadata_yaml: Path) -> str:
    """Reads charm name from metadata.yaml.

    Args:
        path_to_metadata_yaml: Path to metadata.yaml

    Returns:
        Charm name from metadata.yaml
    """
    return yaml.safe_load(path_to_metadata_yaml.read_text())["name"]


def create_build_matrix():
    """Create build matrix from charmcraft.yaml file(s).

    Called by GitHub Actions (see .github/workflows/ci.yaml)
    """
    build_matrix = []
    version_to_series = {version: series for series, version in SERIES_TO_VERSION.items()}
    for charmcraft_yaml in Path(".").glob("**/charmcraft.yaml"):
        for index, version in enumerate(get_base_versions(charmcraft_yaml)):
            build_matrix.append(
                {
                    "name": get_charm_name(charmcraft_yaml.parent / "metadata.yaml"),
                    "series": version_to_series[version],
                    "bases_index": index,
                    "path": charmcraft_yaml.parent.as_posix(),
                }
            )
    output_file = os.environ["GITHUB_OUTPUT"]
    with open(output_file, "a") as file:
        file.write(f"build_matrix={json.dumps(build_matrix)}")
