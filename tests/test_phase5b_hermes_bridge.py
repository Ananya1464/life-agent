import importlib
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Make life_agent importable without an installed package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
# The bridge lives in a Hermes checkout outside this repo; point HERMES_AGENT_PATH at it
_hermes_path = os.environ.get("HERMES_AGENT_PATH")
if _hermes_path:
    sys.path.insert(0, _hermes_path)


# Mock tools.registry to allow testing the bridge without full hermes environment
class MockRegistry:
    def __init__(self):
        self.registered_tools = []
    def register(self, **kwargs):
        self.registered_tools.append(kwargs)
    def get_all_entries(self):
        return [Mock(name=t['name']) for t in self.registered_tools]

@pytest.fixture
def mock_registry_fixture():
    pytest.importorskip("tools.registry", reason="Hermes not available; set HERMES_AGENT_PATH")
    with patch("tools.registry.registry", MockRegistry()) as mock:
        yield mock

def test_bridge_registration(mock_registry_fixture):
    # Reload the bridge to trigger registration
    bridge = pytest.importorskip("tools.life_agent_bridge", reason="life_agent_bridge not found in Hermes checkout")
    importlib.reload(bridge)

    # Verify registrations occurred in the mock registry
    names = [t['name'] for t in mock_registry_fixture.registered_tools]
    assert "get_recent_activity" in names
    assert "read_vault_note" in names
    assert "list_vault_notes" in names

def test_e2e_grounding():
    # Verify secure path validation is triggered (using actual deterministic_tools)
    from life_agent.tools import deterministic_tools

    # This should raise ValueError due to security validation
    with pytest.raises(ValueError, match="Access denied"):
        deterministic_tools.read_vault_note("../hidden.md")
