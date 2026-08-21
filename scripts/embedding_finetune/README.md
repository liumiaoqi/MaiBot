# AI 实验区（scripts/embedding_finetune）

> MaiBot 所有 AI 相关实验的统一工作区（2026-08-17 立）——**独立于主项目**：uv 隔离环境（Python 3.12 + torch cu128），规则见 `RULES.md`。

## 实验线全景

| 子目录 | 内容 |
|--------|------|
| `snn_behavior/` | 脉冲神经网络行为模拟（LIF→Braitenberg→STDP→R-STDP 学习线 + 情绪/欲望行为实验 exp51-60） |
| `cpu_lm/` | 纯 CPU 小语言模型实验（mini_transformer/mini_ssm/bpe_tokenizer——可复现） |
| `music_rule_gen/` | 音乐规则生成器（简谱解析 + 规则归纳 + 推理生成——"音乐是数值结构不是统计结构"） |
| `trading/` | 股票数据抓取/分析实验（fetch_*/industry_*——数据爬取与行业分析） |
| `knob_experiment/` | 旋钮参数实验 |
| `maibot_embedding_finetune/` | bge 向量微调工具链（下文详细） |

> **数据说明**：实验数据/模型产物（data/ output/ checkpoints/ engines/ onnx_model/ .venv/）**不随仓库分发**（.gitignore 排除）——clone 后按各子目录 NOTES/README 重新生成或自行准备数据。

---

# Embedding 微调工具链（原 README）

微调 bge-large-zh-v1.5，让向量更贴合 MaiBot 聊天记忆的语义空间。

## 前置条件

### 宿主机（Windows，不用 Docker）

```bash
# PyTorch + CUDA（RTX 5060，选 CUDA 12.6）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

# 微调框架
pip install "sentence-transformers[training]"

# ONNX 导出
pip install "optimum[onnxruntime]" onnx onnxruntime
```

### 验证 GPU
```python
import torch
print(torch.cuda.is_available())  # 应为 True
print(torch.cuda.get_device_name(0))  # 应显示 RTX 5060
```

## 步骤

### Step 1: 提取 A_memorix 数据
```bash
python scripts/embedding_finetune/step1_extract_data.py
```
输出：`data/paragraphs.csv`, `data/episodes.csv`, `data/relations.csv`, `data/entities.csv`

### Step 2: 构造三元组
```bash
python scripts/embedding_finetune/step2_build_triplets.py --top-k 3 --bottom-k 3
```
用阿里 API embedding 计算向量，按余弦相似度自动构造 (anchor, positive, negative) 三元组。
输出：`data/train_triplets.jsonl`

### Step 3: 微调模型（GPU，RTX 5060）
```bash
python scripts/embedding_finetune/step3_finetune.py --epochs 3 --batch-size 16
```
输出：`finetuned_model/`（PyTorch 格式）

### Step 4: 导出 ONNX INT8
```bash
python scripts/embedding_finetune/step4_export_onnx.py
```
输出：`onnx_model/`（~350MB，CPU 推理用）

## 参数说明

| 参数 | 默认 | 说明 |
|------|------|------|
| `--epochs` | 3 | 训练轮数，3 轮通常够用 |
| `--batch-size` | 16 | 批大小，RTX 5060 (8GB) 用 16 安全 |
| `--top-k` | 3 | 每个 anchor 取 Top-K 近邻为 positive |
| `--bottom-k` | 3 | 每个 anchor 取 Bottom-K 远邻为 negative |

## 预计耗时

| 步骤 | 耗时 | 设备 |
|------|------|------|
| Step 1 | <1s | CPU |
| Step 2 | ~5-10 分钟 | 网络（阿里 API） |
| Step 3 | ~30-60 分钟 | GPU |
| Step 4 | ~1-3 分钟 | CPU |