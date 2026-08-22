"""agent_interaction 测试公共 fixture。"""

from unittest.mock import Mock

import pytest

from src.core.adapters.agent_config_port import (
    reset_agent_config_provider,
    set_agent_config_provider,
)
from src.core.app_config_port_registry import (
    reset_app_config_port,
    set_app_config_port,
)
from src.core.protocols import AgentConfigProvider, AppConfigPort, MemoryServicePort
from src.core.types import AgentInteractionSnapshot


@pytest.fixture
def mock_app_config_port():
    """提供 mock AppConfigPort，返回默认 AgentInteractionSnapshot。"""
    port = Mock(spec=AppConfigPort)
    port.get_agent_interaction_config.return_value = AgentInteractionSnapshot()
    set_app_config_port(port)
    yield port
    reset_app_config_port()


@pytest.fixture
def mock_agent_config_provider():
    """提供 mock AgentConfigProvider。"""
    provider = Mock(spec=AgentConfigProvider)
    set_agent_config_provider(provider)
    yield provider
    reset_agent_config_provider()


@pytest.fixture
def mock_memory_port():
    """提供 mock MemoryServicePort。"""
    return Mock(spec=MemoryServicePort)