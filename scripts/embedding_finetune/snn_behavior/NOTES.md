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

---

## `flywire_data/` 的渠道（2026-09-27 实测 —— lmq 问「果蝇的渠道」）

> ⚠️ 先答一句：「**能从线虫那个地方下吗**」⇒ **不能**。线虫那份来自 **Neural Interactome**，
> 那是**线虫专属**项目（整个项目就是那 302/279 个神经元），**没有果蝇**。
> 果蝇走的是**另一套渠道** —— 而且**我们早就在用了**。

### 手上这份是怎么来的

`fetch_flywire_mb.py` / `_probe_rel.py` 用的就是 **`neuprint.janelia.org` 的 Cypher API**，
里面**硬编码**了 dataset：**`hemibrain:v1.2.1`**（2020 年的**雌性半脑**）
⇒ `flywire_data/` 那 2464 神经元 / 76 061 边**就是从渠道拉的**，不是别人给的。

### ⭐ 想要「完整果蝇」：**换 dataset 名，一字之改**

| | |
|---|---|
| 现在 | `dataset='hemibrain:v1.2.1'`（雌性半脑，2020） |
| **完整雄性 CNS** | ⭐ **`dataset='male-cns:v1.0'`**（2026-09-03 发布；脑＋视叶＋腹神经索，166 691 神经元 / ~1.25 亿突触） |

token、Cypher 查询、`fetch_adjacencies` 全都不用改。
官方建议用 **`neuprint-python`**：`Client("https://neuprint.janelia.org", dataset='male-cns:v1.0', token=token)`。

### 免登录直链（2026-09-27 `curl -I` 实测，均 **HTTP 200**）

基址 `https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome/`

| 文件 | 实测大小 | 是什么 |
|---|---|---|
| `body-annotations-male-cns-v1.0-minconf-0.5.feather` | **13.8 MB** | 注释：类别 / 类型 / 左右侧 |
| ⭐ `body-neurotransmitters-male-cns-v1.0.feather` | **41.3 MB** | ⭐⭐ **每个神经元的递质预测** —— **正好补上我们这份缺的"极性/递质"** |
| `connectome-weights-male-cns-v1.0-minconf-0.5.feather` | **1002.5 MB** | **完整 CNS 的连接图**（"线虫式矩阵"的对应物） |
| `syn-partners-male-cns-v1.0-minconf-0.5.feather` | **6463.2 MB** | 突触配对（**不建议下**） |

（另有 `tbar-neurotransmitters` 2.7 GB · `syn-points` 12.7 GB · 骨架 SWC · 供自建 neuprint 的 neo4j 库）

⚠️ **别全量下** —— 光连接表就 1 GB、突触表 6.5 GB 起。
**正解 = 在 neuprint 上只拉子图**（= 我们原来拉蘑菇体子图的做法）＋ **那两个小表直接下**。

### 其它入口（Janelia 官方页，2026-09-27 读）

MaleCNS 站点 `janelia-flyem.github.io/male-cns/` · Cell Type Explorer · **Clio** · **Neuroglancer**
（standalone 场景含 segmentation/synapses/neuropil）· **Virtual Fly Brain**
预印本 DOI **`10.1101/2025.10.09.680999v2`**（Janelia 页给的；另有 *Cell* 版）
**许可 CC-BY 4.0** ⇒ 注明出处即可。

### ⭐ 由此得到的一条可做动作

`body-neurotransmitters-male-cns-v1.0.feather`（41 MB，免登录）
＋ 用 `male-cns:v1.0` **重拉一次蘑菇体子图**
⇒ 就得到「**完整雄性果蝇里、带兴奋/抑制极性的蘑菇体**」
—— 而不是现在这份 2020 hemibrain 的、**没有极性**的切片。
