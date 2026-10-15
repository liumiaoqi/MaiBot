"""3 段 · 密钥引用化：**写回守卫**的回归测试（lead 那一半，配 `raw_api_key_of`）。

守的是这条命门：``${VAR}`` 的解析在 ``APIProvider.model_post_init`` 里**就地改写**，
配置对象里存的是**解析后的明文**；而 ``write_config_to_file`` 会在"版本升级/钩子命中"时
**用这个对象回写文件** ⇒ 不管的话，任何一次 ``MODEL_CONFIG_VERSION`` 提升都会把
``api_key = "${MAIBOT_TEST_KEY}"`` **静默换成明文**，密钥外部化白做。

⚠️ **两条必须按生产形态调**（`override_repr=True`）：`main.py:67` 与 `config.py:360` 都用 True，
模板里**会**带 `api_key`。默认的 `override_repr=False` 会让该字段（`repr=False`）整键不进模板，
于是"谁都不覆盖它"⇒ 测试**假绿**（herta 2026-10-16 实测指出，本文件已按此重写）。

三种情形：

1. **盘上是引用、生产形态写回** ⇒ 写回后**仍是引用**（回放以盘上原文为准，明文绝不落盘）；
2. **盘上是明文** ⇒ 照常写（无差别，守卫不插手）；
3. **盘上是引用但取不到原文** ⇒ **拒绝写出并出声**（``ConfigWriteRefusedError``），文件未动。
   ⚠️ 这一态**正常生产构造不可达**（见该测试 docstring），是防御分支，如实标注。

夹具一律用假值；配置文件写在 ``tmp_path``，活配置一个字节都不碰。

---

**4 段（解析时机归位）之后的补充（本文件末尾两组）**：解析从 ``model_post_init`` 挪到了
"注入客户端之前"，对象里存的**就是盘上原文** ⇒ 上面三种情形里的 ①② 现在是"两条路都通"，
而守卫本身**不再被触发**。本文件因此加两条：

- ``TestVersionUpgradeEndToEnd``：**真造一次版本升级**（生产路径 ``load_config_from_file``，
  文件版本填低一档）⇒ 断言盘上仍是 ``${VAR}``、明文不进文件、升级本身成功（不抛拒绝异常）；
- ``TestGuardStaysDormant``：把"守卫不再触发"变成**有输出的判据**——直接跑采集/回放两步，
  断言采集件为空（旧实现下同输入必产出 1 条，这是"根因已除"与"守卫被绕过"的分界）。
"""

import os
from pathlib import Path
from typing import Any

import tomlkit
import pytest

from src.config import config as config_module
from src.config.config import (
    ConfigWriteRefusedError,
    MODEL_CONFIG_VERSION,
    ModelConfig,
    load_config_from_file,
    write_config_to_file,
)
from src.config.model_configs import APIProvider, ModelInfo

FAKE_ENV_NAME = "MAIBOT_TEST_WRITEBACK_KEY"
FAKE_SECRET = "sk-fake-writeback-0001"

MODEL_CONFIG_TEMPLATE = """\
[inner]
version = "{version}"

[[models]]
name = "probe-model"
model_identifier = "probe-model"
api_provider = "probe"

[[api_providers]]
name = "probe"
base_url = "https://example.invalid/v1"
api_key = "{api_key}"
auth_type = "bearer"
"""


class _SkippingProvider(APIProvider):
    """**跳过解析路径**的 provider（故意不调 super）——用来造"取不到 raw"那一态。

    ``model_construct`` 不足以造这一态：实测它**仍会**触发 ``model_post_init``，
    raw 照样留下。类体里不加别的方法（``AttrDocBase`` 的字段说明提取只放行
    ``model_post_init`` 与 ``@field_validator`` / ``@model_validator``），故不定义别的。
    """

    def model_post_init(self, context: Any = None) -> None:
        pass  # noqa: PIE790 -- 故意留空：模拟"对象未经 model_post_init 构造"


def _write_config(tmp_path: Path, api_key_value: str) -> Path:
    """把一份最小 model_config 写到临时目录（只含守卫关心的字段）。"""
    config_path = tmp_path / "model_config.toml"
    config_path.write_text(
        MODEL_CONFIG_TEMPLATE.format(version=MODEL_CONFIG_VERSION, api_key=api_key_value),
        encoding="utf-8",
    )
    return config_path


def _api_key_line(config_path: Path) -> str:
    """取文件里 api_key 那一行的值（裸值，便于断言）。"""
    for line in config_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("api_key") and "=" in stripped:
            return stripped.split("=", 1)[1].split("#", 1)[0].strip().strip('"')
    raise AssertionError("配置里找不到 api_key 行")


