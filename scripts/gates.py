#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命名门集：quick / full / docs —— 每档一条命令，失败即停。

## 为什么有它

路线图 P1（`.agents/notes/proposed/process/2026-10-17-dsh-alignment-roadmap.md`）：
本仓的验收命令是散的（ruff / 目标 pytest / 全量 pytest / `verified_state.py --check`），
"该跑哪几条、按什么顺序、哪条属于快速档"只存在于人脑。本脚本把它们变成**文件**：
一条门 = 一行名字 + 一条命令；档 = 有序门列表；失败即停；退出码非零。

形态学 dsh 的 `scripts/run-gates.ts`（命名 aggregate + 单一 runner），但**不抄它的检查表**：
本仓 CI 主力是 Python，用 Python 跑门，少一层 TS 工具链。

## 三档

```sh
python scripts/gates.py quick              # 提交前：目标 < 2 分钟
python scripts/gates.py full               # 发布前：全量 pytest，判「新增失败 = 0」；末尾打印指纹
python scripts/gates.py docs [--ref REF]   # 文档/生成物：verified_state.py --check（默认 v0.1.0）
python scripts/gates.py quick --dry-run    # 只列门表，不执行（也用于自检"一条门一行"）
```

## full 的通过条件：新增失败 = 0（不是 "0 failed"）

`full` 跑完双目录全量后，把**本次失败集合**与**已知基线**
（`C:\\hub\\.scratch\\current_failures.txt`，**只读**）做集合差，至少打印三行：

```
基线 33 条
本次 33 条
新增 0 / 消失 0
```

**只有「新增 X」> 0 才非零**；X=0 时即使「本次 M」> 0 也 exit 0。「消失 Y」只报告，不判红。

记账口径：**已知基线 33 条（两族：`test_token_budget` / `test_token_estimator`），见
`current_failures.txt`，非本次引入**。

为什么不是 "0 failed"：

- 否则 `full` **永远** exit 1 ⇒ 又是一个"从第一天起就红的门"（`#47` 那族）；
- 这本来就是我们手工反复在做的事（逐条比对、报"新增 0 / 缺失 0"）⇒ 该把它写成工具，
  而不是人肉流程。

## 如实声明

- **`uv run ruff check`（全仓）在本仓从来就不是绿的**：`main` `322023712` 实测红 **1208 条**
  （1049 在 `scripts/embedding_finetune/` 隔离实验区；159 在 `src/tests/pytests/scripts`），
  不是本档引入的。**本季所有"ruff 干净"都是逐文件口径**——这句话必须带范围
  （哪几个文件 / 全仓），否则就是"账目会腐"。所以 quick 只查「本次改动文件」，
  并在档首显式打印「本档不含」。
- **quick 不含全量 pytest / 前端三绿**：前者归 full，后者尚未接入 Python 门（P2/P3 再说）。
- **full 的指纹**在测试全量跑完后打印；失败时也打印（记录"跑的是什么状态"，便于复现），
  但它不是一道门，不改变"失败即停"对**门**的语义。
- **full 的指纹在 worktree 里 `.shared`/`lab` = ABSENT**（gitlink 未 materialize）⇒
  **发布验收必须在主 checkout 跑**；worktree 里的 full 只用于改门/自测。
- **full 实测：本机 2m43s / 3m17s**；早前那几次 **~20 分钟**是在**八个成员同时压这台机**
  时跑的 ⇒ 两个数都记，标「环境差异，不构成趋势」（跨时刻只做趋势）。
