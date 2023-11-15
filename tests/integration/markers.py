# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import importlib.metadata

import ops
import pytest

# libjuju version != juju agent version, but the major version should be identical—which is good
# enough to check for secrets
_libjuju_version = ops.JujuVersion(importlib.metadata.version("juju"))
only_with_juju_secrets = pytest.mark.skipif(not _libjuju_version.has_secrets)
only_without_juju_secrets = pytest.mark.skipif(_libjuju_version.has_secrets)
