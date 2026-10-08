(* probe16_gap_theory.wls -- exp27 的「间隔标度」分析：
   分数池 N(0.5,0.12)（500 项）的 top-8 边界 gap 谱 + 标度律对照表。
   目的：给「扰动强度该多大」一个解析判据（sigma / gap 计数）。
   数据来源：probe16_pareto.py 的 sigma 扫描（见 wl16 输出对照）。
   Run: wolframscript -file probe16_gap_theory.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {16, d}]];

mu = 0.5; sg = 0.12; n = 500;

(* 解析：正态顺序统计量期望 = mu + sg * InverseCDF[1 - j/(n+1)] *)
es[j_] := mu + sg*InverseCDF[NormalDistribution[], 1.0 - j/(n + 1)];

Print["=== probe16: gap scale theory (N(0.5,0.12), n=500, top-8) ==="];
Print["--- expected score ladder near top-8 ---"];
Do[Print["s_", j, " ~ ", fmt[es[j], 4]], {j, 6, 12}];
Print["--- expected adjacent gaps ---"];
Do[Print["gap_", j, " = ", fmt[es[j] - es[j + 1], 5]], {j, 6, 10}];

Print["--- numeric check: empirical gaps (mean over 60 draws) ---"];
SeedRandom[7];
gapdraws = Table[
   srt = Reverse[Sort[RandomVariate[NormalDistribution[mu, sg], n]]];
   Table[srt[[j]] - srt[[j + 1]], {j, 6, 10}],
   {60}];
Print["empirical gap_6..gap_10: ", Row[Map[fmt[Mean[#], 5] &, Transpose[gapdraws]], "  "]];

g8 = es[8] - es[9];
Print[""];
Print["gap_8 = ", fmt[g8, 5], "   (the boundary scale that governs top-8 swaps)"];

(* 标度律对照：probe16 的 gauss 扫描（sigma -> overlap 实测） *)
obs = {{0.005, 0.9343}, {0.01, 0.8894}, {0.02, 0.7589}, {0.05, 0.4572}, {0.1, 0.1953}, {0.2, 0.0657}};
Print[""];
Print["--- scale law: sigma / gap_8 vs observed overlap (gauss family) ---"];
Do[
  {s, ov} = pair;
  Print["sigma/gap_8 = ", fmt[s/g8, 2], "   sigma = ", s, "   overlap = ", ov],
  {pair, obs}];

Print[""];
Print["reading: sigma < gap -> overlap > 0.93 (barely disturbed);"];
Print["sigma ~ 2-4 x gap -> the sweet band (overlap 0.89-0.76, quality > 0.99);"];
Print["sigma > 10 x gap -> collapse (overlap < 0.2)."];
