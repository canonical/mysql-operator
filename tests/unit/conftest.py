import pytest

@pytest.fixture(autouse=True)
def with_juju_secrets(monkeypatch):
    monkeypatch.setattr("ops.JujuVersion.has_secrets", True)

@pytest.fixture
def without_juju_secrets(monkeypatch):
    monkeypatch.setattr("ops.JujuVersion.has_secrets", False)