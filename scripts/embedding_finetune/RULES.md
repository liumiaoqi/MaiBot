# AI 实验区工作规则（scripts/embedding_finetune）

> 最后更新：2026-08-17
> **本目录 = MaiBot 所有 AI 相关实验的统一工作区**（embedding 微调 / SNN 脉冲网络 / 小模型 / 新架构验证）——独立于主项目，uv 隔离环境（Python 3.12 + torch cu128，与主项目 3.14 彻底隔离）。
> 规则：AGENTS.md「AI 实验区」条款 + 本文件。

---

## 0. AI 实验区总则（2026-08-17 立）

- **统一位置**：所有 AI 相关实验（微调/SNN/小模型/新架构/行为模拟）在**本目录**做；lab/ 只放非 AI 的零散脚本
- **uv 隔离**：独立 .venv（Python 3.12），不用根目录 uv run（会按主项目 pyproject 用根 .venv）
- **环境**：torch 必须 cu128（RTX 50 系 Blackwell sm_120）
- **新实验子目录**：每个实验一个子目录（如 snn_behavior/）+ 自己的 NOTES.md + 报告进 .shared/research/
- **依赖**：新实验依赖加入 pyproject.toml（如 snntorch）或实验子目录 requirements

---

## 1. embedding_finetune 微调专题（原 RULES 内容）

> 环境规则（硬性）

---

### 1.1 环境规则（硬性）

- **独立环境**：本目录有独立的 `.venv`（Python 3.12，由 `pyproject.toml` 声明）——与主项目（MaiBot 根 .venv）**彻底隔离**。
- **建环境**（torch 命中 uv 缓存，秒装）：
  ```powershell
  cd scripts\embedding_finetune
  uv venv --python 3.12 .venv
  uv pip install -e .        # 按 pyproject.toml 声明装依赖（torch 自动走 cu128 索引）
  ```
- **使用**：`cd scripts\embedding_finetune` 后 `.\venv\Scripts\activate`，直接 `python run_train_v1.py`。
- **不要用根目录的 uv run 跑本目录脚本**（会按主项目 pyproject 用根 .venv）；本目录内的 uv 命令自动用本目录 .venv。
- **torch 必须 cu128**：RTX 50 系（Blackwell sm_120）的 kernel 只在 cu128+ 轮子中；cu126 报 `no kernel image is available for execution on the device`。
- 依赖声明：`pyproject.toml`（torch 走 `pytorch-cu128` 专用索引）；requirements.txt 是参考副本。

### 1.2 数据规则

- 三元组格式：`{"anchor": str, "positive": str, "negative": str}`，JSONL 一行一条。
- **positive 必须同源相关**（同一角色/话题的不同侧面），negative 必须语义不相关（hard negative 优先：同域不同话题 > 跨域）。
- 数据量：**1000 条精审数据足够**（比 2283 条混审更好）；资料类长文做 doc 侧、对话短文本（5-100 字）做 query 侧——**过滤规则别按长度剔**，短文本是 query 侧样本。
- 审核优先级：positive 对细看（跨会话的优先），negative 扫一眼（纯怪的直接过，假 negative——其实相关的——要挑出）。

### 1.3 训练规则

- 入口：`run_train_v1.py` → `step3b_finetune.py`。step3 是初版（无 instruction），正式训练只用 step3b。
- **fp16 必需**：`--fp16`（sentence-transformers 3.x 参数是 `use_amp`，不是 fp16——传错报 TypeError）。Tensor Core 只加速 fp16，fp32 浪费 5060 一半算力。
- **`--max-seq-length 256`**：长文本截断，单步计算量减半。
- batch 经验：笔记本 5060（8GB 显存）**batch 8** 是甜点位；16 卡线（显存内存吃满）。
- 训练耗时参考：2283 条 × 3 epochs × batch 8 ≈ 5.5 小时（fp16 + 256 截断）。
- **一致性三原则**（训练/部署必须对齐）：
  1. query 侧（短文本 ≤100 字）加 instruction：`为这个句子生成表示以用于检索相关文章：`（与 BAAI 官方 README 一致）
  2. 向量 L2 normalize（训练验证与部署都做）
  3. 度量：训练 cosine = 部署 faiss 内积 + 归一化向量

