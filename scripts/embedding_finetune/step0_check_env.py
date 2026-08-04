"""Step 0: 验证微调环境是否就绪。

检查项：
  1. PyTorch + CUDA
  2. sentence-transformers
  3. optimum + onnxruntime
  4. GPU 信息
  5. 训练数据是否存在
  6. 模型文件是否存在

用法：
  python step0_check_env.py [--model-dir PATH]
"""

import argparse
from pathlib import Path

DEFAULT_MODEL_DIR = Path("importantClone/bge-large-zh-v1.5")


def check(label: str, fn: callable) -> bool:
    try:
        result = fn()
        if result:
            print(f"  ✅ {label}")
        else:
            print(f"  ❌ {label}")
        return result
    except Exception as e:
        print(f"  ❌ {label} — {e}")
        return False


def main(model_dir: Path) -> None:
    all_ok = True

    print("=== 依赖检查 ===")

    all_ok &= check("PyTorch", lambda: __import__("torch") is not None)
    all_ok &= check("sentence-transformers", lambda: __import__("sentence_transformers") is not None)
    all_ok &= check("optimum", lambda: __import__("optimum") is not None)
    all_ok &= check("onnxruntime", lambda: __import__("onnxruntime") is not None)

    print("\n=== GPU 检查 ===")

    def cuda_check():
        import torch
        if not torch.cuda.is_available():
            return False
        print(f"       设备: {torch.cuda.get_device_name(0)}")
        props = torch.cuda.get_device_properties(0)
        print(f"       显存: {props.total_mem / 1024**3:.1f} GB")
        print(f"       CUDA: {torch.version.cuda}")
        return True

    all_ok &= check("CUDA GPU", cuda_check)

    print("\n=== 数据检查 ===")

    data_dir = Path("scripts/embedding_finetune/data")
    all_ok &= check("paragraphs.csv", lambda: (data_dir / "paragraphs.csv").exists())
    all_ok &= check("episodes.csv", lambda: (data_dir / "episodes.csv").exists())
    all_ok &= check("train_triplets.jsonl", lambda: (data_dir / "train_triplets.jsonl").exists())

    print("\n=== 模型检查 ===")

    def model_check():
        if model_dir.exists():
            files = list(model_dir.glob("*.bin")) + list(model_dir.glob("*.safetensors"))
            if files:
                total_mb = sum(f.stat().st_size for f in files) / 1024**2
                print(f"       路径: {model_dir}")
                print(f"       文件: {[f.name for f in files]}")
                print(f"       大小: {total_mb:.0f} MB")
                return True
        return False

    all_ok &= check("bge-large-zh-v1.5 模型", model_check)

    print(f"\n=== 总结: {'✅ 全部就绪' if all_ok else '❌ 有缺失项，请先安装'} ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    main(**vars(parser.parse_args()))