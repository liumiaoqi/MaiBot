# exp0 实验笔记：LIF 神经元基础

> 最后更新：2026-08-17
> 目的：亲手摸到脉冲神经元（事件驱动/泄漏/阈值放电）与普通神经网络的差别
> 脚本：snn_behavior/exp0_lif_basics.py

## 三件事（本轮学会）

1. **事件驱动**：输入弱（0.2）→ 静默不放电；输入强（1.2）→ 稳定放电——有输入才算，没输入不干活
2. **泄漏（beta）**：beta=0.5 忘得快、beta=0.99 记得久——遗忘曲线的微观机制（对应 lab/forgetting_curve）
3. **阈值放电**：膜电位累积 → 超阈值 → 输出脉冲 → 复位——计算的最小单元

## 下一步（候选）

- exp1：Braitenberg 车辆（2 传感器 + 2 马达，趋光/避光涌现）
- exp2：STDP 可塑性（越用越熟——积累性）
- exp3：嗅觉趋避（果蝇级）

## 与认知的对应

- 神经元六机制：事件驱动 ✅（exp0a）、积累/遗忘 ✅（exp0b）、独立性（exp1 多神经元）
- 浙大线虫启示：302 神经元就能涌现行为——我们的起点远高于它（exp1 就 4 个神经元）

## exp2 迭代记录（真实教学：三次失败→一次成功）

| 版本 | 机制 | 结果 | 教训 |
|------|------|------|------|
| exp2 v1 | 连续值 STDP | 权重不变（稳态数学抵消） | STDP 必须是脉冲+事件驱动 |
| exp2 v2 | 事件驱动 STDP | 权重会动但学不到（车辆2 强化错误模式/车辆3 从不放电） | 无监督 Hebbian 不认"好坏" |
| exp2b v1 | R-STDP 连续奖励 | 全没学会（确定性环境无探索，reward≈0） | 需要探索-利用平衡 |
| **exp2b v2** | **R-STDP 符号奖励 + 探索噪声** | **车辆1 学会（0.20）/ 车辆3 靠近（4.64）** | **探索 + 明确好/坏信号 = 学习成立** |

**结论链**：脉冲化（事件驱动）→ 奖励调制（三因子）→ 探索噪声（强化学习雏形）——三步缺一不可。
**呼应**：欲望驱动学习 = R-STDP 的全局奖励——MaiBot 欲望系统（想靠近想要的东西）的微观机制。

---

## 数据来源（2026-09-27 核实 —— lmq：「记得是在一个网站上获得的」）

> ⭐ 这条此前**只记在引入那次提交的信息里**（`45a5482e7`，2026-08-19，`[dsh]`：
> 「线虫全连接组——279x279化学突触2217边+电突触1065边(Varshney2011,全规模不用压缩)」）
> ⇒ 主题 NOTES 里一直没有。2026-09-27 补齐并**坐实到具体来源**。

### 来源：C. elegans **Neural Interactome**

| 项 | 内容 |
|---|---|
| 是什么 | 交互式仿真平台 —— **实时给神经元注电流**(stimuli injection)、看网络动力学 |
| 网页版（= lmq 记忆里的"那个网站"） | `http://neuralcode.amath.washington.edu/neuralinteractome` |
| 仓库 | `https://github.com/shlizee/C-elegans-Neural-Interactome` |
| 论文（**引用用这篇**） | Kim J, Leahy W, Shlizerman E. *Neural Interactome: Interactive Simulation of a Neuronal System.* **Front. Comput. Neurosci. 2019** · DOI `10.3389/fncom.2019.00008` |

⭐ **判定依据：文件名逐一相同** —— 该仓库根目录同时有 **`Gg.npy` · `Gs.npy` · `chem.json` · `gap.json`**
（另有 `emask.npy` · `neuron_names.txt`），与 `worm_data/` 下四个文件**名字完全对应**
⇒ 不是"同款数据"，是**同一来源**。
⭐ **交叉印证**：`chem.json`/`gap.json` 的节点字段带 **`inputCurrent` · `voltage`** ——
正是该平台"注电流"界面的状态字段（普通连接组数据不会有这两个字段）。

### 实测（`worm_data/_verify.py`，2026-09-27 落地在此）

```
Gs(化学突触) (279, 279) | 非零边 2217 | 权重和 6607
Gg(电突触)   (279, 279) | 非零边 1065 | 权重和 1840
```

⭐ **279 是正常的、不是缺数据**：Varshney 2011 的**躯体**连接组就是 279 ——
302 个神经元 = 20 咽部 + 282 躯体；躯体里再排除 **CANL/R 与 VC6**（这三个不与其它神经元成突触）
⇒ **282 − 3 = 279** ✓

⚠️ **两处口径要注意（未定案）**：

1. 我们记的是 **"Varshney2011"**，但该仓库 **v3（2020-10）自述**：
   *"Updated connectomes **according to Haspel et al.**"* ⇒ **版本口径可能不一致**，
   要严谨引用就得核清手上这份是"Varshney 版"还是"Haspel 更新版"。
2. ⚠️ **引用义务**：仓库明写
   *"**The paper has to be cited in any use or modification of the dataset or the code.**"*
   ⇒ 用到这份数据/代码，**要引 Neural Interactome 那篇（2019）**，不能只提 Varshney。

⚠️ 读 `.npy` 时 numpy 报 *"created on Python 2"*：与该仓库 2017-02 那次
「**Converted all `.mat` files into `.npy`**」的提交吻合（**推断**，非定案）——旧式 `.npy` 头所致，**不影响取值**。
