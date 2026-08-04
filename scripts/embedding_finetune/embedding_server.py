"""本地 embedding 推理服务（OpenAI 兼容 /v1/embeddings）。

加载 step4 导出的 model_q8.onnx（int8），MaiBot 的 openai_client 直接对接。

用法：
  uv pip install fastapi uvicorn onnxruntime
  uvicorn embedding_server:app --host 127.0.0.1 --port 9997

一致性（训练/部署对齐）：
  - pooling：CLS（bge 1_Pooling 配置 pooling_mode_cls_token=true）
  - normalize：L2（faiss METRIC_INNER_PRODUCT 内积 + 归一化 = 余弦）
  - instruction：query 侧加训练时前缀；doc 侧不加。
    服务通过 "is_query" 字段区分（默认 query 行为，与 v1 训练 anchor 侧一致）。
    v2 训练若改为全不加 instruction，则把 QUERY_INSTRUCTION 置空即可。
"""

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI
from pydantic import BaseModel, Field
from transformers import AutoTokenizer

MODEL_DIR = "onnx_model"
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

app = FastAPI(title="Local BGE Embedding Server")

_tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
_session = ort.InferenceSession(f"{MODEL_DIR}/model_q8.onnx")


class EmbeddingRequest(BaseModel):
    model: str = "bge-finetuned"
    input: str | list[str]
    is_query: bool = Field(default=True, description="query 侧加 instruction（doc 侧传 false）")


def _encode(texts: list[str]) -> np.ndarray:
    inputs = _tokenizer(
        texts, return_tensors="np", padding=True, truncation=True, max_length=512,
    )
    outputs = _session.run(
        None, {k: v.astype(np.int64) for k, v in inputs.items()},
    )
    embeddings = outputs[0][:, 0, :].astype(np.float32)  # CLS pooling
    norms = np.linalg.norm(embeddings, axis=-1, keepdims=True)
    return embeddings / np.maximum(norms, 1e-12)  # L2 normalize


@app.post("/v1/embeddings")
def embeddings(body: EmbeddingRequest) -> dict:
    texts = [body.input] if isinstance(body.input, str) else list(body.input)
    if QUERY_INSTRUCTION and body.is_query:
        texts = [QUERY_INSTRUCTION + t for t in texts]
    embeddings = _encode(texts)
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": i, "embedding": emb.tolist()}
            for i, emb in enumerate(embeddings)
        ],
        "model": body.model,
    }


if __name__ == "__main__":
    # 自检：模拟 query（加 instruction）与 doc（不加）各一条
    for label, is_query in (("query", True), ("doc", False)):
        emb = _encode([QUERY_INSTRUCTION + "测试" if is_query else "测试"])
        print(f"{label}: 维度 {emb.shape[1]}, 范数 {np.linalg.norm(emb[0]):.6f}")
