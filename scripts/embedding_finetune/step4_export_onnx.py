"""Step 4: 将微调后的模型导出为 ONNX INT8 格式，供 MaiBot CPU 推理使用。

手动 torch.onnx.export（绕开 optimum——optimum 与 sentence-transformers 3.x
不兼容：SentenceTransformer.config 只读 property 报错）。

前置：
  - pip install onnx onnxruntime
  - step3b_finetune.py 已生成 output/v1/

用法：
  python step4_export_onnx.py [--model DIR] [--output DIR]

部署一致性（P0，微调训练/部署必须对齐）：
  1. instruction：训练时短 query 加了 "为这个句子生成表示以用于检索相关文章："，
     MaiBot 检索 query 侧也必须拼同一前缀（doc 侧不加）
  2. 度量：训练用 cosine 相似度，MaiBot faiss 用 METRIC_INNER_PRODUCT——
     部署时向量必须 L2 normalize（内积 + 归一化 = 余弦）
  3. pooling：bge 用 CLS token（1_Pooling 配置 pooling_mode_cls_token=true）
"""

import argparse
from pathlib import Path

DEFAULT_MODEL = Path("scripts/embedding_finetune/output/v1")
DEFAULT_OUTPUT = Path("scripts/embedding_finetune/onnx_model")

QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："


def main(model_dir: Path, output_dir: Path) -> None:
    import numpy as np
    import torch
    from transformers import AutoModel, AutoTokenizer

    print(f"导出 ONNX (INT8 动态量化): {model_dir} → {output_dir}")

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    # 加载 BERT 主体（AutoModel 只读 config.json + 权重，忽略 1_Pooling/ 等 ST 目录）
    model = AutoModel.from_pretrained(str(model_dir))
    model.eval()

    output_dir.mkdir(parents=True, exist_ok=True)
    fp32_path = output_dir / "model.onnx"
    int8_path = output_dir / "model_q8.onnx"

    dummy = tokenizer(["测试"], return_tensors="pt", padding=True, truncation=True, max_length=512)
    with torch.no_grad():
        torch.onnx.export(
            model,
            (dummy["input_ids"], dummy["attention_mask"], dummy["token_type_ids"]),
            str(fp32_path),
            input_names=["input_ids", "attention_mask", "token_type_ids"],
            output_names=["last_hidden_state"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "seq"},
                "attention_mask": {0: "batch", 1: "seq"},
                "token_type_ids": {0: "batch", 1: "seq"},
                "last_hidden_state": {0: "batch", 1: "seq"},
            },
            opset_version=17,
        )

    # INT8 动态量化（权重 int8，激活 fp32——embedding 检索几乎无损）
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(str(fp32_path), str(int8_path), weight_type=QuantType.QInt8)

    # 保存 tokenizer（部署侧复用）
    tokenizer.save_pretrained(str(output_dir))
    print(f"ONNX 模型已保存至: {output_dir}（model.onnx fp32 + model_q8.onnx int8）")

    print("验证推理（query 侧加 instruction + CLS pooling + L2 normalize）...")
    import onnxruntime as ort

    session = ort.InferenceSession(str(int8_path))
    texts = ["麦麦今天心情不好", "测试ONNX推理效果"]
    inputs = tokenizer(
        [QUERY_INSTRUCTION + text for text in texts],
        return_tensors="np", padding=True, truncation=True, max_length=512,
    )
    outputs = session.run(None, {k: v.astype(np.int64) for k, v in inputs.items()})
    embeddings = outputs[0][:, 0, :].astype(np.float32)  # CLS pooling
    norms = np.linalg.norm(embeddings, axis=-1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-12)
    for text, emb in zip(texts, embeddings, strict=True):
        print(f"  '{text}' → 维度 {len(emb)}, 前5维: {np.round(emb[:5], 4).tolist()}")

    print("\n部署到 MaiBot（一致性要求）：")
    print(f"  1. 将 {output_dir} 目录复制到 MaiBot 可访问路径")
    print(f"  2. query 侧（检索/召回）文本前拼 instruction：{QUERY_INSTRUCTION}")
    print("  3. 编码后向量必须 L2 normalize（faiss METRIC_INNER_PRODUCT 需要）")
    print("  4. doc 侧（写入记忆的段落）不加 instruction、同样 normalize")
    print("  5. 推理：tokenize → model_q8.onnx → last_hidden_state[:, 0, :] → normalize")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, dest="model_dir")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, dest="output_dir")
    main(**vars(parser.parse_args()))
