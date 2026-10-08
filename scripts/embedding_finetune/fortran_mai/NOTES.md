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

## 梗

- 「公式是 1957 年的，指数衰减是 2026 年的」
- 数组一行流 `e = b + (e-b)*exp(-rate*1.0)` —— Fortran 的数学基因（比 NumPy 早 30 年）
- 后续候选（✅ 方案③ exp29 已完成）：**方案②** f2py 接入 A_memorix（扩散激活内核）·
  **方案②** f2py 接入 A_memorix（扩散激活内核）· **fpm 版**（「用 2026 年的包管理器装 1957 年的语言」）
