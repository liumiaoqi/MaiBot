"""启动 embedding 微调训练（第一版）。

用法：python run_train_v1.py
"""

import subprocess
import sys

cmd = [
    sys.executable,
    "scripts/embedding_finetune/step3b_finetune.py",
    "--triplets", "scripts/embedding_finetune/data/train_triplets_final.jsonl",
    "--base-model", "importantClone/bge-large-zh-v1.5",
    "--epochs", "3",
    "--batch-size", "8",
    "--fp16",
    "--max-seq-length", "256",
    "--output", "scripts/embedding_finetune/output/v1",
]

print("启动训练：", " ".join(cmd[1:]))
sys.exit(subprocess.call(cmd))