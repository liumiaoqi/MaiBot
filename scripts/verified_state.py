#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""被验证状态指纹：**生成器 + 机检**（本仓 `gen-*` / `verify-* --check` 形态的第一件）。

## 为什么需要它

`pitfalls #52`：**"被验证状态" = 主仓 SHA ＋ 每个 gitlink 各自指向哪个提交**。
实测依据（写进 `v0.1.0` tag 注释里那段）：同一个主仓 SHA `428c07af2` 配 v1-compat `9d643c0`
⇒ 全量 33 = 基线；配 `61021af` ⇒ **多一条红**。⇒ 只记主仓 SHA 的"验证声明"是**不可复现**的。

而这份指纹此前**只以手写形式存在于 tag 注释里** ⇒ 无法机检、必然腐。本工具把它变成一对：
`--emit` 生成 / `--check` 重算并比对。

## ⭐ 两个问法（**语义不同，别混**）

| 问法 | 基准 | 判不判 | 用途 |
|---|---|---|---|
| **(a) 自洽性** `--check <ref>` | **那个 ref 自己的树**（`rev-parse <ref>^{commit}` ＋ `ls-tree <ref>`） | **判**：不一致 ⇒ 非零退出 | ⭐ **过闸用这条**："这个 tag 承诺了什么、它自己是否说得对"。**好 tag 应当永远绿**。 |
| **(b) 漂移** `--check <ref> --drift` | **当前工作区** | **只报不判**（永远 0） | 给人看："仓在 tag 之后变了什么"。**漂移 ≠ 失败**。 |
| (b′) `--check <文本>` / `--from-file` | 给定文本 vs 当前工作区 | 只报不判；加 `--strict` 才判 | 临时对账（如把 `--emit` 原文回喂）。 |

⚠️ **为什么必须分开**：若只留 (b)，`--check v0.1.0` 在主仓前进后**必然红** ⇒ 造出一个
**永远红的闸**（`#47` 那族：判据自己成为故障源）。**"红"在 (a) 是错误、在 (b) 是报告**。

## 用法

```sh
python scripts/verified_state.py --emit                                       # 生成（粘进 tag 注释）
python scripts/verified_state.py --check v0.1.0                               # (a) 自洽性 —— 过闸
python scripts/verified_state.py --check v0.1.0 --drift                       # (b) 漂移 —— 只报不判
python scripts/verified_state.py --check v0.1.0 --allow-absent .shared,lab    # 外部克隆者：私有子模块取不到
python scripts/verified_state.py --check --from-file fp.txt --strict          # (b′) 判（造红用）
```

退出码：`0` 一致 / 仅漂移 · `1` **不一致**（逐项指出哪一项票）· `2` 用法/解析错误。

## 格式（稳定、可比对、且**能读懂已手写的那份**）

```
⭐ 被验证状态指纹: main <40hex> · .shared <40hex> · lab <40hex> · napcat-adapter <40hex> · v1-compat <40hex>
   分支: main · 工作区: clean
```

- **主仓与每个 gitlink 都给 full 40 位**（手写那份是 7 位缩写 ⇒ 解析**按前缀匹配**，两种都能比；
  升级成 40 位是为消除缩写碰撞的余地）—— **宽进严出**。
- 标签用**短名**（`napcat-adapter` / `v1-compat`）以贴合已手写的那份；解析同时接受完整路径。
- `工作区` 是**内容级**判定 —— **管文件，不管 gitlink**（见 `_content_dirty`）：不用 `git status`
  的字样，因为本仓有 **stat 缓存假脏**（`.gitattributes` 的 `eol=crlf` 会让"检出时物化行尾"被记成改动）。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

#: 指纹行的识别锚（已手写的那份里是 `⭐ 被验证状态指纹（缺一不可）: `）
FINGERPRINT_ANCHOR = "被验证状态指纹"

#: gitlink 短名 → 仓内路径。`main` 特指主仓本身。
GITLINK_LABELS: List[Tuple[str, str]] = [
    ("main", "."),
    (".shared", ".shared"),
    ("lab", "lab"),
    ("napcat-adapter", "plugins/maibot-team.napcat-adapter"),
    ("v1-compat", "plugins/maibot-team.v1-compat"),
]

#: 解析时也接受完整路径写法
_LABEL_ALIASES: Dict[str, str] = {
    "plugins/maibot-team.napcat-adapter": "napcat-adapter",
    "plugins/maibot-team.v1-compat": "v1-compat",
}

