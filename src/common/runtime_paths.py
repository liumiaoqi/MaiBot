"""运行期数据根路径的**唯一来源**。

## 为什么容器与宿主的 `data/` 根**本来就不同**（这不是 bug，是部署形状）

同一份代码在两个 `PROJECT_ROOT` 下跑，`data/` 落在两个地方：

| 场景 | `PROJECT_ROOT` | `data/` 实际落在哪 | 怎么来的 |
|---|---|---|---|
| 容器 `maim-bot-core` | `/MaiMBot` | `/MaiMBot/data` | `docker-compose.yml:50` 把宿主 `./data/MaiMBot` 挂到 `/MaiMBot/data` |
| 宿主直跑 `bot.py` | `<仓根>` | `<仓根>/data` | 没有挂载，就是仓根下的 `data/` |

⇒ 容器那侧背后是 **`data/MaiMBot/`（生产库 30 MB）**，宿主那侧是仓根 `data/`（空壳 + 一份旁路副本）。
**两者不该被"统一成一个路径"** —— 统一会把容器的生产库指丢。

## 真正要修的是"根**各推各的**"

过去这个根由每个调用点自己推：

- `src/common/database/database.py:27` 用 `Path(__file__).parents[3]` 推一遍；
- `src/maisaka/deepseek/cost_tracker.py:19` 用 **`Path("data/deepseek_cost.db")`（相对 CWD）** 又推一遍。

于是"宿主跑一次 `bot.py` 就在仓根建起第二套库"这件事，**没有任何一处代码能负责**——
两个调用点各自算出来的路径可以不一致（相对路径随 CWD 变），而且没有任何地方能回答
"这次的 data 根到底是什么、是谁定的"。

本模块把它收敛成**一处**：

    MAIBOT_DATA_DIR（环境变量，显式覆盖，最高优先）
        ↓ 未设时
    resolve_project_root() / "data"      ← 全仓唯一的 `__file__` 推导，只写在本文件里

> ⚠️ **同族还有一批"自己推 data 根"的调用点**（`src/webui/routers/system.py:69`、
> `src/emoji_system/emoji_manager.py:35`、`src/chat/image_system/image_manager.py:23`、
> `src/prompt/prompt_manager.py:20`、`src/A_memorix/paths.py:23` 等，实测约 18 处）。
> 它们今天**恰好都能推出同一个仓根**，所以没有立刻出错；但它们是**未经对账的副本**。
> 收敛它们属独立一批（机械替换 `PROJECT_ROOT = ...parents[N]` → `resolve_data_root()`），
> **本模块只负责把"唯一来源"先立起来**，不在这批里顺手改它们。

## 宿主侧是**显式**的

`resolve_host_side_alternate_root()` 会认出"宿主侧"这个形态：当前 data 根下**还有一个
`MaiMBot/` 子目录** —— 那正是容器挂成 `/MaiMBot/data` 的生产数据（容器内**不存在**这个子目录）。
`database.py` 用它发一条 WARNING，写明"你正在用的是哪个根、生产库在哪、怎么切过去"。

**为什么不做硬失败**：宿主直跑是日常开发路径，**测试也全在宿主跑**——
硬失败会让整套测试与本地开发直接不可用。⇒ 按派发单给的两个选项，这里选"**留下清楚的说明**"。
"""

import os
from pathlib import Path

__all__ = [
    "DATA_DIR_ENV",
    "resolve_project_root",
    "resolve_data_root",
    "resolve_data_file",
    "resolve_host_side_alternate_root",
    "describe_data_root",
]

#: 数据根的环境变量覆盖名（显式来源；未设时才回落到仓根推导）
DATA_DIR_ENV = "MAIBOT_DATA_DIR"

#: 仓根下 data 目录的名字
_DATA_DIRNAME = "data"

#: 容器里被挂载的生产数据目录名 —— 它只会在**宿主侧**的 data 根下出现（见模块 docstring）
_HOST_SIDE_MARKER = "MaiMBot"


def resolve_project_root() -> Path:
    """仓根。**全仓唯一的 `__file__` 推导点**，只在本文件里出现。

    本文件在 `src/common/runtime_paths.py` ⇒ 上溯三级到仓根：
    `runtime_paths.py` → `common/` → `src/` → 仓根。
    """
    return Path(__file__).resolve().parents[2]


def resolve_data_root() -> Path:
    """数据根（唯一来源：环境变量 → 仓根推导）。

    Returns:
        Path: 已解析为绝对路径的数据根。容器内是 `/MaiMBot/data`，
        宿主上是 `<仓根>/data`（两者都**与改动前一致**，见模块 docstring 的兼容性说明）。
    """
    override = os.environ.get(DATA_DIR_ENV, "").strip()
    if override:
        candidate = Path(override).expanduser()
        if not candidate.is_absolute():
            # 相对值按"相对仓根"解释 —— 不让它随 CWD 漂
            candidate = resolve_project_root() / candidate
        return candidate.resolve()
    return (resolve_project_root() / _DATA_DIRNAME).resolve()


def resolve_data_file(*parts: str) -> Path:
    """数据根下的文件/子目录（`resolve_data_file("MaiBot.db")`）。

    调用点**不要**自己拼 `"data"` —— 那是旧的"各推各的"写法。
    """
    return resolve_data_root().joinpath(*parts)


def resolve_host_side_alternate_root() -> Path | None:
    """宿主侧特有的信号：当前 data 根下还有一个 `MaiMBot/` 子目录。

    它就是容器（`maim-bot-core`）挂成 `/MaiMBot/data` 的那份**生产数据**
    （`docker-compose.yml:50`）。容器内该子目录**不存在**（实测）。

    Returns:
        Path | None: 存在则返回该目录，否则 None。
    """
    candidate = resolve_data_root() / _HOST_SIDE_MARKER
    return candidate if candidate.is_dir() else None


def describe_data_root() -> str:
    """给日志用的自述串（说明"这次的根是什么、谁定的"）。"""
    override = os.environ.get(DATA_DIR_ENV, "").strip()
    source = f"环境变量 {DATA_DIR_ENV}={override}" if override else "仓根推导（未设 " + DATA_DIR_ENV + "）"
    return f"data 根={resolve_data_root()}（来源：{source}）"
