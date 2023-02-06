# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
"""Collect charms to build from charmcraft.yaml file(s)"""

import json
import os
import logging
import sys
from pathlib import Path

import yaml


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


logging.basicConfig(level=logging.INFO, stream=sys.stdout)
charms = []
for charmcraft_yaml in Path(".").glob("**/charmcraft.yaml"):
    path = charmcraft_yaml.parent
    charm_name = yaml.safe_load((path / "metadata.yaml").read_text())["name"]
    for index, version in enumerate(get_base_versions(charmcraft_yaml)):
        charms.append(
            {
                "_job_display_name": f"Build {charm_name} charm | {version}",
                "bases_index": index,
                "directory_path": path.as_posix(),
                "file_path": f"local:./{path/charm_name}_ubuntu-{version}-amd64.charm",
            }
        )
logging.info(f"Collected {charms=}")
output_file = os.environ["GITHUB_OUTPUT"]
with open(output_file, "a") as file:
    file.write(f"charms={json.dumps(charms)}")
