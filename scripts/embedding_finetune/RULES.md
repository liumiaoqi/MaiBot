# embedding_finetune 工作规则

> 最后更新：2026-08-04
> 本目录是独立于 MaiBot 主项目的本地模型微调工作区（训练环境 3.12，与主项目 3.14 隔离）。

---

## 1. 环境规则（硬性）

- **Python 3.12 专用**：微调环境是 `.venv`（cpython-3.12.11，Windows）。**不要用 uv run**——`uv run` 按主项目 pyproject 声明（3.14）重建环境，会冲掉训练环境（已踩坑一次）。
- **正确用法**：
  ```powershell
  .\.venv\Scripts\activate   # 激活后直接 python 跑
  python scripts\embedding_finetune\run_train_v1.py
  ```
- **torch 必须 cu128**：RTX 50 系（Blackwell sm_120）的 kernel 只在 cu128+ 轮子中；cu126 报 `no kernel image is available for execution on the device`。
- **环境重建命令**（环境被冲后恢复）：
  ```powershell
  uv venv --python 3.12 .venv
  uv pip install torch --index-url https://download.pytorch.org/whl/cu128   # 命中 uv 缓存，无需下载
  uv pip install -r scripts\embedding_finetune\requirements.txt
  ```
- 依赖（requirements.txt）：sentence-transformers[training]、accelerate>=1.1.0（sentence-transformers 3.x 的 fit 必需）、optimum[onnxruntime]、onnx、onnxruntime。torch 单独装（cu128 索引）。

## 2. 数据规则

- 三元组格式：`{"anchor": str, "positive": str, "negative": str}`，JSONL 一行一条。
- **positive 必须同源相关**（同一角色/话题的不同侧面），negative 必须语义不相关（hard negative 优先：同域不同话题 > 跨域）。
- 数据量：**1000 条精审数据足够**（比 2283 条混审更好）；资料类长文做 doc 侧、对话短文本（5-100 字）做 query 侧——**过滤规则别按长度剔**，短文本是 query 侧样本。
- 审核优先级：positive 对细看（跨会话的优先），negative 扫一眼（纯怪的直接过，假 negative——其实相关的——要挑出）。

## 3. 训练规则

- 入口：`run_train_v1.py` → `step3b_finetune.py`。step3 是初版（无 instruction），正式训练只用 step3b。
- **fp16 必需**：`--fp16`（sentence-transformers 3.x 参数是 `use_amp`，不是 fp16——传错报 TypeError）。Tensor Core 只加速 fp16，fp32 浪费 5060 一半算力。
- **`--max-seq-length 256`**：长文本截断，单步计算量减半。
- batch 经验：笔记本 5060（8GB 显存）**batch 8** 是甜点位；16 卡线（显存内存吃满）。
- 训练耗时参考：2283 条 × 3 epochs × batch 8 ≈ 5.5 小时（fp16 + 256 截断）。
- **一致性三原则**（训练/部署必须对齐）：
  1. query 侧（短文本 ≤100 字）加 instruction：`为这个句子生成表示以用于检索相关文章：`（与 BAAI 官方 README 一致）
  2. 向量 L2 normalize（训练验证与部署都做）
  3. 度量：训练 cosine = 部署 faiss 内积 + 归一化向量

## 4. 部署规则

- 导出：`python step4_export_onnx.py --model scripts\embedding_finetune\output\v1`（输出 onnx_model/，int8 量化）。
- step4 验证代码已内置 instruction + normalize（与训练一致）。
- 本地服务：自写 fastapi（20 行 OpenAI 兼容 /v1/embeddings）或 Xinference。MaiBot 接入**零代码**（配置见调研报告 `.shared/research/2026-08/embedding_config_chain_0804.md`）。
- **维度迁移大坑**：之前用过 2048 维（如阿里 text-embedding-v4）则存量向量库是 2048——接 1024 的 bge 前必须清空 `data/a-memorix/vectors` 重建，否则持久化被锁 + 检索降级。

## 5. 踩坑记录（2026-08-03/04）

| 坑 | 现象 | 解法 |
|----|------|------|
| `uv run` 重建环境 | .venv 变 3.14 + 主项目依赖，torch 环境丢失 | 永远用激活的 python，不用 uv run |
| cu126 torch | `no kernel image is available for execution on the device` | cu128 重装 |
| fit 的 fp16 参数 | `FitMixin.fit() got an unexpected keyword argument 'fp16'` | 3.x 改 `use_amp` |
| accelerate 缺失 | Trainer 要求 accelerate>=1.1.0 | requirements 已补 |
| step4 参数名 | `main() got an unexpected keyword argument 'model'` | argparse `dest="model_dir"`（已修） |
| 笔记本功耗墙 | 训练越跑越慢（降频） | 夏天别拉功耗；垫高 + 清灰 + 风扇拉满 |
| 内存吃满 | 显存满溢出到系统内存 | batch 降到 8 |

## 6. 当前状态（2026-08-04）

- v1 训练完成：2283 条 × 3 epochs，模型在 `output/v1`
- v2 计划：用户精审 1000 条 + CA 短文本语料（query 侧）后重训
- 微调产物接入方案、融合向量接线方案：见 `.shared/research/2026-08/` 调研报告
