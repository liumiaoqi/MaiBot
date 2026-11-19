"""节保存端点测试：全合成配置，覆盖类型感知落盘与节级类型纠正。

不读真实配置；所有 tmp_path 自建。
"""

import asyncio
import tomllib
from pathlib import Path
from typing import Any

import pytest
import tomlkit

from src.webui.routers import config as config_router

BOT_CONFIG = '''[inner]
version = "0.9.0"

[bot]
qq_account = "10001"
nickname = "SeamBot"

[personality]
personality = "You are SeamBot."
multiple_reply_style = ["style-one"]

[chat]
max_context_size = 42

[maim_message]
auth_token = ["fake-token"]
enable_api_server = true
api_server_allowed_api_keys = ["fake-key"]

[a_memorix.connectionist]
inner_voices = { welt = [
    { name = "规则甲", style = "direct", focus_concepts = ["概念甲"], weight_multiplier = 1.11 },
    { name = "规则乙", style = "soft", focus_concepts = ["概念乙"], weight_multiplier = 1.22 },
    { name = "规则丙", style = "playful", focus_concepts = ["概念丙"], weight_multiplier = 1.33 },
] }
'''


def _write_config(config_dir: Path) -> Path:
    path = config_dir / "bot_config.toml"
    path.write_text(BOT_CONFIG, encoding="utf-8")
    return path


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _write_config(tmp_path)
    monkeypatch.setattr(config_router, "CONFIG_DIR", str(tmp_path))

    async def _reload(_context: str) -> str:
        return "ok"

    monkeypatch.setattr(config_router, "_reload_config_or_report", _reload)
    return tmp_path


def _save(section_name: str, payload: dict[str, Any]) -> Any:
    return asyncio.run(config_router.update_bot_config_section(section_name, payload))


def _inline_chain(doc: Any, role: str) -> Any:
    inner = doc["a_memorix"]["connectionist"]["inner_voices"]
    assert type(inner).__name__ == "InlineTable"
    rules = inner[role]
    assert type(rules).__name__ == "Array"
    for rule in rules:
        assert type(rule).__name__ == "InlineTable"
    return rules


def _count_comments(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("#"))


def _count_headers(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.lstrip().startswith("["))


def test_a_memorix_section_save_keeps_inline_chain(config_dir: Path) -> None:
    path = config_dir / "bot_config.toml"
    payload = {
        "connectionist": {
            "inner_voices": {
                "welt": [
                    {"name": "新甲", "style": "x", "focus_concepts": ["新一"], "weight_multiplier": 1.41},
                    {"name": "新乙", "style": "y", "focus_concepts": ["新二"], "weight_multiplier": 1.52},
                    {"name": "新丙", "style": "z", "focus_concepts": ["新三"], "weight_multiplier": 1.63},
                ]
            }
        }
    }
    _save("a_memorix", payload)

    text = path.read_text(encoding="utf-8")
    tomllib.loads(text)
    doc = tomlkit.loads(text)
    rules = _inline_chain(doc, "welt")
    assert len(rules) == 3
    assert "welt = name =" not in text


def test_coerce_section_payload_coerces_numeric_and_keeps_unknown(
    config_dir: Path,
) -> None:
    coerced = config_router._coerce_section_payload(
        "webui", {"webui_style": "1"}, config_router.Config
    )
    assert coerced == {"webui_style": 1}
    assert type(coerced["webui_style"]) is int

    untouched = config_router._coerce_section_payload(
        "inner", {"version": "9.9.9"}, config_router.Config
    )
    assert untouched == {"version": "9.9.9"}


def test_comment_and_header_counts_unchanged(config_dir: Path) -> None:
    path = config_dir / "bot_config.toml"
    before = path.read_text(encoding="utf-8")
    _save("a_memorix", {"connectionist": {"inner_voices": {"welt": []}}})
    after = path.read_text(encoding="utf-8")

    assert _count_comments(after) == _count_comments(before)
    assert _count_headers(after) == _count_headers(before)


