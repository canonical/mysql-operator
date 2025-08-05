# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import Mock, PropertyMock, patch

import pytest
from ops.charm import ActionEvent
from ops.testing import Harness

from charm import MySQLOperatorCharm


class FakeMySQLBackend:
    """Simulates the real MySQL backend, either returning a dict or raising."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    def get_cluster_status(self):
        """Return the preset response or raise the preset error."""
        if self._error:
            raise self._error
        return self._response


@pytest.fixture
def harness():
    """Start the charm so harness.charm exists and peer databag works."""
    h = Harness(MySQLOperatorCharm)
    h.begin()
    return h


def make_event():
    """Create a dummy ActionEvent with spies on set_results() and fail()."""
    evt = Mock(spec=ActionEvent)
    evt.set_results = Mock()
    evt.fail = Mock()
    evt.params = {}  # ensure .params.get() won’t AttributeError
    return evt


def test_get_cluster_status_action_success(harness):
    """On success, the action wraps and forwards the status dict."""
    # Prepare peer-databag so handler finds a cluster-name
    rel = harness.add_relation("database-peers", "database-peers")
    harness.update_relation_data(rel, harness.charm.app.name, {"cluster-name": "my-cluster"})

    # Patch out the MySQL backend to return a known dict
    sample = {"clusterrole": "primary", "status": "ok"}
    fake = FakeMySQLBackend(response=sample)
    with patch.object(MySQLOperatorCharm, "_mysql", new_callable=PropertyMock, return_value=fake):
        evt = make_event()

        # Invoke the action
        harness.charm._get_cluster_status(evt)

        # Expect set_results called once with {'success': True, 'status': sample}
        evt.set_results.assert_called_once_with({"success": True, "status": sample})
        evt.fail.assert_not_called()


def test_get_cluster_status_action_failure(harness):
    """On backend error, the action calls event.fail() and does not set_results()."""
    # Seed peer-databag for cluster-name lookup
    rel = harness.add_relation("database-peers", "database-peers")
    harness.update_relation_data(rel, harness.charm.app.name, {"cluster-name": "my-cluster"})

    # Patch MySQL backend to always raise
    fake = FakeMySQLBackend(error=RuntimeError("boom"))
    with patch.object(MySQLOperatorCharm, "_mysql", new_callable=PropertyMock, return_value=fake):
        evt = make_event()

        # Invoke the action
        harness.charm._get_cluster_status(evt)

        # It should report failure and never set_results
        evt.fail.assert_called_once()
        args, _ = evt.fail.call_args
        assert "Failed to read cluster status" in args[0]

        evt.set_results.assert_not_called()


def test_get_cluster_status_action_none_return(harness):
    """When the backend returns None (no error), the action should fail."""
    rel = harness.add_relation("database-peers", "database-peers")
    harness.update_relation_data(rel, harness.charm.app.name, {"cluster-name": "my-cluster"})

    fake = FakeMySQLBackend(response=None)  # Simulate silent failure
    with patch.object(MySQLOperatorCharm, "_mysql", new_callable=PropertyMock, return_value=fake):
        evt = make_event()
        harness.charm._get_cluster_status(evt)

        evt.fail.assert_called_once_with(
            "Failed to read cluster status. See logs for more information."
        )
        evt.set_results.assert_not_called()