_PAIR_RE = re.compile(r"([A-Za-z0-9_./@-]+)\s+([0-9a-fA-F]{7,40})")


class GitError(RuntimeError):
    """git 调用失败 —— **不吞**，让调用方把层级说清楚（脚手架/工具/路径/产品）。"""


def _git(repo: Path, *args: str) -> str:
    """跑一条只读 git 命令，返回 stdout（strip）。失败即抛，不静默兜底。"""
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} 失败（rc={proc.returncode}）：{proc.stderr.strip()[:200]}")
    return proc.stdout.strip()


def _git_bytes(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} 失败（rc={proc.returncode}）")
    return proc.stdout


def resolve_repo_root() -> Path:
    """本脚本所在仓的根（worktree 同样成立：`scripts/verified_state.py` → 上一级）。"""
    return Path(__file__).resolve().parents[1]


def _head_of(repo_root: Path, path: str) -> Optional[str]:
    """**工作区**里 `path` 目录的 HEAD（full 40 位）；不是 git 仓（如未 clone 的子模块）⇒ None。"""
    target = repo_root if path == "." else repo_root / path
    if not (target / ".git").exists():
        return None
    try:
        return _git(target, "rev-parse", "HEAD")
    except GitError:
        return None


def _content_dirty(repo_root: Path, rel: str) -> bool:
    """**内容级**判定：HEAD 里的 blob 与工作区文件，**归一化 CRLF 后**是否不同。

    ⚠️ 判词：**内容级判定管文件，不管 gitlink** —— gitlink（子仓）那一项"变了"= 它的 HEAD 动了，
    那正是**指纹项**要表达的东西，不该在这儿重复计一次脏（否则工作区永远显示 dirty）。

    为什么不用 `git status --porcelain` 的字样：本仓有 stat 缓存假脏 ——
    `.gitattributes` 的 `eol=crlf` 会让"检出时物化行尾"被记成改动，而内容其实没变。
    （同族先例：`docs/pitfalls.md` 那条「判据归一化：比对前 \\r\\n→\\n」。）
    """
    disk = repo_root / rel
    if not disk.exists():
        return True  # 删了 = 真脏
    if disk.is_dir():
        return False  # gitlink：见上「管文件，不管 gitlink」
    try:
        blob = _git_bytes(repo_root, "show", f"HEAD:{rel}")
    except GitError:
        return True  # HEAD 里没有（新文件）⇒ 真脏
    return blob.replace(b"\r\n", b"\n") != disk.read_bytes().replace(b"\r\n", b"\n")


def collect_state(repo_root: Path) -> Dict[str, object]:
    """采集**当前工作区**状态：主仓 SHA / 各 gitlink HEAD / 分支 / 内容级脏文件。"""
    items: List[Tuple[str, Optional[str]]] = [(label, _head_of(repo_root, path)) for label, path in GITLINK_LABELS]

    numstat = _git(repo_root, "diff", "--numstat")
    candidates = [line.split("\t")[-1].strip() for line in numstat.splitlines() if line.strip()]
    dirty = sorted(rel for rel in candidates if _content_dirty(repo_root, rel))

    untracked = [ln for ln in _git(repo_root, "ls-files", "--others", "--exclude-standard").splitlines() if ln.strip()]
    return {
        "items": items,
        "branch": _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": dirty,
        "untracked": len(untracked),
    }


def collect_ref_state(repo_root: Path, ref: str) -> Dict[str, Optional[str]]:
    """**(a) 自洽性用的基准**：`ref` **自己的树**里各 gitlink 记的提交（不是工作区）。

    - `main` → `git rev-parse <ref>^{commit}`
    - 其余 → `git ls-tree <ref> <path>`；gitlink 在 ls-tree 里是 `160000 commit <sha>\\t<path>`。
      ⚠️ 目录型路径要带尾斜杠才列得出其下的 gitlink（`plugins/x` 是逐条目、`plugins/` 才一次列全）。
    """
    out: Dict[str, Optional[str]] = {}
    for label, path in GITLINK_LABELS:
        if path == ".":
            try:
                out[label] = _git(repo_root, "rev-parse", f"{ref}^{{commit}}")
            except GitError:
                out[label] = None
            continue
        sha: Optional[str] = None
        for probe in (path, path + "/", str(Path(path).parent) + "/"):
            try:
                text = _git(repo_root, "ls-tree", ref, probe)
            except GitError:
                continue
            for line in text.splitlines():
                parts = line.split()
                if len(parts) < 4 or parts[0] != "160000":
                    continue
                if parts[3].rstrip("/") == path:
                    sha = parts[2]
                    break
            if sha:
                break
        out[label] = sha
    return out


