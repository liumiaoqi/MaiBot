# AI 实验区索引（scripts/embedding_finetune——2026-08-22 建）

> 定位：MaiBot 所有 AI 相关实验的统一实验室（2026-08-17 立）——uv 隔离（Python 3.12 + torch cu128），规则见 `RULES.md`
> **有索引先读索引，索引有遗漏向 lmq 报告**。全景 README：`README.md`
> 状态图例：🟢 活跃 / 🟡 暂停或阶段完成 / ⚪ 数据或产物目录（不入库）

## 实验线

| 子目录 | 内容 | 状态 | 入口（先读） |
|--------|------|------|------------|
| `snn_behavior/` | 脉冲神经网络行为模拟——LIF→Braitenberg→STDP→R-STDP 学习线 + 情绪/欲望行为实验（exp51-60 等） | 🟢 | NOTES.md（exp0 起） |
| `cpu_lm/` | 纯 CPU 小语言模型实验——mini_transformer/mini_ssm/bpe_tokenizer（可复现） | 🟢 | NOTES.md |
| `music_rule_gen/` | 音乐规则生成器——简谱解析 + 规则归纳 + 推理生成（“音乐是数值结构不是统计结构”） | 🟡 | README.md |
| `trading/` | 股票数据抓取/分析（fetch_*/industry_*/probe_*——89 个 py，数据实验） | 🟢 | NOTES.md（2026-08-18 建） |
| `knob_experiment/` | 旋钮参数实验 | 🟡 | README.md |
| `C++/` | C++ 加速实现（build_triplets 三元组构建） | 🟡 | build_triplets.cpp + Makefile |
| `maibot_embedding_finetune/` | bge 向量微调工具链（step0-4 流水线 + ONNX 导出） | 🟡 | README.md 下半部 |

## 数据/产物目录（不入库——.gitignore 排除）

| 目录 | 内容 |
|------|------|
| `data/` | 训练数据（paragraphs/episodes/relations/triplets） |
| `output/` | 实验输出 |
| `onnx_model/` | ONNX 导出模型 |
| `maibot_embedding_finetune.egg-info/` | 包元数据 |
| `.venv/` | 隔离环境（3.12 + cu128） |

## 顶层脚本分组（2026-08-22 补——trading 域脚本已迁入 trading/，顶层残留多为早期）

| 组 | 脚本 | 用途 |
|----|------|------|
| 微调流水线 | step0_check_env / step1_extract_data / step2_build_triplets / step3(f)b_finetune / step4_export_onnx | bge 微调五步（对齐 README 步骤） |
| 数据处理 | clean_triplets / rewrite_clean / show_training_data / preview_data | 三元组清洗与预览 |
| 嵌入服务 | embedding_server.py | 向量服务 |
| 早期抓取/分析 | fetch_* / probe_* / industry_* / read_tiers* / refetch_*（30+ 个） | trading 域早期脚本——新工作在 trading/ 内做 |

## 使用方式

1. 进实验区先读本索引 → 确定实验线 → 读该线 NOTES/README
2. 新实验：按 RULES.md 建目录（有独立 NOTES.md）
3. 数据/模型产物不入库；clone 后按 NOTES 重新生成