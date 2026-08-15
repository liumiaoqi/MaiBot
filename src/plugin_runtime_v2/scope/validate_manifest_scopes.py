"""发布端 manifest scopes 校验工具（ZG16-5 模块 A）。

纯逻辑静态校验 + Tier 1 高危操作正则检测 + CLI 入口。
不修改 manifest、不加载插件、不执行插件代码（spec 5.1.1 规则 7）。
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from src.plugin_runtime_v2.scope.vocabulary import ScopeVocabulary


@dataclass(frozen=True)
class ValidateResult:
    """manifest scopes 校验结果。"""

    ok: bool
    missing_scopes: list[str] = field(default_factory=list)
    invalid_scopes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class Tier1Detector:
    """Tier 1 高危操作静态检测器——扫描插件代码中的关键调用模式。

    基于正则文本扫描，不做 AST 分析（保持 < 100ms，design 2.4.1）。
    """

    # 检测规则表（可配置）：正则模式 → 对应 Tier 1 scope
    _DETECTION_RULES: dict[str, str] = {
        r"subprocess\.(run|Popen|call|check_output|check_call)": "system:execute:cli",
        r"os\.system\(": "system:execute:cli",
        r"os\.popen\(": "system:execute:cli",
        r"asyncio\.create_subprocess_exec": "system:execute:cli",
        r"pyautogui\.screenshot": "system:read:screenshot",
        r"ImageGrab\.grab": "system:read:screenshot",
        r"mss\.grab": "system:read:screenshot",
        r"exifread.*GPS|GPSInfo": "system:read:location",
        r"geopy|Nominatim": "system:read:location",
        r"qzone|qq_zone|qqzone|签到": "account:execute:operation",
        r"qr_code|qrcode|收款码": "finance:read:qr_code",
        r"urllib\.request\.urlopen|requests\.get|httpx\.get|aiohttp.*get": "network:fetch:url",
    }

    @classmethod
    def detect(cls, plugin_code_path: str, rules: dict[str, str] | None = None) -> list[str]:
        """静态扫描插件代码，返回检测到的 Tier 1 scope 列表（去重 + 排序）。

        Args:
            plugin_code_path: 插件代码目录路径。
            rules: 自定义检测规则（正则 → scope），None 时用默认 _DETECTION_RULES。

        Returns:
            去重排序后的 Tier 1 scope 列表。

        Raises:
            FileNotFoundError: plugin_code_path 不存在。
        """
        code_dir = Path(plugin_code_path)
        if not code_dir.exists():
            raise FileNotFoundError(f"插件代码目录不存在: {plugin_code_path}")

        active_rules = rules if rules is not None else cls._DETECTION_RULES
        detected: set[str] = set()

        for py_file in code_dir.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                # 不可读文件 → 跳过继续其他（design 2.4.1）
                continue
            for pattern, scope in active_rules.items():
                if re.search(pattern, content):
                    detected.add(scope)

        return sorted(detected)


def validate_manifest_scopes(
    manifest: dict | str,
    *,
    plugin_code_path: str | None = None,
) -> ValidateResult:
    """校验 manifest scopes 声明完整性 + Tier 1 静态检测。

    Args:
        manifest: manifest dict 或 manifest 文件路径。
        plugin_code_path: 插件代码目录路径（用于 Tier 1 静态检测）；
            None 时跳过 Tier 1 检测（仅校验 scope 合法性）。

    Returns:
        ValidateResult（ok/missing_scopes/invalid_scopes/errors）。
    """
    errors: list[str] = []

    # 1. 解析 manifest
    if isinstance(manifest, str):
        manifest_path = Path(manifest)
        if not manifest_path.exists():
            return ValidateResult(ok=False, errors=[f"manifest 文件不存在: {manifest}"])
        try:
            raw = manifest_path.read_text(encoding="utf-8")
            manifest_dict = json.loads(raw)
        except (OSError, UnicodeDecodeError) as e:
            return ValidateResult(ok=False, errors=[f"manifest 格式损坏: {e}"])
        except json.JSONDecodeError as e:
            return ValidateResult(ok=False, errors=[f"manifest 格式损坏: {e}"])
    else:
        manifest_dict = manifest

    if not isinstance(manifest_dict, dict):
        return ValidateResult(ok=False, errors=["manifest 格式损坏: 顶层不是 JSON 对象"])

    # 2. 提取 scopes（缺失或空时不阻断，spec 5.1.3 场景 3）
    scopes = manifest_dict.get("scopes", [])
    if not isinstance(scopes, list):
        return ValidateResult(ok=False, errors=["manifest 格式损坏: scopes 不是列表"])

    # 3. 校验 scope 合法性
    invalid_scopes = [s for s in scopes if not ScopeVocabulary.validate(s)]

    # 4. Tier 1 静态检测
    missing_scopes: list[str] = []
    if plugin_code_path is not None:
        try:
            detected = Tier1Detector.detect(plugin_code_path)
        except FileNotFoundError as e:
            return ValidateResult(ok=False, errors=[f"Tier 1 检测失败: {e}"])
        except Exception as e:
            return ValidateResult(ok=False, errors=[f"Tier 1 检测失败: {e}"])
        # 5. 比对缺失
        missing_scopes = [s for s in detected if s not in scopes]

    # 6. ok 判定
    ok = not invalid_scopes and not missing_scopes and not errors

    return ValidateResult(ok=ok, missing_scopes=missing_scopes, invalid_scopes=invalid_scopes, errors=errors)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：argparse 解析 → 调 validate_manifest_scopes → 格式化输出 → 设置退出码。

    退出码：0=通过, 1=校验失败, 2=错误（manifest 不存在/格式损坏/检测器失败）
    """
    parser = argparse.ArgumentParser(description="校验插件 manifest scopes 声明完整性")
    parser.add_argument("manifest", help="manifest 文件路径")
    parser.add_argument("--code", help="插件代码目录路径（Tier 1 静态检测）", default=None)
    parser.add_argument("--json", dest="as_json", action="store_true", help="JSON 格式输出（机器可读）")
    parser.add_argument("--human", dest="as_human", action="store_true", help="人可读文本输出（默认）")
    args = parser.parse_args(argv)

    result = validate_manifest_scopes(args.manifest, plugin_code_path=args.code)

    # errors 非空 → 退出码 2；ok=False → 退出码 1；ok=True → 退出码 0
    if result.errors:
        exit_code = 2
    elif not result.ok:
        exit_code = 1
    else:
        exit_code = 0

    # 输出格式：--json 优先，默认 --human
    if args.as_json:
        print(json.dumps({
            "ok": result.ok,
            "missing_scopes": result.missing_scopes,
            "invalid_scopes": result.invalid_scopes,
            "errors": result.errors,
        }, ensure_ascii=False))
    else:
        # --human（人可读文本，含中文说明）
        if result.ok:
            print("校验通过：manifest scopes 声明完整。")
        else:
            if result.missing_scopes:
                print(f"缺失 Tier 1 scope: {result.missing_scopes}")
            if result.invalid_scopes:
                print(f"不合法 scope: {result.invalid_scopes}")
            if result.errors:
                print(f"错误: {result.errors}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())