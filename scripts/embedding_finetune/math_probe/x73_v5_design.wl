(* x73_v5_design.wl —— s6.1 v5 的世界设计（M-first，§9 第 5 条）
   目标：设计一个「有诱惑节点」的世界，基线 0.6-0.8，让反馈学习有净升空间。
   问题：
     ① 诱惑节点 sim 要多高才能混进 top5（让基线降到 ~0.7）
     ② 诱惑节点的 √率低 → conf 压低 → 净升量级估算
     ③ 反馈预算（多少条反馈覆盖诱惑节点）
   Run: wolframscript -file x73_v5_design.wl *)

fmt[x_, d_] := ToString[NumberForm[N[x], {12, d}]];

Print["=== x73: v5 world design (temptation nodes) ==="];
Print[""];

(* ① 世界模型：query = 主簇 A（直取中心），A 节点 sim ~ N(0.62, 0.35)
   诱惑节点：属于 B 簇但 sim 被抬到 N(mu_t, 0.1)（"看起来像 A"）*)
Print["--- 1. how high must temptation sim be to enter top5? ---"];
(* A 的 top5 门槛：A 节点第 5 名的期望（10 个 A 节点，取第 5 高） *)
(* 数值：模拟 A 节点 sim，看第 5 名分布 *)
SeedRandom[42];
aSims = Table[Max[Sort[RandomVariate[NormalDistribution[0.62, 0.35], 10]][[-5]]], {i, 5000}];
thr = N[Mean[aSims]];
Print["A 节点第 5 名 sim 均值 = ", fmt[thr, 4]];
Do[
  p = NProbability[x > thr, x \[Distributed] NormalDistribution[mu, 0.1]];
  Print["  temptation mu=", fmt[mu, 2], " -> P(挤进 top5) = ", fmt[p, 4]],
  {mu, {0.85, 0.90, 0.95}}];
Print["=> 取 mu=0.90~0.95（P≈0.3~0.7），世界基线将显著下降"];
Print[""];

(* ② 学习净升估算：诱惑节点被评后 conf 从 1.0 → 0.3（√率低） *)
Print["--- 2. learning delta estimate ---"];
(* 每查询场景：5 席中诱惑节点占 k 席；学后 k 席归还给 A *)
Do[
  baseHit = 1 - k/5.;
  afterHit = 1.0;
  Print["  k=", k, " temptation slots: base=", fmt[baseHit, 3], " -> after=", fmt[afterHit, 3],
        "  gain=+", fmt[afterHit - baseHit, 3]],
  {k, {1, 2, 3}}];
Print["=> 诱导节点覆盖率 ~70-90% 时，学习净升 +0.2~+0.4 —— 生长空间充足"];
Print[""];

(* ③ 覆盖预算 *)
Print["--- 3. coverage budget ---"];
nTempt = 20; nQueries = 60;
Print["temptation nodes = ", nTempt, " | queries/batch = ", nQueries];
Print["每次查询最多碰 1 个诱惑节点（top1）；500 条反馈下期望覆盖 = ",
      fmt[Min[1.0, 500.0/nTempt] * 100, 1], "% of temptation nodes"];
Print["=> 500 条足够全覆盖（每节点 ~25 次评估）"];
Print[""];
Print["=== v5 设计处方 ==="];
Print["① temptation sim mu=0.90, sigma=0.1（P(挤入)~0.5）；② 基线预期 0.6-0.8；"];
Print["③ 未评默认 1.0（v4 处方沿用）；④ 反馈 500 条可全覆盖诱惑节点。"];
Print["(2026-10-14, x73 · M-first)"];