def test_reference_on_disk_is_kept_on_production_write(tmp_path: Path) -> None:
    """情形①（生产形态）：盘上是引用 ⇒ 写回后仍是引用，明文绝不落盘。

    ⚠️ **4 段按归位后的口径改写过**：旧判据 ``assert 内存里 == 明文`` 现在**反转**成
    "内存里也是引用"——解析不再发生在加载期。反转之后本条守的东西不变
    （盘上引用必须活下来），但"它为什么活下来"变了：不再靠守卫回放，而是**根本没有那个差**。
    守卫仍在位且仍被调用（``test_collect_returns_nothing_after_relocation`` 钉住它"不触发"）。
    """
    os.environ[FAKE_ENV_NAME] = FAKE_SECRET
    try:
        config_path = _write_config(tmp_path, f"${{{FAKE_ENV_NAME}}}")

        # 走生产读取路径：对象里存的是**盘上原文**（归位后不再就地解析）
        config, _updated = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)
        assert config.api_providers[0].api_key == f"${{{FAKE_ENV_NAME}}}"  # 内存里就是引用

        # ⚠️ 生产形态：main.py:67 / config.py:360 都用 override_repr=True
        write_config_to_file(config, config_path, MODEL_CONFIG_VERSION, override_repr=True)

        assert _api_key_line(config_path) == f"${{{FAKE_ENV_NAME}}}", "引用被明文覆盖了"
        assert FAKE_SECRET not in config_path.read_text(encoding="utf-8"), "明文进了文件"
    finally:
        os.environ.pop(FAKE_ENV_NAME, None)


def test_reference_survives_when_template_omits_the_field(tmp_path: Path) -> None:
    """情形①-b：``override_repr=False``（模板里没有该字段）⇒ 引用同样要活下来。

    这一支靠的是 `_merge_config_template` 的"表数组逐项合并"（不吃模板里没有的键），
    与回放守卫是两条独立的保护；本条把这条也钉住（免得日后有人把合并改回整体替换）。
    """
    os.environ[FAKE_ENV_NAME] = FAKE_SECRET
    try:
        config_path = _write_config(tmp_path, f"${{{FAKE_ENV_NAME}}}")
        config, _updated = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

        write_config_to_file(config, config_path, MODEL_CONFIG_VERSION)

        assert _api_key_line(config_path) == f"${{{FAKE_ENV_NAME}}}", "字段被模板跳过时引用没保住"
        assert FAKE_SECRET not in config_path.read_text(encoding="utf-8")
    finally:
        os.environ.pop(FAKE_ENV_NAME, None)


def test_literal_on_disk_is_written_unchanged(tmp_path: Path) -> None:
    """情形②：盘上是明文 ⇒ 照常写，守卫不插手。"""
    config_path = _write_config(tmp_path, "sk-fake-literal-0002")

    config, _updated = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)
    write_config_to_file(config, config_path, MODEL_CONFIG_VERSION, override_repr=True)

    assert _api_key_line(config_path) == "sk-fake-literal-0002"
    assert "sk-fake-literal-0002" in config_path.read_text(encoding="utf-8")


def test_missing_raw_refuses_write_and_leaves_file_untouched(tmp_path: Path) -> None:
    """情形③：盘上是引用但取不到原文 ⇒ 拒绝写出，文件一字未动。

    ⚠️ **不可达的防御分支**（如实标注，别当成覆盖）：正常生产构造必然经过
    ``APIProvider.model_post_init`` ⇒ raw 一定留下；能造出这一态的只有"跳过解析路径"的对象
    （本测试用 ``_SkippingProvider``）。守卫留着是为了"万一将来出现第三条拿到解析后对象的写路径"。
    """
    os.environ[FAKE_ENV_NAME] = FAKE_SECRET
    try:
        config_path = _write_config(tmp_path, f"${{{FAKE_ENV_NAME}}}")
        before = config_path.read_bytes()

        provider = _SkippingProvider(
            name="probe",
            base_url="https://example.invalid/v1",
            api_key=FAKE_SECRET,
        )
        # 占位模型要过 ModelConfig.model_post_init 的三条校验（models 非空 / 标识符非空 /
        # api_provider 指向已声明的服务商）——本态只想造"provider 无 raw"，不想顺带触发别的错。
        placeholder_model = ModelInfo.model_construct(
            name="probe-model",
            model_identifier="probe-model",
            api_provider="probe",
        )
        config = ModelConfig.model_construct(models=[placeholder_model], api_providers=[provider])

        with pytest.raises(ConfigWriteRefusedError):
            write_config_to_file(config, config_path, MODEL_CONFIG_VERSION, override_repr=True)

        assert config_path.read_bytes() == before, "被拒绝的写出仍改了文件"
    finally:
        os.environ.pop(FAKE_ENV_NAME, None)


