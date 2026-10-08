# 实验区索引 —— trading/ × math_probe/

> 2026-10-08 立（`probe22_make_index.py` 生成 + 手写分组）。
> **入口**：`trading/` 是实验本体（73 个 exp）；`math_probe/` 是审计探针与档案（21 探针）。
> 探针结论详情 → `math_probe/NOTES.md`；审计方法论 → `math_probe/AUDIT-CHECKLIST.md`。

## A. 交易基础线（exp1–14）  
*R-STDP 演进 / 特征 / 先验 / 参数寻优*

| exp | 文件 | 行数 | 摘要（首行 docstring） | 探针 |
|---|---|---|---|---|
| exp1 | `exp1_linear_ai.py` | 69 | 按预测交易:预测涨->持有,预测跌->空仓。算交易成本。 |  |
| exp1b | `exp1b_param_scale.py` | 26 | (no docstring) |  |
| exp2 | `exp2_lstm.py` | 65 | (no docstring) |  |
| exp3 | `exp3_snn.py` | 79 | SNN: 输入收益率 -> 脉冲 -> Leaky 神经元 -> 读末态 -> 预测涨跌 |  |
| exp4 | `exp4_rule_ai.py` | 76 | AI 输出每个时间点的看涨概率(0-1)。 |  |
| exp5 | `exp5_rstdp.py` | 95 | exp5: R-STDP 交易(对齐 exp2b 觅食)——v2 修复:输入放大+阈值降低 |  |
| exp6 | `exp6_rstdp_v3.py` | 116 | exp6: R-STDP 改进奖励——持有期也学习(解决涨股踏空) |  |
| exp6 | `exp6_rstdp_v4.py` | 113 | exp6v2: R-STDP 三动作(买/卖/持有)——持有奖励真正落到权重 |  |
| exp6v3 | `exp6v3_bench.py` | 84 | exp6v3: 快速验证——长周期持有奖励 + 基准对照奖励 |  |
| exp6v5 | `exp6v5_bench.py` | 96 | exp6v5: 真正实现相对基准奖励——跑赢'买入持有'才算好 |  |
| exp7 | `exp7_trend.py` | 114 | exp7: 趋势特征 R-STDP——让 AI 感知大趋势(解决中石油式踏空) |  |
| exp7 | `exp7_trend2.py` | 89 | exp7v2: 2输入 R-STDP(单日收益 + 20日趋势方向)——趋势用符号信号 |  |
| exp8 | `exp8_prior.py` | 101 | exp8: 先验注入 R-STDP——人的领域知识(贝塔)作为额外输入 |  |
| exp9 | `exp9_cycle_plan.py` | 113 | exp9: 周期先验 + 五年计划先验注入 R-STDP |  |
| exp10 | `exp10_trust.py` | 124 | exp10: 先验信度学习——AI 自己学'该信多少先验' |  |
| exp12 | `exp12_policy_prior.py` | 110 | exp12: 时代年轮真实政策先验 + 信度学习 |  |
| exp12b | `exp12b_stability.py` | 17 | exp12b: 多次运行取平均——验证真实政策先验的稳定性(10次不同种子) |  |
| exp13 | `exp13_param_search.py` | 115 | exp13: 参数寻优——不同股票的最优参数是否不同?有没有规律? |  |
| exp14 | `exp14_full_pipeline.py` | 116 | exp14: 完整流程跑第二批——参数寻优 + 政策先验 + 信度学习 |  |

## B. 噪声与量子信道线（exp15–28）  
*噪声注入 / 量子信道 / 种子 / 完整方法 / 检索扰动*

