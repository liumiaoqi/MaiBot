# wander-02 · 广域碰运气（第二轮）

> 2026-10-15 ｜ 装置：`math_probe/wander2.py`（硬随机 rdrand）
> v2 改动：分类池 59（候选 24）；**冷门优先分层**（热 ≥500 / 中 50–499 / 冷 <50：热1+中2+冷3）；HF 趋势榜；GitHub 池 100（近月）
> 素材：`wander-02_picks.txt`

## 〇、抽签结果

- 候选 24（59 池硬抽）；分层：**热 0 / 中 7 / 冷 17**（意外：双随机叠加把大热门全滤掉）
- 抽中 6 类：cs.RO · math.PR · cs.SD · math.DS · q-bio.PE · math.MG

## 一、命中

1. **★★ GitHub：dsh 生态插件爆款**——`Ebony-Vinyl/dsh-our-free-model`（**16682★**）："在 dsh 装上即用前沿模型（DeepSeek V4.1 Flash / Kimi K3），免费不限量"——**你天天用的生态被社区玩法推到了万星级**。⚠️ 实现方式存疑（"免费不限量"的凭证/代理模式有安全与合规问号）——**现象记档、不建议装**。
2. **★★ GitHub：`QingYunA/answer-me-with-html`（3391★）**——"让 Agent 用**一页 HTML** 回答复杂问题"的 **skill**——**这个交互美学被产品化了**（你的日常习惯就是它的用例）。
3. **★ arXiv q-bio.PE：《Physiology-Informed Sparse Identification of Dynamic Crop Models》**——**SINDy 式「稀疏辨识」**（从数据反推动力学方程的标准工具族）——**给情绪引擎 T6「系统辨识」方向的具体化**（比 T6 表里的一般方向更可落地：从轨迹学出可解释的方程）。
4. **storytold ArtCraft 生态持续爆发**：`filmcraft` **13.4k★**（9-30 才 2.9k——涨了 4 倍+）、**`gridcraft` 新仓 4.9k★**（pure-Rust Excel）、craft-launcher 2.7k（昨日）——"clean-room 全家桶"在织大网。
5. **决策引擎流派在铺基础设施**：`laya-mlx` 6.9k★ + `laya-coreml` 1.6k★——**Laya（typed decision models）的端侧运行时**（M3 Max 上 5–14ms 短决策）——挖宝录 §一 记的"Jev/Laya 流派"从论文长到了硬件运行时。
6. 其他：Compositor 1.7 万★（Mac 的 PS 替代）；fsearch 2.1k（macOS 版 Everything）；omdrop 2.7k（非苹果 airdrop）；ACR-Net（音频-语义解耦、"缓解语义占优"——弱相关）。

## 二、落空

arXiv 16 篇里约 14 落（cs.RO / math.DS / math.MG 全落）；GitHub 12 个里约 6 落。

## 三、观察

1. **「冷门优先」生效过猛**：热层 0——**双随机（先抽候选、再分层）叠加把大热门全滤掉了**——下一版把"热/冷"做成**显式参数**（如固定保底 2 个源大分类），别让机制意外。
2. **GitHub 侧再次全场最佳**：本轮最有价值的几条全在 GitHub 段——**"新仓榜"是工程生态变化的最高灵敏传感器**（比 arXiv 更贴"生态"）。
3. **skill 化继续扩散**（01 的观察 3 再现）：answer-me-with-html / ict-trading-model——"把方法做成 skill 发布"正在成为惯例。
4. HF 403（镜像缺 UA？）——**待修**（下轮：加 UA 或换端点）。

## 四、机制备注

- 装置：`wander2.py`；下轮待改：热层保底参数、HF 403 修复。
