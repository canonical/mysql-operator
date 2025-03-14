# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import os
import uuid

import pytest

from . import architecture


@pytest.fixture(scope="session")
def charm():
    # Return str instead of pathlib.Path since python-libjuju's model.deploy(), juju deploy, and
    # juju bundle files expect local charms to begin with `./` or `/` to distinguish them from
    # Charmhub charms.
    return f"./mysql_ubuntu@22.04-{architecture.architecture}.charm"


@pytest.fixture(scope="session")
def cloud_configs_aws() -> tuple[dict[str, str], dict[str, str]]:
    configs = {
        "endpoint": "https://s3.amazonaws.com",
        "bucket": "data-charms-testing",
        "path": f"mysql/{uuid.uuid4()}",
        "region": "us-east-1",
    }
    credentials = {
        "access-key": os.environ["AWS_ACCESS_KEY"],
        "secret-key": os.environ["AWS_SECRET_KEY"],
    }
    return configs, credentials


@pytest.fixture(scope="session")
def cloud_configs_gcp() -> tuple[dict[str, str], dict[str, str]]:
    configs = {
        "endpoint": "https://storage.googleapis.com",
        "bucket": "data-charms-testing",
        "path": f"mysql/{uuid.uuid4()}",
        "region": "",
    }
    credentials = {
        "access-key": os.environ["GCP_ACCESS_KEY"],
        "secret-key": os.environ["GCP_SECRET_KEY"],
    }
    return configs, credentials
