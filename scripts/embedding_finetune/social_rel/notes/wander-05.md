# wander-05 · 论文侧专项（承 lmq「论文侧刚刚好像没怎么碰运气」）

> 2026-10-15 ｜ 装置：`math_probe/wander5_papers.py`（硬随机 rdrand）
> 口径：**加量 8 倍**（8 类 × 12 篇 = 81 篇实抽）+ **专挑跨界富矿池**（28 个应用/交叉类，硬抽 8）——
> 热门 cs.AI/cs.LG 本轮不参与。素材：`wander-05_picks.txt`。
> 抽中 8 类：eess.SP · nlin.AO · physics.soc-ph · cs.SI · cs.GT · stat.TH · stat.ML · econ.TH

## 〇、机制验证（本轮主旨）

| 口径 | 论文侧命中率（"中及以上"） |
|---|---|
| wander-02/03/04（每轮 12 篇 · 均匀分层） | ~10%（每轮 1-2 条） |
| **wander-05（81 篇 · 擦边专项）** | **~20%（15-18 条）** |

⇒ **"论文侧没出大货"的病因确认 = 量太小 + 抽签落回 cs 域**；**药方（加量 + 擦边专项）有效**。

## 一、Top 命中（按价值）

1. **★★ stat.TH《Minimax estimation of the pseudo-spectral gap of continuous Markov chains》**——
   **从单条轨迹极小极大估计马氏链的「伪谱隙」**——**松弛线的「估计版」**：我们（probe28/31）测的是**已知图**的谱隙；
   这篇解决的是**从观测数据估计谱隙**——将来要在真库上"从日志估松弛"，这就是现成的方法论。
2. **★★ stat.TH《MCMC Can See Can't See》**——**"收敛诊断守不住收敛"被证明为不可能性定理**（任何有限诊断清单都可被骗过）——
   与手艺册子「Lean 守逻辑不守翻译」同族：**验证有边界，且这边界被数学封死**。
3. **★ physics.soc-ph《Uncovering higher-order interactions from memory in observed dynamics》**——
   **从"记忆"中发现高阶交互**（超图）——pairwise 不够的又一实锤（接 probe23 多重叠教训 / 方向 B）。
4. **★ cs.SI《Ergodic and Metastable Behavior of Stochastic Popularity Dynamics》**——人气动力学的**亚稳行为**——
   "冻结态/亚稳态"词汇的又一参照系（exp35 盆底 · SK 慢化同族）。
5. **★ cs.SI《Filling holes in science draws collective attention…》**——把知识表示为概念嵌入、看"**洞**"与集体注意——
   概念图（A_memorix 同族对象）上的结构分析方法。
6. **★ cs.SI《Semantic Communities and Boundary-Spanning Lyrics in K-pop》**——**语义图 + 社区发现做歌词研究**（MiniLM 384 维 × 7891 首）——
   LT-2（分类涌现）的同款任务 + 音乐线趣味（图×语义×音乐三交叉）。
7. **stat.ML《GLL: A Differentiable Graph Learning Layer》**——**可微图学习层**（图结构学习接进网络）——关系图学习工具面。
8. **nlin.AO《Online training of Echo State Networks》**——ESN 在线训练——"给模型加在线状态"的技术路线之一（接今日"状态"话题）。
9. **cs.GT《What Does Disagreement Mean?…》**——**分歧的语义分解**（稳定异质性 vs 短暂随机 vs …）——"表观一致"的镜像问题。
10. **econ.TH《Who Keeps a Bubble Alive? Skin in the Game…》·《Rewarding Noise: Incentives in Decentralized A/B Testing》**——
    理性泡沫存活机制 / "奖励噪声"的激励怪象——交易线与"噪声治理"的趣味参照。

## 二、富矿地图（本轮实证）

**"社会物理 + 统计 + 博弈"三角是论文侧的相关岛**：cs.SI · physics.soc-ph · stat.TH · stat.ML · cs.GT · econ.TH（+ wander-01 的 q-fin/eess）——
约 **30 个"应用/交叉分类"**构成富矿带；**热门大分类反而是贫矿**（信号被淹没）。

## 三、跨轮次主题聚类

- **「从数据 / 文献恢复动力学」家族第 3 次出现**（SINDy[q-bio] → AlphaRLM[q-fin] → 相位动力学重建[nlin]）——持续线索，值得盯；
- **「松弛 / 谱 / 亚稳」**（谱隙估计 · 亚稳 · MCMC 诊断）——与 probe28–31 一条线；
- **「记忆 / 高阶交互」**（higher-order from memory）——与证据独立性；
- **「LLM 多智能体社会模拟」**（Generalized Multi-Agent Social Simulation 等 3 条）——MaiBot 线的学术周边。

## 四、机制备注

- **cross-list 重复**又见（4-5 篇在两分类重复抽中）⇒ 论文侧也需**同标题去重**（v5 待办合流）。