def render(state: Dict[str, object]) -> str:
    """渲染成**一行指纹 + 一行旁注**（可直接粘进 tag 注释）。"""
    items = state["items"]
    assert isinstance(items, list)
    parts = [f"{label} {sha if sha else 'ABSENT'}" for label, sha in items]
    first = f"⭐ {FINGERPRINT_ANCHOR}: " + " · ".join(parts)
    dirty = state["dirty"]
    assert isinstance(dirty, list)
    workspace = "clean" if not dirty else f"dirty({len(dirty)}): " + ", ".join(dirty[:5]) + ("…" if len(dirty) > 5 else "")
    return f"{first}\n   分支: {state['branch']} · 工作区: {workspace}"


def parse_fingerprint(text: str) -> Dict[str, str]:
    """从任意文本里抽指纹（**能读懂手写的那份**：7 位缩写、短名、`⭐ …（缺一不可）:` 前缀都能认）。

    Returns:
        {短名: 记录的 SHA（可能是缩写）}；找不到指纹行 ⇒ 抛 ValueError（不猜、不兜底）。
    """
    line = next((ln for ln in text.splitlines() if FINGERPRINT_ANCHOR in ln), None)
    if line is None:
        raise ValueError(f"文本里找不到「{FINGERPRINT_ANCHOR}」那一行（搜索范围：整段文本）")
    tail = line.split(FINGERPRINT_ANCHOR, 1)[1]
    found: Dict[str, str] = {}
    for raw_label, sha in _PAIR_RE.findall(tail):
        label = _LABEL_ALIASES.get(raw_label, raw_label)
        if label not in {name for name, _ in GITLINK_LABELS}:
            continue  # 不是我们认得的项（如「（缺一不可）」这类字样），跳过而不是塞进结果
        found[label] = sha
    if not found:
        raise ValueError(f"指纹行里没解析出任何 (标签, SHA) 对；原文：{line.strip()[:160]}")
    return found


def compare(
    expected: Dict[str, str], actual: Dict[str, Optional[str]], allow_absent: Set[str]
) -> Tuple[List[str], List[str]]:
    """逐项比对，返回 (不一致项, 因 --allow-absent 跳过的项)。"""
    problems: List[str] = []
    skipped: List[str] = []

    for label, _path in GITLINK_LABELS:
        want = expected.get(label)
        got = actual.get(label)
        if got is None and label in allow_absent:
            skipped.append(f"{label}（--allow-absent：私有子模块/未补料，取不到）")
            continue
        if want is None:
            problems.append(f"{label}: 指纹里**没有这一项**（实际 {got or 'ABSENT'}）—— 缺项即不一致")
            continue
        if got is None:
            problems.append(f"{label}: 取不到（目录不是 git 仓：未 clone/未补料）⇒ 无法比对；指纹记录 {want}")
            continue
        if not got.lower().startswith(want.lower()):
            problems.append(f"{label}: **票** — 记录 {want} ≠ 实际 {got}")
    return problems, skipped


def _print_table(
    title: str, expected: Dict[str, str], actual: Dict[str, Optional[str]], allow_absent: Set[str]
) -> None:
    print(f"== {title} ==")
    for label, _path in GITLINK_LABELS:
        got = actual.get(label) or "ABSENT"
        want = expected.get(label, "（未记录）")
        if got == "ABSENT" and label in allow_absent:
            mark = "-- "
        else:
            mark = "OK " if want != "（未记录）" and got.lower().startswith(want.lower()) else "!! "
        print(f"  {mark}{label:16s} 记录 {want:42s} 实际 {got}")


