import subprocess

import ops
import pytest

juju_version = ops.JujuVersion(
    subprocess.run(
        ["juju", "version"], capture_output=True, check=True, encoding="utf-8"
    ).stdout.split("-")[0]
)

only_with_juju_secrets = pytest.mark.skipif(not juju_version.has_secrets)
only_without_juju_secrets = pytest.mark.skipif(juju_version.has_secrets)
