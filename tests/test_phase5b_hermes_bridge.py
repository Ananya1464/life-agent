import sys
from pathlib import Path
import pytest
from unittest.mock import Mock, patch

# Add hermes-agent path
sys.path.insert(0, r"C:\Users\Ananya\AppData\Local\hermes\hermes-agent")
# Add src to path so life_agent is importable
sys.path.insert(0, r"D:\life-agent\src")

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
    with patch("tools.registry.registry", MockRegistry()) as mock:
        yield mock

def test_bridge_registration(mock_registry_fixture):
    # Reload the bridge to trigger registration
    import importlib
    import tools.life_agent_bridge
    importlib.reload(tools.life_agent_bridge)

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
