# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import ops.testing

# Since ops>=1.4 this enables better connection tracking.
# See: More at https://juju.is/docs/sdk/testing#heading--simulate-can-connect
ops.testing.SIMULATE_CAN_CONNECT = True