def test_data_equivalent_except_target(config_dir: Path) -> None:
    path = config_dir / "bot_config.toml"
    before = tomllib.loads(path.read_text(encoding="utf-8"))
    _save("a_memorix", {"connectionist": {"inner_voices": {"welt": []}}})
    after = tomllib.loads(path.read_text(encoding="utf-8"))

    before["a_memorix"]["connectionist"]["inner_voices"]["welt"] = []
    assert after == before


def test_same_payload_twice_is_idempotent(config_dir: Path) -> None:
    path = config_dir / "bot_config.toml"
    payload = {"connectionist": {"inner_voices": {"welt": [{"name": "稳定", "style": "s", "focus_concepts": ["同"], "weight_multiplier": 1.77}]}}}
    _save("a_memorix", payload)
    first = tomllib.loads(path.read_text(encoding="utf-8"))
    _save("a_memorix", payload)
    second = tomllib.loads(path.read_text(encoding="utf-8"))

    assert first == second
    assert len(second["a_memorix"]["connectionist"]["inner_voices"]["welt"]) == 1

MODEL_CONFIG = '''[inner]
version = "0.9.0"

[[api_providers]]
name = "提供商甲"
base_url = "https://example.invalid/a"
api_key = "fake-key-a"
client_type = "openai"
auth_type = "bearer"
auth_header_prefix = "Bearer"
model_list_endpoint = "/models"
timeout = 30
retry_interval = 5
max_retry = 2
organization = "org-a"
project = "proj-a"

[[api_providers]]
name = "提供商乙"
base_url = "https://example.invalid/b"
api_key = "fake-key-b"
client_type = "openai"
auth_type = "bearer"
auth_header_prefix = "Bearer"
model_list_endpoint = "/models"
timeout = 30
retry_interval = 5
max_retry = 2
organization = "org-b"
project = "proj-b"

[[models]]
category = "llm"
name = "模型甲"
model_identifier = "model-a"
api_provider = "提供商甲"
capabilities = ["text_generation"]

[[models]]
category = "llm"
name = "模型乙"
model_identifier = "model-b"
api_provider = "提供商乙"
capabilities = ["text_generation"]

[[models]]
category = "llm"
name = "模型丙"
model_identifier = "model-c"
api_provider = "提供商甲"
capabilities = ["text_generation"]

[model_task_config.replyer]
model_list = ["模型甲"]
max_tokens = 2048
temperature = 0.5
'''


@pytest.fixture
def model_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "model_config.toml").write_text(MODEL_CONFIG, encoding="utf-8")
    monkeypatch.setattr(config_router, "CONFIG_DIR", str(tmp_path))

    async def _reload(_context: str) -> str:
        return "ok"

    monkeypatch.setattr(config_router, "_reload_config_or_report", _reload)
    return tmp_path


def test_model_section_save_keeps_aot(model_config_dir: Path) -> None:
    path = model_config_dir / "model_config.toml"
    before_headers = _count_headers(path.read_text(encoding="utf-8"))

    providers = tomllib.loads(path.read_text(encoding="utf-8"))["api_providers"]
    asyncio.run(config_router.update_model_config_section("api_providers", providers))

    text = path.read_text(encoding="utf-8")
    tomllib.loads(text)
    doc = tomlkit.loads(text)
    assert type(doc["models"]).__name__ == "AoT"
    assert len(doc["models"]) == 3
    assert len(doc["api_providers"]) == 2
    assert _count_headers(text) == before_headers


def test_model_list_replace_keeps_aot(model_config_dir: Path) -> None:
    path = model_config_dir / "model_config.toml"
    models = tomllib.loads(path.read_text(encoding="utf-8"))["models"]
    asyncio.run(config_router.update_model_config_section("models", models))

    text = path.read_text(encoding="utf-8")
    tomllib.loads(text)
    doc = tomlkit.loads(text)
    assert type(doc["models"]).__name__ == "AoT"
    assert len(doc["models"]) == 3


def test_full_bot_save_keeps_inline_chain(config_dir: Path) -> None:
    path = config_dir / "bot_config.toml"
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    asyncio.run(config_router.update_bot_config(payload))

    text = path.read_text(encoding="utf-8")
    tomllib.loads(text)
    doc = tomlkit.loads(text)
    _inline_chain(doc, "welt")