### 1.4 部署规则

- 导出：`python step4_export_onnx.py --model scripts\embedding_finetune\output\v1`（输出 onnx_model/：model.onnx fp32 + model_q8.onnx int8 + tokenizer）。
- 推理服务：`embedding_server.py`（OpenAI 兼容 /v1/embeddings，加载 model_q8.onnx）：
  ```powershell
  uvicorn embedding_server:app --host 127.0.0.1 --port 9997
  ```
- **instruction 决策（v1 现状）**：MaiBot 的 openai_client 只发 {model, input}——服务 `is_query` 恒 True = 所有文本加 instruction。query 检索侧与 v1 训练（anchor 加前缀）对齐 ✓；doc 写入侧训练没加但部署加（轻微偏移）。
- **v2 对齐方案**：训练时去掉 instruction（step3b 的 QUERY_INSTRUCTION 置空——v1.5 官方支持无 instruction 检索），服务端 `QUERY_INSTRUCTION` 同步置空——完全对齐，零偏移。
- MaiBot 接入**零代码**（配置见调研报告 `.shared/research/2026-08/embedding_config_chain_0804.md`）：model_config.toml 加 `LocalEmbed` provider（auth_type="none" + api_key="none"）+ embedding.model_list；bot_config.toml `dimension = 1024`。
- **维度迁移大坑**：之前用过 2048 维（如阿里 text-embedding-v4）则存量向量库是 2048——接 1024 的 bge 前必须清空 `data/a-memorix/vectors` 重建，否则持久化被锁 + 检索降级。

### 1.5 踩坑记录（2026-08-03/04）

| 坑 | 现象 | 解法 |
|----|------|------|
| `uv run` 重建环境 | .venv 变 3.14 + 主项目依赖，torch 环境丢失 | 独立 .venv + 本目录 pyproject.toml 隔离；根目录 uv run 碰不到 |
| cu126 torch | `no kernel image is available for execution on the device` | cu128 重装 |
| fit 的 fp16 参数 | `FitMixin.fit() got an unexpected keyword argument 'fp16'` | 3.x 改 `use_amp` |
| accelerate 缺失 | Trainer 要求 accelerate>=1.1.0 | requirements 已补 |
| step4 参数名 | `main() got an unexpected keyword argument 'model'` | argparse `dest="model_dir"`（已修） |
| 笔记本功耗墙 | 训练越跑越慢（降频） | 夏天别拉功耗；垫高 + 清灰 + 风扇拉满 |
| 内存吃满 | 显存满溢出到系统内存 | batch 降到 8 |
| optimum × ST 3.x 不兼容 | 导出 ONNX 报 `property 'config' has no setter` | 绕开 optimum——step4 手动 torch.onnx.export + onnxruntime quantize_dynamic |
| onnxscript 缺失 | torch.onnx.export 报 `No module named 'onnxscript'` | torch 2.11 新导出器依赖——requirements 已补 |
| setuptools 包发现 | `uv pip install -e .` 报 `Multiple top-level packages: data/output/onnx_model` | pyproject 加 `[tool.setuptools] py-modules=[] + packages.find exclude` |
| torchvision warning | 导出时 `torchvision is not installed. Skipping torchvision::roi_align` | 无害噪音（图像算子，BERT 用不到），忽略 |

### 1.6 当前状态（2026-08-04）

- v1 训练完成：2283 条 × 3 epochs，模型在 `output/v1`
- v2 计划：用户精审 1000 条 + CA 短文本语料（query 侧）后重训
- 微调产物接入方案、融合向量接线方案：见 `.shared/research/2026-08/` 调研报告