def _read_tag_annotation(repo_root: Path, ref: str) -> Optional[str]:
    """取 tag 注释全文（annotated tag）。不是 tag ⇒ None。"""
    try:
        _git(repo_root, "rev-parse", "--verify", f"refs/tags/{ref}")
    except GitError:
        return None
    try:
        return _git(repo_root, "for-each-ref", f"refs/tags/{ref}", "--format=%(contents)")
    except GitError:
        return _git(repo_root, "tag", "-l", "-n99", ref)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="被验证状态指纹：生成与机检（主仓 SHA + 每个 gitlink HEAD）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--emit", action="store_true", help="生成指纹（默认动作）")
    parser.add_argument(
        "--check",
        nargs="?",
        const="",
        default=None,
        metavar="REF|TEXT",
        help="比对：tag 名（默认 (a) 自洽性）/ 指纹文本（(b′) 对当前工作区；裸给时须配 --from-file）",
    )
    parser.add_argument("--from-file", default=None, help="从文件读指纹文本再比对")
    parser.add_argument("--drift", action="store_true", help="(b) 用当前工作区做基准：**只报不判**")
    parser.add_argument("--strict", action="store_true", help="(b)/(b′) 也判（非零退出）—— 造红/临时硬门用")
    parser.add_argument("--allow-absent", default="", help="逗号分隔的标签：取不到即跳过（如 .shared,lab）")
    parser.add_argument("--repo", default=None, help="仓根（默认=本脚本所在仓）")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo).resolve() if args.repo else resolve_repo_root()
    allow_absent: Set[str] = {s.strip() for s in args.allow_absent.split(",") if s.strip()}

    if args.check is None and args.from_file is None:
        args.emit = True

    if args.emit:
        try:
            state = collect_state(repo_root)
        except GitError as exc:
            print(f"[层=脚手架/路径] 采集失败：{exc}\n（仓根={repo_root}）", file=sys.stderr)
            return 2
        print(render(state))
        return 0

    # ---- 比对路径：先定基准与来源 ----
    if args.from_file and args.check:
        print("[层=用法] --check 与 --from-file 只能给一个", file=sys.stderr)
        return 2
    if args.from_file:
        text, source, ref = Path(args.from_file).read_text(encoding="utf-8"), f"文件 {args.from_file}", None
    else:
        assert args.check is not None
        if not args.check:
            print("[层=用法] 裸 --check 须配 --from-file（或给 REF/文本）", file=sys.stderr)
            return 2
        annotation = _read_tag_annotation(repo_root, args.check)
        if annotation is not None:
            text, source, ref = annotation, f"tag {args.check} 的注释", args.check
        else:
            text, source, ref = args.check, "命令行给的指纹文本", None

    try:
        expected = parse_fingerprint(text)
    except ValueError as exc:
        print(f"[层=解析] 比对基准取不到：{exc}", file=sys.stderr)
        print(f"（来源：{source}；文本前 120 字：{text.strip()[:120]!r}）", file=sys.stderr)
        return 2

    # ⭐ 问法选择：(a) 自洽性（基准是 tag 且没要 --drift）/ (b) 漂移（只报不判）
    if ref is not None and not args.drift:
        try:
            actual = collect_ref_state(repo_root, ref)
        except GitError as exc:
            print(f"[层=脚手架/路径] 取 {ref} 的树失败：{exc}", file=sys.stderr)
            return 2
        _print_table(f"(a) 自洽性：{source} vs **该 tag 自己的树**", expected, actual, allow_absent)
        problems, skipped = compare(expected, actual, allow_absent)
        for item in skipped:
            print(f"  -- 跳过：{item}")
        if problems:
            print("\n[红] **这个 tag 的注释与它自己的树不一致**（(a) 口径）——逐项：")
            for item in problems:
                print(f"  · {item}")
            return 1
        print("\n[绿] (a) 自洽性通过：注释与它自己的树逐项一致。")
        return 0

    # (b) / (b′)：基准 vs **当前工作区**
    try:
        state = collect_state(repo_root)
    except GitError as exc:
        print(f"[层=脚手架/路径] 采集失败：{exc}\n（仓根={repo_root}）", file=sys.stderr)
        return 2
    current: Dict[str, Optional[str]] = dict(state["items"])  # type: ignore[arg-type]
    label = "(b) 漂移" if ref is not None else "(b′) 对给定基准"
    _print_table(f"{label}：{source} vs **当前工作区**", expected, current, allow_absent)
    problems, skipped = compare(expected, current, allow_absent)
    for item in skipped:
        print(f"  -- 跳过：{item}")
    if problems:
        print("\n[漂移] 以下项与基准不同 —— ⚠️ **漂移 ≠ 失败**（仓在基准之后变了，属正常报告）：")
        for item in problems:
            print(f"  · {item}")
        if args.strict:
            print("\n[红] 但你给了 --strict ⇒ 按失败计。")
            return 1
        return 0
    print("\n[绿] 无漂移：与基准逐项一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