| exp | 文件 | 行数 | 摘要（首行 docstring） | 探针 |
|---|---|---|---|---|
| exp15 | `exp15_noise_vs_deterministic.py` | 176 | exp15: 噪声注入 vs 确定性——输入噪声作为正则化资源 |  |
| exp16 | `exp16_noise_sensitivity.py` | 147 | exp16: 噪声受益股票的识别特征——哪类股票该加噪声? |  |
| exp16b | `exp16b_batch1_validation.py` | 109 | exp16b: batch1 验证——交易频率规则是否跨批次成立 |  |
| exp17 | `exp17_annealing.py` | 139 | exp17: 自适应噪声——噪声退火 vs 固定噪声 vs 确定性 |  |
| exp18 | `exp18_adaptive_noise.py` | 139 | exp18: 行为反馈自适应噪声——交易频率实时调噪(不靠静态特征) |  |
| exp19 | `exp19_quantum_noise.py` | 178 | exp19: 量子信道式噪声 vs 高斯噪声——16 只新样本大规模验证 |  |
| exp20 | `exp20_quantum_noise_cross_batch.py` | 100 | exp20: 量子信道噪声跨批次验证——batch1 + batch2 全部 18 只 |  |
| exp21 | `exp21_all_samples_noise_stability.py` | 130 | exp21: 全样本(34 只)× 多 seeds(10)量子噪声稳定性验证 |  |
| exp22 | `exp22_complete_method_noise.py` | 258 | exp22: 完整方法组合——之前所有积累 + 量子噪声(修正 exp19-21 的变量隔离偏差) |  |
| exp23 | `exp23_hard_rng_compare.py` | 90 | exp23: 硬随机(secrets) vs 伪随机(PRNG)——统计等效验证 |  |
| exp24 | `exp24_seed_correlation.py` | 93 | exp24: 种子相关性验证——连续小种子 vs 大随机种子 vs 硬随机 |  |
| exp25 | `exp25_big_seed_recheck.py` | 120 | exp25: exp21 复核——大随机种子列表(方差修正后) |  |
| exp26 | `exp26_qiskit_noise.py` | 232 | exp26: 真·Qiskit 量子信道噪声——特征过量子电路(修正 exp19 的数学模拟) |  |
| exp27 | `exp27_maibot_retrieval_diversity.py` | 128 | exp27: 量子信道噪声迁移到 MaiBot 检索——检索多样性 vs 质量损失 | probe16 |
| exp28 | `exp28_real_structure_retrieval.py` | 122 | exp28: 真实结构检索模拟——A_memorix 三通道融合下的量子信道扰动 | probe16 |

## C. 记忆与量子结构线（exp29–40）  
*遗忘 / 去重 / Hopfield / 果蝇 VQC / 退火 / 故障注入 / QSNN*

| exp | 文件 | 行数 | 摘要（首行 docstring） | 探针 |
|---|---|---|---|---|
| exp29 | `exp29_quantum_forgetting.py` | 139 | exp29: 量子遗忘曲线——振幅阻尼/两能级 vs 现状 granular_decay vs 复习强化 | probe1 |
| exp30 | `exp30_entanglement_dedup.py` | 139 | exp30: 纠缠熵记忆去重——量子互信息 vs 文本相似度(信息论冗余度) | probe7 |
| exp31 | `exp31_grover_goal_amplification.py` | 150 | exp31: Grover 式目标放大——概率放大 vs 确定性贪心(ZH ㉑) | probe3 |
| exp32 | `exp32_quantum_annealing_desire.py` | 103 | exp32: 量子退火欲望演化——隧穿跳出局部最优(ZH ㉓) | probe10 |
| exp33 | `exp33_fault_injection.py` | 121 | exp33: 量子信道式故障注入——bitflip 混沌测试 sqlite 存储鲁棒性(ZG) |  |
| exp34 | `exp34_qsnn.py` | 191 | exp34: QSNN——复振幅量子神经元 R-STDP(SNN 线 × 量子线收官) | probe15 |
| exp35 | `exp35_quantum_hopfield.py` | 175 | exp35: 量子 Hopfield 式记忆检索——残缺输入恢复 vs 相似度检索(ZH 候选2) |  |
| exp36 | `exp36_intrinsic_randomness.py` | 179 | exp36: 内禀随机性 vs 伪随机——对抗场景下不可预测性的价值(ZH 候选3) | probe14 |
| exp37 | `exp37_tensor_network_compression.py` | 141 | exp37: 张量网络压缩会话历史——低秩结构 vs 截断(对标 dsh compaction) | probe2/5 |
| exp38 | `exp38_fruitfly_olfaction.py` | 190 | exp38: 果蝇级嗅觉趋避——三组对比(无学习/R-STDP/QSNN) |  |
| exp38b | `exp38b_qsnn_phase_interference.py` | 191 | exp38b: QSNN 相位放大适配稀疏任务——双路径干涉版(修 exp38 失败) |  |
| exp39 | `exp39_qiskit_fruitfly_vqc.py` | 167 | exp39: Qiskit VQC 果蝇嗅觉——变分量子电路(正交做法,修 exp38b 手写公式失败) |  |
| exp40 | `exp40_real_connectome_vqc.py` | 192 | exp40: 真实果蝇连接组 VQC——真实 KC->MBON 突触权重 vs exp39 随机连接 |  |
| exp40b | `exp40b_real_connectome_3layer.py` | 208 | exp40b: 真实连接组 VQC 16 qubit 三层版——修复二部布局缺陷 |  |

