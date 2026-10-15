# wander-04 · 广域碰运气（第四轮）

> 2026-10-15 ｜ 装置：`math_probe/wander4.py`（硬随机 rdrand）
> v4：祛魅 v2（强/弱词分级——修 v3 假阳性）；其余同 v3（2/2/2 平衡 + HF UA + GitHub 池 100）
> 素材：`wander-04_picks.txt`

## 〇、抽签

- 分层 热 1 / 中 6 / 冷 17；抽中：cs.AI · cs.LG · stat.ML · cond-mat.dis-nn · q-fin.PM · cs.RO

## 一、命中

1. **★ cs.AI：《Bench2Robust: Scenario-Controlled Recovery for Tool-Using Agents》**——**工具型 agent 的「恢复力」评测**（受控场景下的 agent 恢复）——今天下午刚做完"图的恢复力"（probe31），**agent 层的对应物**出现了：同一主题在多个层次同时被研究。
2. **★ q-fin.PM：《AlphaRLM: Aligning Language Models for Literature-Grounded Symbolic Factor Discovery》**——**用 LLM 从文献里发现符号化因子**（LLM + 符号回归的金融版）——与 SINDy 家族（wander-02 命中）同源——AI 交易线的现成工具面。
3. **`replica-skill`（2.6k★，"Eleven free Claude skills that clone any app"）**——**"克隆任何 App"的 skill 包**（size=66KB 的提示词集）——**与 rea「逆一切」同套路**（"X 任何 Y"命名公式 + 提示词包）——祛魅层的活体标本；不足："clone any"没进 v4 词表 ⇒ **v5 补"clone any / 克隆任何 / 复刻一切"**。
4. stat.ML《What Information Buys in Active Inference》——主动推理×信息价值（pymdp 线的邻居）。
5. **storytold 宇宙再扩建**：`soundcraft` 2.8k（**Avid Pro Tools 的 pure-Rust clean-room 重写**）——craft 家族已覆盖 影/音/图/表/矢量/3D……
6. 奇观与生态：`nvidia-macos-driver` 3k（给 macOS 写 N 卡 Metal 驱动——社区神活）；`DroidDeck` 8.4k（SteamOS 体验移植到 Android）；`Aleph-Alpha/Kolibri-1`（欧洲系 reasoning 模型）；`embeddinggemma-2-ft-typed-decision`（**决策流派扩散**——连 gemma 都被社区微调成 typed decision）。

## 二、祛魅 v2 首跑

- 强/弱词分级后本批**零误报**（v3 假阳性修复 ✓）；新标本 replica-skill 属"强词缺席、套路明确"型——
  词表在对抗中成长（v5 补词）。

## 三、漫游机制观察

- **重复发现现象**：quasiperiodic 那篇被两个分类各抽中一次（arXiv cross-list）；GitHub 侧
  filmcraft / answer-me-with-html / solidcraft / NanoJev 反复出现——**池子有限**（100 池多轮必重复）
  ⇒ **v5：GitHub 池滚动更新 / 已抽记录去重**。

## 四、落空

arXiv 约 10/16；GitHub 约半。常规水位。
