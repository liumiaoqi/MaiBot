#!/usr/bin/env python3
"""仓库级单一入口 —— build / verify / gen / dev。

为什么存在：仓库原有 8 个 CI workflow，各自装环境、各自写命令，本地没有一条命令能
复现 CI 的全部门禁。加入 Rust 之后这种碎片化会变成主要成本。

三条硬约定：

1. CI 与本地调**同一批 argv**；workflow 只负责装环境，然后调用本脚本。
2. 不经 shell：argv 是显式列表，Windows 与 POSIX 行为一致。
3. 可执行文件找不到时**失败**，不跳过——跳过等于「门禁没跑，却显示通过」，
   与本仓反复出现的静默失效同族。

用法：

    python scripts/task.py verify                    # 全部门禁
    python scripts/task.py verify --only lint,test   # 只跑选中的组
    python scripts/task.py verify --list             # 只列出将执行什么，不跑
    python scripts/task.py build --only web
    python scripts/task.py gen --only contract
    python scripts/task.py dev --only web

产物统一落 `.task-out/`（gitignored）：报告、二进制、快照都在这里，CI 从同一路径上传。
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "mingtang"
OUT = ROOT / ".task-out"

# Rust 侧产物契约：cargo 吐 target/release/*，统一拷到 bin/。
# Python 侧与 Dockerfile 只需要知道 bin/<name>，不需要知道 cargo 的目录布局。
BIN = ROOT / "bin"
RUST_ENGINE = "maibot-config"


@dataclass(frozen=True)
class Step:
    """一条可执行的验证/构建动作。"""

    group: str
    label: str
    argv: tuple[str, ...]
    cwd: Path = ROOT
    why: str = ""
    env: dict[str, str] = field(default_factory=dict)
    capture_to: str = ""
    advisory: bool = False


def _mingtang_env() -> dict[str, str]:
    """清空 NODE_OPTIONS：本机有 NODE_OPTIONS shim，会污染 vite/tsc。"""
    return {"NODE_OPTIONS": ""}


VERBS: dict[str, dict[str, list[Step]]] = {
    "verify": {
        "lint": [
            Step(
                "lint", "ruff check（全仓）",
                ("uv", "run", "ruff", "check", "--output-format=concise"),
                why="静态检查；scripts/ 与 lab/ 的排版类规则已按口径在 pyproject 放宽，"
                    "AI 实验区（scripts/embedding_finetune）独立成项目、不参与",
            ),
        ],
        "i18n": [
            Step("i18n", "i18n 三语键集", ("uv", "run", "python", "scripts/i18n_validate.py"), why="键集不残缺"),
        ],
        "wiring": [
            Step(
                "wiring",
                "N1 接线检查",
                (
                    sys.executable, "scripts/n1_wiring_checker.py",
                    "--scan", "src",
                    "--whitelist", "scripts/.n1_whitelist.json",
                    "--json",
                ),
                why="新模块有生产调用点",
                capture_to="n1_report.json",
            ),
        ],
        "security": [
            Step(
                "security",
                "N4 无认证端点检查",
                (
                    sys.executable, "scripts/n4_security_checker.py",
                    "--scan", "src/webui/routers",
                    "--whitelist", "scripts/.n4_whitelist.json",
                    "--json",
                ),
                why="webui 路由带认证依赖",
                capture_to="n4_report.json",
            ),
        ],
        "contract": [
            Step(
                "contract", "契约一致性（只读快照，不访问后端）",
                ("node", "scripts/contract/cli.mjs", "check", "--source", "snapshot"),
                cwd=WEB, why="前端类型与后端 OpenAPI 不漂移", env=_mingtang_env(),
            ),
        ],
        "test": [
            Step("test", "pytest 全量", ("uv", "run", "pytest"), why="tests/ + pytests/ 双目录"),
        ],
        "web": [
            Step("web", "前端 lint", ("pnpm", "run", "lint"), cwd=WEB, why="eslint", env=_mingtang_env()),
            Step("web", "前端 test", ("pnpm", "run", "test"), cwd=WEB, why="vitest", env=_mingtang_env()),
        ],
    },
    "build": {
        "web": [
            Step(
                "web", "pnpm install（frozen lockfile）",
                ("pnpm", "install", "--frozen-lockfile"),
                cwd=WEB, why="锁文件必须一致，否则构建不可复现", env=_mingtang_env(),
            ),
            Step(
                "web", "前端构建",
                ("pnpm", "run", "build"),
                cwd=WEB, why="tsc -b + vite build；产物 mingtang/dist", env=_mingtang_env(),
            ),
            Step(
                "web", "产物守卫",
                (
                    sys.executable, "-c",
                    "import pathlib, sys; "
                    "p = pathlib.Path('dist/index.html'); "
                    "sys.exit(0) if p.is_file() else sys.exit('缺失 dist/index.html（容器 healthcheck 查的就是它）')",
                ),
                cwd=WEB, why="容器 healthcheck 查 /MaiMBot/mingtang/dist/index.html，缺了镜像就是坏的",
            ),
        ],
        "rust": [
            Step(
                "rust", "配置引擎 release 构建",
                ("cargo", "build", "--release", "-p", RUST_ENGINE),
                why="纯配置引擎（合并/校验/provenance），不连数据库",
            ),
        ],
    },
    "gen": {
        "contract": [
            Step(
                "contract", "重新生成前端类型与快照",
                ("node", "scripts/contract/cli.mjs", "generate"),
                cwd=WEB, why="派生件必须由生成器产出，不进人工编辑", env=_mingtang_env(),
            ),
        ],
        "i18n": [
            Step("i18n", "提取候选键", ("uv", "run", "python", "scripts/i18n_extract_candidates.py"), why="新文案进词表"),
        ],
    },
    "dev": {
        "web": [
            Step("web", "前端开发服务（7999）", ("pnpm", "run", "dev"), cwd=WEB, why="固定端口，避免与后端抢", env=_mingtang_env()),
        ],
        "core": [
            Step("core", "容器重建", ("docker", "compose", "up", "-d", "core"), why="活服务换码"),
        ],
    },
}


def resolve(program: str) -> str:
    """定位可执行文件；找不到就抛错，不静默跳过。"""
    if os.path.isabs(program):
        return program
    path = shutil.which(program)
    if path is None:
        raise FileNotFoundError(
            f"找不到可执行文件 `{program}`。先装它，或确认它在 PATH 上——"
            f"本脚本不会因为缺工具而跳过对应门禁。"
        )
    return path


def prepare(argv: tuple[str, ...]) -> list[str]:
    """把 argv 首项解析成可执行路径。

    Windows 上 `pnpm` 是 `.cmd`，CreateProcess 不能直接执行它（抛 WinError 2），
    必须经 `cmd.exe /c`。只对 `.cmd`/`.bat` 包装，其余平台与可执行文件不受影响。
    """
    exe = resolve(argv[0])
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd.exe", "/c", exe, *argv[1:]]
    return [exe, *argv[1:]]


def expand(verb: str, only: str | None) -> list[Step]:
    """把 --only 展开成待执行步骤；all 表示该动词下全部组。"""
    groups = VERBS[verb]
    if only is None or only.strip() in ("", "all"):
        return [step for steps in groups.values() for step in steps]

    wanted = [name.strip() for name in only.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in groups]
    if unknown:
        available = ", ".join(groups)
        raise SystemExit(f"未知的组 {unknown}；{verb} 可用组：{available}")

    return [step for name in wanted for step in groups[name]]


def describe(verb: str, steps: list[Step]) -> None:
    """只列出将执行什么，用于确认与评审。"""
    print(f"task {verb} → {len(steps)} 步")
    for index, step in enumerate(steps, 1):
        rel = step.cwd.relative_to(ROOT) if step.cwd != ROOT else Path(".")
        print(f"  {index:>2}. [{step.group}] {step.label}")
        print(f"      cwd : {rel}")
        print(f"      cmd : {' '.join(step.argv)}")
        if step.why:
            print(f"      why : {step.why}")


def run_one(step: Step) -> tuple[bool, float]:
    """执行一步，输出直通。返回 (是否成功, 耗时秒)。"""
    started = time.monotonic()
    argv = prepare(step.argv)
    print(f"\n▸ [{step.group}] {step.label}")
    print(f"  $ {' '.join(step.argv)}")
    env = {**os.environ, "PYTHONUNBUFFERED": "1", **step.env}
    OUT.mkdir(parents=True, exist_ok=True)
    if step.capture_to:
        completed = subprocess.run(
            argv, cwd=step.cwd, env=env, check=False, stdout=subprocess.PIPE
        )
        raw = completed.stdout or b""
        target = OUT / step.capture_to
        target.write_bytes(raw)
        print(f"  \u2192 {target.relative_to(ROOT)} ({len(raw)} B)")
        if completed.returncode != 0:
            for line in raw.decode("utf-8", "replace").splitlines()[-50:]:
                print(f"  | {line}")
    else:
        completed = subprocess.run(argv, cwd=step.cwd, env=env, check=False)
    elapsed = time.monotonic() - started
    return completed.returncode == 0, elapsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="task.py",
        description="仓库级单一入口：build / verify / gen / dev。CI 只调这里。",
    )
    parser.add_argument("verb", choices=sorted(VERBS), help="要做的事")
    parser.add_argument(
        "--only",
        default=None,
        help="逗号分隔的组名；省略或 all 表示全部。用 --list 看可用组。",
    )
    parser.add_argument("--list", action="store_true", help="只列出将执行什么，不运行")
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="一步失败后继续（默认 fail-fast）；退出码仍为失败",
    )
    args = parser.parse_args(argv)

    steps = expand(args.verb, args.only)
    if not steps:
        print(f"task {args.verb}：没有可执行的步骤", file=sys.stderr)
        return 1
    if args.list:
        describe(args.verb, steps)
        return 0

    print(f"task {args.verb} · {len(steps)} 步 · 产物目录 {OUT.relative_to(ROOT)}")
    total_started = time.monotonic()
    failures: list[tuple[Step, float]] = []
    advisories: list[tuple[Step, float]] = []
    for step in steps:
        try:
            prepare(step.argv)
        except FileNotFoundError as error:
            print(f"\n✗ [{step.group}] {step.label}\n  {error}", file=sys.stderr)
            failures.append((step, 0.0))
            if not args.keep_going:
                break
            continue
        ok, elapsed = run_one(step)
        if not ok and step.advisory:
            advisories.append((step, elapsed))
            print(f"△ [{step.group}] {step.label} 有告警（advisory，不阻断，{elapsed:.1f}s）", file=sys.stderr)
            continue
        if not ok:
            failures.append((step, elapsed))
            print(f"✗ [{step.group}] {step.label} 失败（{elapsed:.1f}s）", file=sys.stderr)
            if not args.keep_going:
                break

    elapsed_total = time.monotonic() - total_started
    passed = len(steps) - len(failures)
    if failures:
        print(f"\n✗ {passed} passed / {len(failures)} failed · {elapsed_total:.1f}s", file=sys.stderr)
        for step, _ in failures:
            rel = step.cwd.relative_to(ROOT) if step.cwd != ROOT else None
            where = f"cd {rel} && " if rel is not None else ""
            print(f"  复现：{where}{' '.join(step.argv)}", file=sys.stderr)
        return 1

    print(f"\n✓ {passed} passed / 0 failed · {elapsed_total:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