# ── 4 段（解析时机归位）补充：端到端版本升级 + 守卫休眠的证据 ──────────────────

OLDER_VERSION = "1.17.0"
"""比当前 ``MODEL_CONFIG_VERSION`` 低一档 ⇒ 走生产升级改写路径。

⚠️ 别写"当前版本减一"这种算出来的值：它以字符串形态比较，减一在 1.17.10 上会翻车。
低一档的固定串对"要不要触发升级"够用（判据是 ``old < new``）。
"""


def test_version_upgrade_keeps_reference_on_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """**判据③（端到端）**：真触发一次版本升级 ⇒ 盘上仍是 ``${VAR}``。

    与情形①的区别（这是本条的要点）：情形①手动调 ``write_config_to_file``；本条走的是
    **生产入口** ``load_config_from_file``，由它自己判定"文件版本低于当前版本 ⇒ 需要升级"、
    构造对象、回写文件。⇒ 覆盖到"升级"这个**触发条件**，而不只是"回写"这个动作。

    三种失败本用例都能抓到：
      - 明文写回（``FAKE_SECRET in 文件``）——3 段的老洞；
      - 升级被守卫拒绝（``ConfigWriteRefusedError`` 从 ``load_config_from_file`` 冒出来）——
        归位只做一半（对象里是解析值、盘上是引用）时的形态；
      - 升级静默没发生（文件版本没被提升）——"断言选点撞上默认值"型的假绿。
    """
    monkeypatch.setenv(FAKE_ENV_NAME, FAKE_SECRET)
    config_path = _write_config(tmp_path, f"${{{FAKE_ENV_NAME}}}")
    # 把版本戳压到旧版：这才是"升级"的触发条件（不压就只会走"无需升级"的静默分支）
    text = config_path.read_text(encoding="utf-8").replace(MODEL_CONFIG_VERSION, OLDER_VERSION)
    assert f'version = "{OLDER_VERSION}"' in text
    config_path.write_text(text, encoding="utf-8")

    config, updated = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)

    assert updated is True, "版本升级没有发生（判据没打到升级路径上）"
    on_disk = config_path.read_text(encoding="utf-8")
    assert _api_key_line(config_path) == f"${{{FAKE_ENV_NAME}}}", "升级后盘上的引用被换掉了"
    assert FAKE_SECRET not in on_disk, "升级把明文写回了文件"
    assert f'version = "{MODEL_CONFIG_VERSION}"' in on_disk, "版本戳没跟着升"
    # 同轮对照：对象里也是引用（不是明文）——这正是"根因已除"与"守卫救了一次"的分界
    assert config.api_providers[0].api_key == f"${{{FAKE_ENV_NAME}}}"


def test_collect_returns_nothing_after_relocation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """**守卫为何不再触发**：把采集/回放两步直接跑一遍，断言采集件为空。

    守卫的触发条件是 ``on_disk_value != pending_value``（盘上是引用、对象里是别的值）。
    归位之后 ``provider.api_key`` 就是盘上原文 ⇒ 该条件**恒不成立**，采集件恒为空，
    回放自然什么都不做。

    ⚠️ 这条用例的价值在于**给出输出**而不是"看着像没触发"：它打印采集条数与两边的值，
    任何"守卫被绕过/对象里混进了解析值"的回归都会让条数从 0 变 1（旧实现下同输入必为 1）。
    """
    monkeypatch.setenv(FAKE_ENV_NAME, FAKE_SECRET)
    config_path = _write_config(tmp_path, f"${{{FAKE_ENV_NAME}}}")
    config, _ = load_config_from_file(ModelConfig, config_path, MODEL_CONFIG_VERSION)
    with open(config_path, "r", encoding="utf-8") as handle:
        document = tomlkit.load(handle)

    collected = config_module._collect_reference_api_keys(config, document)  # noqa: SLF001 — 判据要打在这两步上
    print(
        f"\n采集件={collected}（盘上={document['api_providers'][0]['api_key']!r}，"
        f"对象里={config.api_providers[0].api_key!r}）"
    )

    assert collected == [], "守卫仍被触发 ⇒ 对象里混进了解析值（归位没做到位）"
    # 回放是纯函数式的：给它空采集件，文档一个字节都不该动
    before = tomlkit.dumps(document)
    config_module._restore_secret_references(config, document, collected, config_path)  # noqa: SLF001
    assert tomlkit.dumps(document) == before