- **docs 的 TODO** 是显式占位：P3 才补各生成物的 `--check`；现在不塞没做的事。
"""

import argparse
import hashlib
import re
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: full 档的已知失败基线：中枢账本，**只读**（本脚本从不写它；判据是「新增失败」）。
BASELINE_PATH = Path(r"C:\hub\.scratch\current_failures.txt")

#: 记账口径（写进 full 档输出；改基线文件时同步改这里，否则账目会腐）。
BASELINE_NOTE = (
    "已知基线 33 条（两族：test_token_budget / test_token_estimator），"
    "见 current_failures.txt，非本次引入"
)

#: pytest 短摘要里的失败/错误行：`FAILED <nodeid> - <原因>`；原因可含 " - "，只切第一个。
#: ⚠️ 已知边界：nodeid 自己若含 " - "（罕见：带空格的参数化 id）会被误切。
FAIL_LINE = re.compile(r"^(?:FAILED|ERROR)\s+(?P<nodeid>\S.*?)(?:\s+-\s+.*)?$")

#: quick 档的「如实声明」——砍掉的条目必须写在这里，不许沉默。
QUICK_CUTS = (
    "全仓 ruff —— 从来不是绿的：main 322023712 实测红 1208 条（1049 在"
    " scripts/embedding_finetune，159 在 src/tests/pytests/scripts；非本档引入）"
    " ⇒ 本档只查本次改动文件（逐文件口径）；「ruff 干净」必须带范围（哪几个文件 / 全仓）",
    "全量 pytest（归 full 档）",
    "前端 lint / test / build（本仓 Python 门暂未接）",
)

#: 不归主仓 ruff 管的路径：AI 实验区（自己的 uv/规则）与外部仓（4 个 gitlink：.shared / lab / 两个 plugins）。
RUFF_OUTSIDE_PREFIXES = (
    "scripts/embedding_finetune/",
    "lab/",
    "plugins/",
    ".shared/",
)

#: quick 的「件 A」目标：插件兼容桥接件的 (甲)/(乙) 单测三例。
#: ⚠️ 任务书写的「件 A」在本仓文本里没有逐字出处；按 e2e 用例注释里自己写的
#: "单测层（(甲)(乙) 3 例）"取：本地面两跳 / 上游在场反向对照 / adapter 契约。
#: 三条都是纯单测（不起子进程、不连 TCP），实测 ~1.5s；跨进程 e2e 留给 full。
PLUGIN_COMPAT_CASES = (
    "tests/plugin_runtime_v2/test_legacy_compat_loader.py::"
    "test_hop1_and_hop2_use_local_face_when_upstream_is_absent",
    "tests/plugin_runtime_v2/test_legacy_compat_loader.py::"
    "test_upstream_present_never_touches_local_face",
    "tests/plugin_runtime_v2/test_legacy_compat_loader.py::"
    "test_local_adapter_forwards_lifecycle_and_exposes_runner_contract",
)


@dataclass(frozen=True)
class Gate:
    """一道门：名字 + 一条命令（+ 一句说明，打印给人看）。"""

    name: str
    command: tuple[str, ...]
    what: str = ""


def _display(command: tuple[str, ...]) -> str:
    """把 argv 渲染成一条可读命令（Windows 参数用 list2cmdline 的引号规则）。"""
    return subprocess.list2cmdline(list(command))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    """跑一条只读 git 命令（调用方自己判 returncode，不在这里吞错）。"""
    return subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def changed_python_files() -> list[str]:
    """工作区相对 HEAD 的改动 + 未跟踪文件里的 `.py`（提交前门要查的那批）。

    排除 `RUFF_OUTSIDE_PREFIXES`：外部仓有各自的规则，主仓 ruff 配置不是它们的判据。
    解析 `git status --porcelain -z`（NUL 分隔，路径带空格也安全）；
    重命名/复制条目会多一个原路径字段，要一并跳过。
    """
    proc = _git("status", "--porcelain", "-z")
    if proc.returncode != 0:
        print(f"[层=脚手架/路径] git status 失败（rc={proc.returncode}）：{proc.stderr.strip()[:200]}")
        return []

    paths: list[str] = []
    fields = proc.stdout.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if not entry:
            continue
        status, path = entry[:2], entry[3:]
        if status[0] in "RC" or status[1] in "RC":
            index += 1  # 重命名/复制：下一字段是原路径，不是新条目
        if not path.endswith(".py"):
            continue
        if path.startswith(RUFF_OUTSIDE_PREFIXES):
            continue
        paths.append(path)
    return sorted(set(paths))


def quick_gates() -> list[Gate]:
    """提交前档：改动文件 ruff + 目标套（件 A 三条 / A_memorix 单元 / 关系反馈）。"""
    changed = changed_python_files()
    gates: list[Gate] = []
    if changed:
        gates.append(
            Gate(
                name="ruff (changed files)",
                command=("uv", "run", "ruff", "check", *changed),
                what=f"本次改动 {len(changed)} 个 .py（提交前口径）",
            )
        )
    else:
        # 没有改动就没东西可 lint；这道门不跑（不是失败），但要出声。
        print("[quick] ruff 门跳过：本次无改动 .py（不是失败）", flush=True)
    gates.extend(
        [
            Gate(
                name="plugin-runtime-v2 / 件A (3 cases)",
                command=("uv", "run", "pytest", "-q", *PLUGIN_COMPAT_CASES),
                what="(甲)/(乙) 单测三例：本地面两跳 / 上游在场反向对照 / adapter 契约",
            ),
            Gate(
                name="a-memorix unit",
                command=("uv", "run", "pytest", "tests/unit/a_memorix", "-q"),
                what="A_memorix 单元面（236 passed 量级，实测 ~11s）",
            ),
            Gate(
                name="a-memorix relation-feedback",
                command=("uv", "run", "pytest", "pytests/A_memorix_test/test_v5_relation_feedback.py", "-q"),
                what="0004 关系反馈的 pytest 侧（3 passed 量级，实测 ~2s）",
            ),
        ]
    )
    return gates


def full_gates() -> list[Gate]:
    """发布前档：双目录全量；判据是「新增失败 = 0」（集合差，基线只读）。

    `--tb=line`：33 条已知失败每次全打 traceback 是噪声；新失败有 nodeid + 一行位置，
    够定位，细看再单跑该 nodeid。
    """
    return [
        Gate(
            name="pytest tests pytests (delta vs baseline)",
            command=("uv", "run", "pytest", "tests", "pytests", "-q", "--tb=line"),
            what=(
                "双目录全量，只判「新增失败」；基线见 current_failures.txt（只读）；"
                "本机 2m43s / 3m17s（~20 分钟那几次是八成员同压：环境差异，不构成趋势）"
            ),
        ),
    ]


def docs_gates(ref: str) -> list[Gate]:
    """文档/生成物档：verified_state 自洽性（(a) 口径：比 tag 自己的树）。"""
    return [
        Gate(
            name=f"verified-state ({ref})",
            command=(sys.executable, "scripts/verified_state.py", "--check", ref),
            what="(a) 自洽性：tag 注释 vs 它自己的树（好 tag 应当永远绿）",
        ),
    ]


def _normalize_nodeid(nodeid: str) -> str:
    """统一成 pytest 的 `/` 分隔 nodeid（Windows 下 pytest 打印的是反斜杠）。"""
    return nodeid.strip().replace("\\", "/")


def load_baseline(path: Path) -> tuple[set[str], int, str]:
    """读已知失败基线（**只读**）。返回 (nodeid 集合, 字节数, sha256 前 12 位)。

    空行与 `#` 注释行跳过；集合口径（重复行只算一条）。sha256 打进输出：
    事后能证明「这次比的是哪一份账本」，也便于发现账本被悄悄改过。
    """
    data = path.read_bytes()
    text = data.decode("utf-8-sig")
    known = {
        _normalize_nodeid(line)
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return known, len(data), hashlib.sha256(data).hexdigest()[:12]


def parse_failed_nodeids(output: str) -> set[str]:
    """从 pytest 的 `short test summary info` 里取 FAILED/ERROR 的 nodeid 集合。"""
    failed: set[str] = set()
    for raw in output.splitlines():
        match = FAIL_LINE.match(raw)
        if match:
            failed.add(_normalize_nodeid(match.group("nodeid")))
    return failed


def run_pytest_capture(command: tuple[str, ...]) -> tuple[int, str]:
    """跑 pytest：输出**同时**透传到终端与收集（不静默 3 分钟，也不整段缓冲）。"""
    proc = subprocess.Popen(
        list(command),
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    stdout = proc.stdout
    if stdout is None:  # 理论上不会：PIPE 已给
        return proc.wait(), ""
    collected: list[str] = []
    for line in stdout:
        collected.append(line)
        sys.stdout.write(line)
        sys.stdout.flush()
    return proc.wait(), "".join(collected)


def execute_command(gate: Gate) -> tuple[bool, int]:
    """默认执行器：原样跑命令，exit 0 才算过（quick / docs）。"""
    proc = subprocess.run(list(gate.command), cwd=str(REPO_ROOT))
    return proc.returncode == 0, proc.returncode


def full_executor(baseline_path: Path) -> Callable[[Gate], tuple[bool, int]]:
    """full 档执行器：跑全量 pytest → 与基线做集合差 → **只有「新增失败」判红**。

    绿：新增 0（哪怕本次仍有 M 条已知失败，或消失 Y 条）；
    红：新增 > 0；pytest 退出码不是 0/1（运行坏了）；解析不出失败行但 pytest 报失败。
    """

    def execute(gate: Gate) -> tuple[bool, int]:
        try:
            known, size, digest = load_baseline(baseline_path)
        except OSError as exc:
            print(
                f"  [层=事实层] 基线读不到：{baseline_path}（{exc}）"
                "⇒ 无法判「新增失败」，按失败处理（不许拿空基线假装全绿）",
                flush=True,
            )
            return False, 2

        print(f"  [full] 记账口径：{BASELINE_NOTE}", flush=True)
        print(
            f"  [full] 基线文件：{baseline_path}（只读；{len(known)} 条 / {size} 字节 / "
            f"sha256:{digest}）",
            flush=True,
        )
        try:
            exit_code, output = run_pytest_capture(gate.command)
        except FileNotFoundError as exc:
            print(f"  pytest 命令不存在：{exc}", flush=True)
            return False, 127

        current = parse_failed_nodeids(output)
        new = current - known
        gone = known - current
        print(f"基线 {len(known)} 条", flush=True)
        print(f"本次 {len(current)} 条", flush=True)
        print(f"新增 {len(new)} / 消失 {len(gone)}", flush=True)

        if new:
            print(f"  [红] 新增失败 {len(new)} 条（full 的判据就是这行非零）：", flush=True)
            for nodeid in sorted(new)[:20]:
                print(f"    + {nodeid}", flush=True)
            if len(new) > 20:
                print(f"    …（其余 {len(new) - 20} 条略；本次 pytest 输出里有全量）", flush=True)
        if gone:
            print(f"  [注] 基线里这 {len(gone)} 条本次没再失败（消失只报告，不判红）：", flush=True)
            for nodeid in sorted(gone)[:10]:
                print(f"    - {nodeid}", flush=True)
            if len(gone) > 10:
                print(f"    …（其余 {len(gone) - 10} 条略）", flush=True)

        if exit_code not in (0, 1):
            print(f"  [红] pytest exit {exit_code}（不是 0/1）⇒ 运行本身坏了，集合差不可信", flush=True)
            return False, exit_code
        if exit_code == 1 and not current:
            print("  [红] pytest 报了失败，但输出里解析不出 FAILED/ERROR 行 ⇒ 解析口径失效", flush=True)
            return False, 1
        if new:
            return False, 1
        return True, 0

    return execute


def run_gate(
    index: int,
    total: int,
    gate: Gate,
    execute: Callable[[Gate], tuple[bool, int]],
) -> tuple[bool, int, float]:
    """跑一道门；返回 (是否通过, 退出码, 耗时秒)。"""
    # flush：门的输出是子进程直接写 stdout 的；不先落盘，管道/日志里会出现
    # "子进程输出在前、门名字在后"的错序（实测 docs 档就这么错过一次）。
    print(f"[{index}/{total}] {gate.name}  ::  $ {_display(gate.command)}", flush=True)
    if gate.what:
        print(f"          {gate.what}", flush=True)
    started = time.perf_counter()
    try:
        passed, code = execute(gate)
    except FileNotFoundError as exc:
        elapsed = time.perf_counter() - started
        print(f"          FAILED（命令不存在：{exc}）")
        return False, 127, elapsed
    elapsed = time.perf_counter() - started
    if not passed:
        print(f"          FAILED (exit {code}, {elapsed:.1f}s)", flush=True)
        return False, code, elapsed
    print(f"          OK ({elapsed:.1f}s)", flush=True)
    return True, 0, elapsed


def run_tier(
    tier: str,
    gates: list[Gate],
    execute: Callable[[Gate], tuple[bool, int]],
) -> int:
    """按顺序跑一道档的门；第一道失败即停，返回进程退出码。"""
    if tier == "quick":
        print("[quick] 本档不含：", flush=True)
        for cut in QUICK_CUTS:
            print(f"  - {cut}", flush=True)
        print()

    started = time.perf_counter()
    for position, gate in enumerate(gates, start=1):
        passed, code, _elapsed = run_gate(position, len(gates), gate, execute)
        if not passed:
            remaining = ", ".join(item.name for item in gates[position:])
            print(f"\n[{tier}] STOP at gate {position}/{len(gates)}: {gate.name}（exit {code}）", flush=True)
            if remaining:
                print(f"[{tier}] 未运行：{remaining}", flush=True)
            return code

    total = time.perf_counter() - started
    print(f"\n[{tier}] PASS（{len(gates)} 道门，{total:.1f}s）", flush=True)
    return 0


def emit_fingerprint() -> int:
    """full 的末尾产物：调 `verified_state.py --emit` 打印被验证状态指纹（pitfalls #52）。"""
    print("\n[full] 被验证状态指纹（pitfalls #52 的默认产物；失败时也打印，用于复现）", flush=True)
    proc = subprocess.run(
        [sys.executable, "scripts/verified_state.py", "--emit"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        print(f"  [红] verified_state.py --emit 失败（rc={proc.returncode}）：{proc.stderr.strip()[:400]}", flush=True)
        return 1
    for line in proc.stdout.rstrip().splitlines():
        print(f"  {line}", flush=True)
    if "ABSENT" in proc.stdout:
        print(
            "  ⚠️ 有 gitlink 在工作区取不到（worktree 常见：.shared/lab 未 materialize）⇒ ABSENT；"
            "它们的 pin 仍在 git ls-tree HEAD 里。**发布验收必须在主 checkout 跑**。",
            flush=True,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="命名门集：quick / full / docs（每档一条命令，失败即停）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python scripts/gates.py quick\n"
            "  python scripts/gates.py full\n"
            "  python scripts/gates.py docs --ref v0.1.0\n"
            "  python scripts/gates.py full --baseline <临时副本>   # 合成「少一条」验证能红\n"
        ),
    )
    parser.add_argument("tier", choices=("quick", "full", "docs"), help="要跑的档")
    parser.add_argument("--ref", default="v0.1.0", help="docs 档的比对基准（默认 v0.1.0）")
    parser.add_argument(
        "--baseline",
        default=str(BASELINE_PATH),
        help=f"full 档的已知失败基线（只读；默认 {BASELINE_PATH}；验证能红请用临时副本，别改账本）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印门表，不执行")
    args = parser.parse_args(argv)

    if args.tier == "quick":
        gates = quick_gates()
    elif args.tier == "full":
        gates = full_gates()
    else:
        gates = docs_gates(args.ref)

    if args.dry_run:
        print(f"== {args.tier} ==")
        for position, gate in enumerate(gates, start=1):
            print(f"[{position}/{len(gates)}] {gate.name}  ::  $ {_display(gate.command)}")
        if args.tier == "full":
            print(f"# 基线：{args.baseline}（集合差：新增 > 0 才非零；基线只读）")
            print(f"# 记账：{BASELINE_NOTE}")
        if args.tier == "docs":
            print("# TODO(P3): 各生成物的 --check（pitfalls 编号连续性 / 两仓镜像表 / legacy_face_surface.json）")
        return 0

    if args.tier == "full":
        code = run_tier("full", gates, full_executor(Path(args.baseline)))
        fingerprint_code = emit_fingerprint()
        return code or fingerprint_code

    code = run_tier(args.tier, gates, execute_command)
    if args.tier == "docs":
        print(
            "# TODO(P3): 各生成物的 --check（pitfalls 编号连续性 / 两仓镜像表 / "
            "legacy_face_surface.json）——占位，未做不假装"
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
