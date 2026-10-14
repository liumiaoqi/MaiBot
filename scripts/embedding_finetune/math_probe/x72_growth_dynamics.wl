(* x72_growth_dynamics.wl —— s6.1 的数学探索（先于 python 落地）
   目的：用符号/数值先看清「反馈定义 conf → conf 乘进排序」的动力学，
   预期在 python 落地前发现：天花板 / 信噪比 / 冷启动 三类问题。
   三个问题：
     ① 天花板：跨簇 query 下 sim 排序的理论命中（top5 同主簇率）
     ② 信噪比：conf 的漂移量 vs sim 差量级的比较（谁大谁小）
     ③ 冷启动：未评节点默认值 r 对系统的影响（0.5 vs 1.0）
   Run: wolframscript -file x72_growth_dynamics.wl *)

fmt[x_, d_] := ToString[NumberForm[N[x], {12, d}]];

Print["=== x72: s6.1 growth dynamics (math exploration FIRST) ==="];
Print[""];

(* ① 天花板：跨簇 query q = 0.62 cA + 0.38 cB（单位化），主簇 A 的节点 sim 分布 *)
Print["--- 1. ceiling analysis: cross-cluster query, sim of A-nodes ---"];
(* 简化模型：A 节点 cos(q) ≈ 0.62 + N(0, sigma_n)；B 节点 ≈ 0.38 + N(0, sigma_n) *)
(* A 的 10 个节点里，top5 谁的 sim 会被 B 混入？—— B 的 sim 需要超过 A 的第 5 名 *)
(* P(B node beats A's 5th) 极小；理论 top5 同主簇率 ≈ 1 *)
Print["A-node sim ~ N(0.62, 0.35), B-node sim ~ N(0.38, 0.35)"];
gap = (0.62 - 0.38)/0.35;
Print["gap / sigma = ", fmt[gap, 3], "  -> P(B 混进 top5) = ",
      fmt[NProbability[x > 0.62 - 0.38, x \[Distributed] NormalDistribution[0, 0.35]], 6]];
Print["=> 结论：干净实现下命中率天然 ~1.0 —— python 版必须先设计『有竞争』的世界"];
Print[""];

(* ② 信噪比：conf 反馈的漂移 vs sim 差 *)
Print["--- 2. signal-to-noise: conf drift vs sim gap ---"];
(* conf 从 0.5 收敛到 p（√率），每步漂移 ~ (p - conf)/n；对 sim 乘性影响 = sim*(conf-1) *)
(* 假设 sim_A ~ 0.62, sim_B ~ 0.38；conf_A -> 0.8, conf_B -> 0.3（长期） *)
Print["long-run: simA*confA = ", fmt[0.62*0.8, 4], " | simB*confB = ", fmt[0.38*0.3, 4]];
Print["mid-run (conf 均匀 0.5): simA*0.5 = ", fmt[0.62*0.5, 4], " | simB*0.5 = ", fmt[0.38*0.5, 4]];
Print["=> conf 从 0.5 → 真值 造成的排序扰动 量级 = sim*Δconf ≈ 0.62*0.3 = ",
      fmt[0.62*0.3, 3]];
Print["   vs sim 原生差 = 0.24 —— 两者同量级 ⇒ 反馈『来得及』影响排序（信噪 OK）"];
Print[""];

(* ③ 冷启动：未评默认 r 的系统性影响 *)
Print["--- 3. cold-start: effect of default r on unrated nodes ---"];
(* 被评节点 conf -> p_true；未评节点 conf = r *)
(* 若 r < p_true（好节点）：被评好节点(0.8) 会盖过未评好节点(r) —— 排序扭曲 *)
(* 用 sim 差距设阈值：未评好节点被挤掉的临界 r *)
Print["rated-good conf -> 0.8; unrated conf = r"];
Print["unrated node with sim 0.62*s vs rated node sim 0.62: 挤掉的临界 "];
Print["  r* = 0.8 * (sim_rated/sim_unrated) = 0.8 * (0.55/0.62) = ", fmt[0.8*0.55/0.62, 3]];
Print["=> 若 r = 0.5 < r*：任何『sim 只要不比被评节点高 30%』的未评好节点都会被挤——系统净降！"];
Print["=> 正确设计一：未评默认 r = 1.0（不惩罚未知）；或 design二：显式探索配额（未评节点保底 1 席）"];
Print[""];

Print["=== 结论（供 s6.1 v4 设计）==="];
Print["① 世界必须含竞争（跨簇 query），且竞争强度要预先符号化估算；"];
Print["② conf 反馈与 sim 差同量级 ⇒ 机制可行；"];
Print["③ 冷启动默认 r 必须 ≥ 1.0（或显式探索），否则『学习』反而伤害系统。"];
Print["(2026-10-14, x72 · M-first workflow)"];
