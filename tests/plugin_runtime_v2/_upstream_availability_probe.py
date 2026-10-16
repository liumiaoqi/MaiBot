"""判据 ⑦ 的探针：**"上游在/不在仍可分辨"**（钉住"选 B"的核心理由）。

为什么要有它
------------
`adapter-hop` 这条路（本地面按**路径**取、**不挂** `maibot_sdk.compat` 命名空间）的核心理由是：
*"兜底面不能冒充上游命名空间——否则 `upstream_available()` 这类探测会拿到我们自己的实现 = 自己骗自己"*。
后人为省事把它改回"挂命名空间"时**不会有任何症状**（插件照样加载成功）⇒ 必须有一条钉子。

为什么在**子进程**里跑
--------------------
调用方（pytest 进程）已经 import 过 `maibot_sdk.compat`，`sys.modules` 里有真模块 ⇒ 在那里
毒不出干净的"上游缺席"态。子进程里两态各问一次，答案才是可分辨的。

输出：一行 JSON 到 stdout（`upstream_absent` 是**结论**字段，调用方断言它）。
用法：`python _upstream_availability_probe.py <legacy_face.py 的绝对路径>`
"""

import importlib.util
import json
import sys
from pathlib import Path


def _load_face(face_file: Path):
    """按**路径**装本地面（与宿主 `plugin_loader._local_face_attr` 同法）。"""

    spec = importlib.util.spec_from_file_location("_probe_face", face_file)
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法建立本地面 spec：{face_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    face_file = Path(sys.argv[1]).resolve()
    face = _load_face(face_file)

    # 态一：上游**在场**（本机 venv 里 maibot_sdk 装着）⇒ 必须 True（否则"上游在"也认不出来）。
    upstream_present = face.upstream_available()

    # 态二：合成"上游缺席"（与 e2e 子进程同法）⇒ 本地面在场也必须**仍报 False**。
    sys.modules["maibot_sdk.compat"] = None
    install_mode = face.install_local_face(force=True)  # 装本地面（这一步不改 maibot_sdk 命名空间）
    upstream_after_face_install = face.upstream_available()

    print(
        json.dumps(
            {
                "face_file": str(face_file),
                "upstream_present": upstream_present,
                "upstream_after_face_install": upstream_after_face_install,
                "install_mode": install_mode,
                # 结论字段：本地面**在场**时，上游缺席必须仍能被分辨出来。
                "upstream_absent": upstream_after_face_install is False,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