## D. 线虫与进化线（exp41–50）  
*真实连接组 / 进化家族 / 社会 / 生存*

| exp | 文件 | 行数 | 摘要（首行 docstring） | 探针 |
|---|---|---|---|---|
| exp41 | `exp41_worm_hopfield.py` | 155 | exp41: 全规模线虫 Hopfield——279x279 真实连接组做联想记忆 |  |
| exp41b | `exp41b_worm_attractors.py` | 137 | exp41b: 线虫连接组自发吸引子——真实结构的"行为守则"实证 | probe8/9 |
| exp42 | `exp42_worm_evolution.py` | 231 | exp42: 线虫进化实验——基因型(10基因)调制真实连接组,股市为自然选择环境 | probe11/17/19 |
| exp43 | `exp43_worm_market_evolution.py` | 206 | exp43: 线虫进化 v2——生存环境=整个股市(多股票组合),非单只股票 |  |
| exp44 | `exp44_worm_society_evolution.py` | 276 | exp44: 线虫社会进化——环境+基因+社会三重复杂化 + 环境极限测试 | probe20 |
| exp45 | `exp45_worm_forced_flow.py` | 223 | exp45: 胁迫环境——现金税逼迫经济流动(用户构想) | 补跑#1 |
| exp46 | `exp46_worm_reproduction.py` | 253 | exp46: 线虫繁殖进化——连续世代种群动态(用户三方向:繁殖/残酷筛选/环境+基因多样性) | probe18 |
| exp47 | `exp47_worm_survival_consumption.py` | 292 | exp47: 生存消费机制逼迫经济流动 + 繁殖即清算(exp45结论 + exp46修正) | 补跑#2 |
| exp48 | `exp48_gene_regulation_evolution.py` | 298 | exp48: 真实基因结构进化——染色体/调控基因/结构变异/发育映射 | probe21 |
| exp49 | `exp49_quantum_mutation_evolution.py` | 338 | exp49: 量子遗传变异——量子信道变异算子 vs 经典变异(量子线 x 线虫进化线交叉) | 补跑#4 |
| exp50 | `exp50_worm_trading.py` | 298 | exp50: 线虫炒股——训练段进化,测试段(2021-2026真未来)实盘对比 |  |

## E. 角色模拟线（exp51–60）  
*角色漂移 / GRN / Concordia / 协方差 —— ⚠️ 尚未被探针覆盖*

| exp | 文件 | 行数 | 摘要（首行 docstring） | 探针 |
|---|---|---|---|---|
| exp51 | `exp51_role_drift_chat.py` | 260 | exp51: 角色参数漂移系统——虚拟角色群聊模拟（ZH 候选立项实验验证） |  |
| exp51b | `exp51b_multi_seed.py` | 28 | exp51b: 多 seed 稳定性验证——5 个 seed 重复对照 |  |
| exp52 | `exp52_quantum_drift.py` | 310 | exp52: 角色参数漂移的量子变异对照——Qiskit 量子信道算子 vs 经典高斯漂移 |  |
| exp53 | `exp53_genome_drift.py` | 318 | exp53: 角色参数漂移——性格基因组版(调控-表达两层结构) × 量子信道对照 |  |
| exp53b | `exp53b_select_drift.py` | 132 | exp53b: 性格基因组 + 选择压力——量子信道完整复刻(exp49 条件齐) |  |
| exp54 | `exp54_grn_drift.py` | 351 | exp54: 三层 GRN 性格基因组 + 关系记忆群聊——复杂度第三级 |  |
| exp55 | `exp55_forward_draft.py` | 286 | exp55: 前向 rollout 草稿评分——角色发言前先推演"我这么说对方怎么反应" |  |
| exp56 | `exp56_narrative_push.py` | 239 | exp56: 叙事推力注入——场景事件驱动角色生长(Concordia maybe_inject_narrative_push 验证) |  |
| exp57 | `exp57_reflection_cadence.py` | 221 | exp57: 固定反思节拍——行动前 5 个固定感知问题(Concordia QuestionOfRecentMemories 验证) |  |
| exp58 | `exp58_event_causal.py` | 220 | exp58: 事件因果化——Event → 因果句 → 广播相关者(Concordia 验证 3/3) |  |
| exp59 | `exp59_precision_mod.py` | 193 | exp59: pymdp 精度调制——动态 gamma(注意力×置信度调制回复确定性) |  |
| exp60 | `exp60_integration.py` | 428 | exp60: 三合一协同模拟——参数漂移 + 叙事推力 + 反思节拍（exp51/56/57 集成验证） |  |
| exp60b | `exp60b_covariance_drift.py` | 290 | exp60b: 协方差矩阵漂移——参数相关性感知的角色漂移（lmq"矩阵化空间"直觉验证） |  |
| exp60c | `exp60c_self_covariance.py` | 281 | exp60c: 自我认知协方差——每角色独立的"自我环"矩阵（exp57 自我认知 × exp60b 矩阵化） |  |

