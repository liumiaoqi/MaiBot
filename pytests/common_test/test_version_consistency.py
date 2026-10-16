"""首发门禁：**应用版本在"改版本必须同步的那几处"之间不许矛盾**。

为什么要有它（`gates before code`）：版本号是**一处改、多处跟**的东西，而**没有一处总账**——
今晚就实测过漏：`uv.lock` 停在 `1.0.11`（与 `pyproject.toml` 的 `0.1.0` 不同步）、
`CODE_WIKI.md` 的来源行也还挂着旧版。⇒ 把"义务"变成一条**会红的**门禁，而不是靠人记。

**它查什么**（改应用版本时必须同步的处）：
1. `pyproject.toml` 的 `version`（**唯一真源**）
2. `uv.lock` 里本仓条目（`[[package]] name = "maibot"`）的 `version`
3. `README.md` 的"最新版本"行
4. `changelogs/changelog.md` 的**首条**版本标题
5. `CODE_WIKI.md` 的**来源声明**——⚠️ 它**不是**"等于当前版本"，而是"**必须指向真源**"
   （`#3` 已把它定性为**历史快照**：正文基于 `v1.0.11` 时点生成 ⇒ 改数字=伪造来源，
   所以它只需要**说清自己是历史快照 + 指向 pyproject/changelogs**）

**为什么它红得起来**：核心判据抽成纯函数 `find_version_inconsistencies(facts)`，
配套一条**合成矛盾**用例（把锁里的本仓版本改成别的值）⇒ **必须返回问题**。
（照今晚的纪律：**不许把门禁写成恒真**——`assert … or True` 比没有断言更坏。）
"""

import re
import tomllib
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]

#: 五处里前四处必须**逐字相等**；第五处（CODE_WIKI）只要求**指向真源**
_EQUALITY_FIELDS = ("pyproject", "lock", "readme", "changelog_first")


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def _first_version(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


def collect_facts() -> dict[str, Any]:
    """从真源码/真文档里取出五处的事实（**不做判断**，判断在下面的纯函数里）。"""

    pyproject = tomllib.loads(_read("pyproject.toml"))
    lock_text = _read("uv.lock")
    lock_block = re.search(
        r'\[\[package\]\]\nname = "maibot"\nversion = "([^"]+)"', lock_text
    )
    readme_text = _read("README.md")
    changelog_text = _read("changelogs/changelog.md")
    code_wiki_text = _read("CODE_WIKI.md")

    return {
        "pyproject": pyproject["project"]["version"],
        "lock": lock_block.group(1) if lock_block else None,
        "readme": _first_version(readme_text, r"最新版本:\s*v([0-9][^\s（(]*)"),
        "changelog_first": _first_version(changelog_text, r"^##\s+([0-9][^\s—]*)"),
        "code_wiki_points_to_source_of_truth": bool(
            re.search(r"`?pyproject\.toml`?|`?changelogs/`?", code_wiki_text)
        ),
        "code_wiki_text": code_wiki_text,
    }


def find_version_inconsistencies(facts: dict[str, Any]) -> list[str]:
    """五处对拍；返回问题清单（空 = 一致）。**纯函数 ⇒ 可以喂合成事实证它红得起来。**"""

    problems: list[str] = []

    missing = [f for f in _EQUALITY_FIELDS if not facts.get(f)]
    if missing:
        # 扫不到 = 门禁自己瞎了（**不许当通过**：照今晚"扫描器瞎了"那条）
        return [f"取不到这些版本事实（门禁自己瞎了，不许当通过）: {missing}"]

    baseline = facts["pyproject"]
    for field in _EQUALITY_FIELDS[1:]:
        if facts[field] != baseline:
            problems.append(
                f"{field}={facts[field]!r} 与 pyproject={baseline!r} 不一致"
                f"（改应用版本时必须同步这一处）"
            )

    if not facts.get("code_wiki_points_to_source_of_truth"):
        problems.append(
            "CODE_WIKI.md 的来源声明没有指向真源（应提到 pyproject.toml 或 changelogs/）——"
            "它是历史快照，必须让读者找到当前版本线"
        )

    return problems


# ── 门禁本体 ────────────────────────────────────────────────────────────────


def test_real_repo_versions_are_consistent() -> None:
    """真仓上：五处不矛盾（改版本漏同步 ⇒ 这条红）。"""

    problems = find_version_inconsistencies(collect_facts())

    assert problems == [], "版本不同步：\n" + "\n".join(problems)


def test_gate_sees_the_real_version() -> None:
    """自检：真仓上确实取到了版本（防"取了个空也算过"）。"""

    facts = collect_facts()

    assert facts["pyproject"], f"取不到 pyproject 版本：{facts}"
    assert facts["lock"], f"取不到 uv.lock 里本仓条目的版本：{facts}"


# ── 证红：合成矛盾必须红（这是"门禁有没有用"的唯一硬证据）──────────────────


def _consistent_facts() -> dict[str, Any]:
    """一份**合成的一致**事实（照真仓形状手写，不读文件）。"""

    return {
        "pyproject": "0.1.0",
        "lock": "0.1.0",
        "readme": "0.1.0",
        "changelog_first": "0.1.0",
        "code_wiki_points_to_source_of_truth": True,
        "code_wiki_text": "",
    }


def test_synthetic_consistent_facts_have_no_problems() -> None:
    """反向自检：合成的一致事实**必须**零问题（否则门禁是恒红的，同样没用）。"""

    assert find_version_inconsistencies(_consistent_facts()) == []


def test_gate_goes_red_when_lock_version_diverges() -> None:
    """**证红**：把锁里的本仓版本改成别的值 ⇒ 门禁必须报问题（今晚那个真实漏洞的形状）。"""

    facts = _consistent_facts()
    facts["lock"] = "1.0.11"

    problems = find_version_inconsistencies(facts)

    assert problems, "锁与 pyproject 不同步却没报 —— 门禁是恒真的"
    assert any("lock" in p for p in problems), problems


def test_gate_goes_red_when_readme_or_changelog_diverges() -> None:
    """**证红**：README / changelog 任一处漏同步 ⇒ 必须红。"""

    for field in ("readme", "changelog_first"):
        facts = _consistent_facts()
        facts[field] = "0.0.9"
        problems = find_version_inconsistencies(facts)
        assert any(field in p for p in problems), f"{field} 漏同步没被抓到: {problems}"


def test_gate_goes_red_when_scanner_sees_nothing() -> None:
    """**证红**：扫描面取空 ⇒ 报"门禁自己瞎了"，**不许静默通过**。"""

    facts = _consistent_facts()
    facts["lock"] = None

    problems = find_version_inconsistencies(facts)

    assert problems and "扫描" in problems[0] or "瞎" in problems[0], problems


def test_gate_goes_red_when_code_wiki_loses_the_pointer() -> None:
    """**证红**：CODE_WIKI 不再指向真源 ⇒ 必须红（它是历史快照，读者得能找到版本线）。"""

    facts = _consistent_facts()
    facts["code_wiki_points_to_source_of_truth"] = False

    problems = find_version_inconsistencies(facts)

    assert any("CODE_WIKI" in p for p in problems), problems
