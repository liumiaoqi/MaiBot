# wander-06 · 定向漫游（最后碰运气 · 主题：记忆 / 检索 / agent / 图）

> 2026-10-15 ｜ 装置：`math_probe/wander6.py`（硬随机 rdrand）
> 定向：分类池收窄 21 个（cs.IR / cs.DB / cs.SI / cs.MA / …）+ GitHub **关键词池**（memory agent / retrieval graph / llm memory / knowledge graph agent，近两月）
> 素材：`wander-06_picks.txt`

## 〇、抽签

- 抽中 6 类：cs.IR · cs.DC · cs.HC · math.OC · q-bio.NC · physics.soc-ph

## 一、命中（贴核心议题的）

1. **★ cs.IR 四连**（本批最贴——改 Maibot 前正好读到）：
   - 《Revisiting Generative vs. Dense Retrieval: **A Static Value Prior Reverses the Gap**》——检索方法之争的修正（价值先验）；
   - 《RCER: Reconstructing **Cross-Evidence Relations** for Iterative RAG》——跨证据关系（与证据独立性同族）；
   - 《**Computed, not Memorized**: Bit-Factorized Identifiers for Generative Retrieval》——**标题即哲学**（算出来而非背下来）；
   - 《**Ground-Truth Subgraphs** for KG-Augmented LLMs》——**真值子图**（与 0004「真值回路」概念撞名）。
2. **★ q-bio.NC 三条「表亲」**（我们三条线各撞一个）：
   - 《**Cortisol time-scales × emotion regulation model**》——**情绪引擎的"激素时间尺度"**（快慢双层的表亲）；
   - 《SSM **Naturally Produce Time Cell** and Oscillatory Behaviors》——**cpu_lm 的 mini_ssm 撞上"时间细胞"**；
   - 《Simulating Alzheimer's on a **fly connectome**》——**snn 线的同一张果蝇连接组**，换个用法。
3. cs.HC 两篇：《**Measuring and Reducing Unusable Replies** of LLM Agents》（agent 输出的可用性度量）+《**Explorable Proofs**》（证明的可探索化——接手艺册子"形式化边界"主题）。
4. cs.DC：《Delta Tokenizer》（会话增量 token 化——接缓存线）；"**遗忘**"主题再 +2（联邦遗忘 ×2——与数据宝库的治理/删除发现呼应）。

## 二、机制观察（v7 改进项）

1. **小批分类池枯竭**：physics.soc-ph 本批 8 条——**抽 8 中 8 全是上一轮已抽过的**（该分类已被抽干）⇒ 滚动池的必要性再次实锤；
2. **关键词池长尾**：`--created >2026-08-01 + 关键词` 给的是"刚出生的婴儿仓"（多为 0–14★）⇒ **v7：关键词池加星数下限（>100★）**。

## 三、HF 生态信号

**uncensored / abliterated 工业化**：趋势榜 8 抽中 **4 个去审查版**（DeepSeek-V4.1-Flash-UNCENSORED / Qwen3.8-27B-Uncensored / abliterated-GSQ / GLM-5.3-Flash-Ablit）——
"去对齐"已从个例变成**流水线**（ablation 技术在多模型量产）——生态"双轨制"信号。

## 四、收尾

**wander 六轮至此收官**（01 广域 → 02 冷门优先 → 03 祛魅 → 04 论文专项 → 05 论文加强 → 06 定向）——
方向探索阶段收口，转「改动 Maibot」。
