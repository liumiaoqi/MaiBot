(* x79 — T1 对照笔记的量级复算（记忆-样本下界 ↔ s6.1 生长曲线）
   2026-10-15 WB · 服务：social_rel/proposals 任务书 T1
   口径：
     d          = 32（嵌入维数，最自然折算——只作量级，不作定理套用）
     T          = 500（s6.1 v8 反馈上限）
     状态       = 120 节点 × 2 计数（pos/tot），计数上限 500 ⇒ 每计数 bits = ceil(log2 500)
   输出关键量：d·ln(1/ε) 组 · M 与 M/d² · T/(d·ln(1/ε)) 比值组 *)

d = 32;
T = 500;
countsMax = 500;
nodes = 120;

b = Ceiling[Log2[countsMax]];
M = nodes*2*b;
Print["== x79: T1 magnitude recheck =="];
Print["bits per count (ceil(log2 500)) = ", b];
Print["M = ", M, " bits   |   M/d^2 = ", N[M/d^2, 4]];
Print[""];
Print["eps      d*ln(1/eps)      T/(d*ln(1/eps))"];
Do[
  Print[ToString[e], "      ", N[d*Log[1/e], 5], "      ", N[T/(d*Log[1/e]), 4]],
  {e, {0.3, 0.1, 0.03}}
];
Print[""];
Print["lower-bound scale c*d*ln(1/eps), eps=0.1, c=2..4: ", N[{2, 3, 4}*d*Log[1/0.1], 4]];
Print["ratio T / (c*d*ln(1/eps)) at eps=0.1: ", N[T/({2, 3, 4}*d*Log[1/0.1]), 3]];
Print["done."];
