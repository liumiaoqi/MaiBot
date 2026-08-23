"""ZG16-6a: dump 测试——CLI + 调试端点 + render。

覆盖 design 4.5 全部 11 个场景，spec 8.4 实测验证项（6 项）。
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.plugin_runtime_v2.config.dump import (
    dump_plugin_config_main,
    handle_dump_endpoint,
    main,
    render_config_dump_human,
    render_config_dump_json,
)
from src.plugin_runtime_v2.config.merger import ProvenanceEntry


def test_dump_json_valid():
    """--json 输出合法 JSON（spec 5.5.1 规则 5a）。"""
    result = render_config_dump_json({"port": 3002}, {}, 1)
    parsed = json.loads(result)
    assert parsed["config"]["port"] == 3002


def test_dump_json_contains_revision():
    """JSON 输出包含 revision。"""
    result = render_config_dump_json({"port": 3002}, {}, 5)
    parsed = json.loads(result)
    assert parsed["revision"] == 5


def test_dump_json_contains_provenance():
    """JSON 输出包含 provenance。"""
    provenance = {"port": ProvenanceEntry("base", "config.toml", 10)}
    result = render_config_dump_json({"port": 3002}, provenance, 1)
    parsed = json.loads(result)
    assert parsed["provenance"]["port"]["layer"] == "base"
    assert parsed["provenance"]["port"]["file"] == "config.toml"
    assert parsed["provenance"]["port"]["line"] == 10


def test_dump_human_with_provenance():
    """--human 输出含 provenance 注释（spec 5.5.1 规则 5b）。"""
    provenance = {"port": ProvenanceEntry("global_override", "bot_config.toml", 10)}
    result = render_config_dump_human({"port": 3002}, provenance, 1)
    assert "# 来源: global_override" in result
    assert "port = 3002" in result


def test_dump_human_contains_revision():
    """human 输出包含 revision 注释。"""
    result = render_config_dump_human({"port": 3002}, {}, 7)
    assert "# revision: 7" in result


def test_dump_human_nested_config():
    """human 输出嵌套配置扁平化。"""
    config = {"server": {"port": 3001, "host": "localhost"}}
    result = render_config_dump_human(config, {}, 1)
    assert "server.port = 3001" in result
    assert "server.host = \"localhost\"" in result


def test_dump_human_string_value():
    """human 输出字符串值加引号。"""
    result = render_config_dump_human({"name": "test"}, {}, 1)
    assert "name = \"test\"" in result


def test_dump_human_bool_value():
    """human 输出布尔值。"""
    result = render_config_dump_human({"enabled": True, "disabled": False}, {}, 1)
    assert "enabled = true" in result
    assert "disabled = false" in result


def test_dump_human_list_value():
    """human 输出列表值。"""
    result = render_config_dump_human({"whitelist": ["a", "b"]}, {}, 1)
    assert "whitelist = [\"a\", \"b\"]" in result


def test_dump_json_empty_config():
    """空配置 JSON 输出。"""
    result = render_config_dump_json({}, {}, 0)
    parsed = json.loads(result)
    assert parsed["config"] == {}
    assert parsed["revision"] == 0


async def test_handle_dump_endpoint():
    """handle_dump_endpoint 调用 manager.dump_config。"""
    manager = MagicMock()
    manager.dump_config = AsyncMock(return_value='{"config": {}}')
    result = await handle_dump_endpoint("X", None, "json", manager)
    manager.dump_config.assert_called_once_with("X", None, "json")
    assert result == '{"config": {}}'


async def test_handle_dump_endpoint_human_format():
    """handle_dump_endpoint human 格式。"""
    manager = MagicMock()
    manager.dump_config = AsyncMock(return_value="# revision: 1")
    result = await handle_dump_endpoint("X", None, "human", manager)
    assert "# revision: 1" in result


def test_dump_json_provenance_empty():
    """provenance 为空时 JSON 输出空对象。"""
    result = render_config_dump_json({"port": 3001}, {}, 1)
    parsed = json.loads(result)
    assert parsed["provenance"] == {}


async def test_dump_plugin_config_main_success():
    """dump_plugin_config_main 成功返回 0。"""
    manager = MagicMock()
    manager.dump_config = AsyncMock(return_value="# revision: 1")
    exit_code = await dump_plugin_config_main("X", manager, None, "human")
    assert exit_code == 0


async def test_dump_plugin_config_main_key_error():
    """dump_plugin_config_main 插件未加载返回 2。"""
    manager = MagicMock()
    manager.dump_config = AsyncMock(side_effect=KeyError("X"))
    exit_code = await dump_plugin_config_main("X", manager, None, "human")
    assert exit_code == 2


async def test_dump_plugin_config_main_exception():
    """dump_plugin_config_main 异常返回 2。"""
    manager = MagicMock()
    manager.dump_config = AsyncMock(side_effect=RuntimeError("dump failed"))
    exit_code = await dump_plugin_config_main("X", manager, None, "json")
    assert exit_code == 2


async def test_dump_plugin_config_main_json_format():
    """dump_plugin_config_main json 格式成功。"""
    manager = MagicMock()
    manager.dump_config = AsyncMock(return_value='{"config": {"port": 3001}}')
    exit_code = await dump_plugin_config_main("X", manager, None, "json")
    assert exit_code == 0


async def test_dump_plugin_config_main_default_format():
    """dump_plugin_config_main 默认 human 格式。"""
    manager = MagicMock()
    manager.dump_config = AsyncMock(return_value="# revision: 1")
    exit_code = await dump_plugin_config_main("X", manager)
    assert exit_code == 0
    manager.dump_config.assert_called_once_with("X", None, "human")


def test_main_cli_success():
    """main CLI 入口成功返回 0。"""
    mock_manager = MagicMock()
    mock_manager.dump_config = AsyncMock(return_value="# revision: 1")
    with patch(
        "src.plugin_runtime_v2.bootstrap.get_plugin_config_manager",
        create=True, return_value=mock_manager,
    ):
        exit_code = main(["X", "--human"])
    assert exit_code == 0


def test_main_cli_json_format():
    """main CLI --json 格式。"""
    mock_manager = MagicMock()
    mock_manager.dump_config = AsyncMock(return_value='{"config": {}}')
    with patch(
        "src.plugin_runtime_v2.bootstrap.get_plugin_config_manager",
        create=True, return_value=mock_manager,
    ):
        exit_code = main(["X", "--json"])
    assert exit_code == 0


def test_main_cli_plugin_not_found():
    """main CLI 插件未加载返回 2。"""
    mock_manager = MagicMock()
    mock_manager.dump_config = AsyncMock(side_effect=KeyError("nonexistent"))
    with patch(
        "src.plugin_runtime_v2.bootstrap.get_plugin_config_manager",
        create=True, return_value=mock_manager,
    ):
        exit_code = main(["nonexistent"])
    assert exit_code == 2


def test_main_cli_with_stream():
    """main CLI --stream 参数。"""
    mock_manager = MagicMock()
    mock_manager.dump_config = AsyncMock(return_value="# revision: 1")
    with patch(
        "src.plugin_runtime_v2.bootstrap.get_plugin_config_manager",
        create=True, return_value=mock_manager,
    ):
        exit_code = main(["X", "--stream", "group:123", "--human"])
    assert exit_code == 0
    mock_manager.dump_config.assert_called_once_with("X", "group:123", "human")