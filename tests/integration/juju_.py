# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import importlib.metadata

import ops

# libjuju version != juju agent version, but the major version should be identical—which is good
# enough to check for secrets
has_secrets = ops.JujuVersion(importlib.metadata.version("juju")).has_secrets