## 二、探针清单（math_probe/，21 个）

| # | 对象 | 一句话结论 |
|---|---|---|
| probe1 | exp29 | 数学体检：策略无关性（31 天留存只依赖次数不依赖分布） |
| probe2 | exp37 | 修正模型验证：间隔效应出现（补上 F12.6 量化对拍教训） |
| probe3 | exp31 | 身份查明：「Grover 式放大」= softmax 温度采样 |
| probe4 | salience | salience 加权 Hopfield SNR：低负载有害 / 高负载有益（交叉结构） |
| probe5 | exp37 | 张量网络压缩：谱结构 + r 拐点（三方逐位对拍 max_diff=0） |
| probe6 | 秩扫描 | 高秩对话下低秩压缩的三重退化 |
| probe7 | exp30 | 「纠缠熵」= 加权共现计数（三层鉴定 + 词袋边界） |
| probe8 | exp41b | 线虫自发吸引子：95% 的「收敛」不是不动点 + 子网全枚举 |
| probe9 | exp41b | ±1 反对称引理与配对统计（含 probe8 结论自我修正） |
| probe10 | exp32 | 量子退火欲望：假退火（常量 ΔE）/「冻结」不存在 / 空转是唯一的罪 |
| probe11 | exp42 | 线虫进化「撞墙者」：scal_back 钉死下界 / scal_fwd 贴上界（玩具判决 = 界外最优） |
| probe12 | 连接组 | 场论第一枪：Ising 化 χ 峰 β_c≈0.5 + exp31 热力学（转变带 β≈2） |
| probe13 | 连接组 | 复分析线：谱半径审计（0.85 = 2.4× 超临界）+ Lee-Yang 零点（嵌套设计） |
| probe14 | exp36 | 对抗随机性审计：对手是 stub / 滑点反向 / 随机性只影响 0.15% 行为 |
| probe15 | exp34 | QSNN：量子测量被 softmax 换芯 / 50.6% 语义空白 / 梯度死区 |
| probe16 | exp27/28 | 检索多样性：公平对照下「量子信道更划算」反转 + gap 标度判据（σ 甜点带 2-4×） |
| probe17 | exp42-49 | 进化家族体检：谱系三代 / 完成度 2/9（后修正为「无存档设计」）/ society 选择失效 |
| probe18 | exp46 | 资产失控追查：跨世界估值跳变（P(>40)=15%）× 截断棘轮 |
| probe19 | exp42 | 挪墙实验：方向信号在、n=1 证据不足（噪声 300% vs 效应 30%） |
| probe20 | exp44 | society 负值化：修好「选择失效」、未修好「选择信号」 |
| probe21 | exp48 | 极限环定案：振荡是「繁殖过滤器」的投影（交易层平稳 41-66%） |

## 三、覆盖缺口（2026-10-08 状态）

- **角色模拟线（exp51–60c）尚未被探针覆盖**——该线含漂移/GRN/Concordia 等 12+ 实验；
- 探针主要在 B/C/D 三线（噪声 / 记忆 / 进化），A 线（交易基础）仅 exp29/31/37 被审过；
- 补跑六连（exp45/47/44/46/48/49）已全部完成，输出留档于 `py_exp*_output.txt`。
