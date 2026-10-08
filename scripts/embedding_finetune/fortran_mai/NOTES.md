# fortran_mai —— 「EmotionManager 被翻译回 1957」（整活原型）

> 起因：2026-10-08 lmq「maibot 可以用它（Fortran）实现点什么吗，就当整活」
> 定位：**纯整活实验**——不接生产、不碰 src/。检验目标：1957 年的语言能否**逐位复刻** 2026 年的情绪内核。

## 是什么

- `mai.f90`：把 `src/maisaka/agent/emotion.py` 的核心（7 情绪 × 指数衰减趋向基线 + 事件触发 clamp）
  用 Fortran 重写；tick = 1 小时；事件表硬编码（与 compare.py 逐条一致）；SELECT CASE 做情绪名映射
- `compare.py`：Python 复刻版对拍器——同公式、同事件表、同 tick——逐值对比

## 跑法

```bash
gfortran -O2 -o mai.exe mai.f90     # GNU Fortran 16.1.0 (WinLibs)
./mai.exe > out.txt
python compare.py
```

## 结果（2026-10-08）

- **对拍：rows=120 · values=840 · max_diff=0.000e+00 → PASS**
  —— 840 个双精度值**逐位一致**（gfortran 16.1 的 exp vs Python 3.14 的 math.exp，舍入路径一致）
- ⚠️ **实验小插曲（值得记）**：第一版对拍 CHECK（max_diff=4.993e-07）——查出来不是公式差，
  而是**输出精度 F12.6 的量化**（6 位小数 → 文本读回误差上限 5e-7，实测 4.993e-7 正好吻合）。
  输出提到 F22.15 后 diff 归零。
  ⇒ 教训：**对拍的分辨率不能超过输出的分辨率**——「文本往返精度」是对拍类实验的第一陷阱。

## 第二弹：exp29 复古复现（2026-10-08 同日）

- `exp29_forgetting.f90`：复刻 `trading/exp29_quantum_forgetting.py`——granular / 振幅阻尼 / 两能级（+间隔复习）
  四个模型 + Ebbinghaus 8 点线性插值拟合 MAE（照抄复刻，不修模型）
- **对拍：labels=24 · max_diff=6.106e-16 → PASS**（ulp 级——机器精度下的「逐位一致」）
- **关键数字复现**（与 2026 实验记录完全一致）：
  - 两能级 31 天留存 **8.56%**（vs granular 现状 27.48%）
  - 间隔复习（1/3/7/14 天）31 天留存 **111.33%**（越复习越强）
  - MAE：granular 0.43316 / 振幅阻尼 0.41652 / **两能级 0.17727**（2.4 倍优势）
- ⇒ 「用 1957 年的语言验证 2026 年的量子记忆实验」——成立。

## 第三弹：扩散激活 · C-ABI 内核（2026-10-08 同日）

- `spread.f90`：把 `src/A_memorix/core/connectionist/spreading_activation.py` 的 BFS 传播核心
  写成 **ISO_C_BINDING / `bind(c)` 的 C-ABI 内核**（导出符号 `spread_recall`），ctypes 直接调用
- `spread_demo.py`：**三路对拍**（python-loop / numpy-vec / fortran-cabi）
- `diag.py`：接口诊断——最小用例 → 真实规模，支持跨 `-fcheck` 调试版

**结果（n=2000, e=7996, depth=3, seeds=5）**

| 路线 | vs fortran max_diff | 耗时 |
|---|---|---|
| python-loop | **0.000e+00** | 390.6 ms |
| numpy-vec | 1.665e-16 | **0.60 ms** |
| fortran-cabi | ——（基准） | 1.04 ms |

激活节点 1036（`-fcheck=all` 调试版与 `-O2` 正式版交叉一致）。

⚠️ **Fortran 没赢**：内核是「边列表全扫描」O(frontier×E) 朴素实现（为保 C-ABI 零依赖），
而 numpy 是向量化折叠（`maximum.at`）——稀疏图 + 小 frontier 场景向量化更优。
改 CSR 邻接表会更快，但那就不是「零依赖可产出 DLL」的形态了。**如实记录，不吹。**

### 三个坑（按代价排序）

1. **`bind(c)` 无 `value` 的标量参数 = 按引用传参**（最贵的一课）
   Fortran 侧 `integer(c_int) :: n` 在 C 侧是 `int *n`；ctypes 按值传 `c_int` ⇒ gfortran 把
   数值 `3` 当指针解引用 ⇒ `access violation reading 0x3`（= n 的值，巧合得极具误导性）。
   修复：标量一律加 `value`，数组**不加**（数组本就传指针，合 C 习惯）。
   附带教训：早先「符号存在」的冒烟测试**根本没调用函数**，把这个问题瞒了一轮——**冒烟测试要真调一次**。
2. **CPython 3.8+ / Windows：`ctypes.CDLL` 裸文件名不搜索 CWD**
   `CDLL('spread.dll')` ⇒ FileNotFoundError；`CDLL('./spread.dll')` / 绝对路径 ⇒ OK
   （3.8 起的 DLL 安全加载变更：裸名走默认目录搜索，不含 CWD）。
   ⇒ demo 里一律用 `os.path.join(os.path.dirname(__file__), ...)` 拼路径。
3. **`-fcheck=all -fbacktrace` 会把 libgfortran 依赖带进 DLL**
   `-O2` 正式版把运行时全内联剔除（objdump 只见系统 DLL，**可裸加载**）；
   调试版依赖 `libgfortran-5.dll` 等 ⇒ 需 `os.add_dll_directory(gfortran 所在 bin)`。
   ⇒ 现象是「**调试版反而加载不了**」，别误判成编译坏了。

### 语义发现

原版 Python 在轮内 **in-place 更新** `activated`（结果依赖 set 迭代序 = 异步更新产物）；
本内核采用**轮初快照（同步语义）**——序无关、可复现。三路对拍统一定义在同步语义上跑。

## 梗

- 「公式是 1957 年的，指数衰减是 2026 年的」
- 数组一行流 `e = b + (e-b)*exp(-rate*1.0)` —— Fortran 的数学基因（比 NumPy 早 30 年）
- 「1957 年的语言，2026 年的 ABI」——`bind(c)` 是把 1957 接进 ctypes 的时光机（附送三个坑）
- 后续候选：**fpm 版**（「用 2026 年的包管理器装 1957 年的语言」）
- ✅ 已完成：第一弹（情绪内核）· 第二弹（exp29 复古复现）· 第三弹（扩散激活 C-ABI）
