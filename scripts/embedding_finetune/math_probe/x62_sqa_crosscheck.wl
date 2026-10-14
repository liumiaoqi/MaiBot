(* x62_sqa_crosscheck.wl —— exp62 的 SQA 交叉验证（独立实现，Wolfram 侧）
   ① 单比特横场 Ising(H = -h sz - G sx)：精确 <sz> = h/Sqrt[h^2+G^2]（符号）
   ② 独立 PIMC 实现：与精确 <sz> 对拍（验 exp62 算法健康性）
   ③ 双井量子版(4x4)：精确谱 —— 隧穿劈裂 Δ = E1 - E0
   Run: wolframscript -file x62_sqa_crosscheck.wl *)

fmt[x_, d_] := ToString[NumberForm[N[x], {12, d}]];

Print["=== x62: exp62 SQA cross-check (Wolfram, independent implementation) ==="];
Print[""];

(* ── ① 精确解：1 比特 TFIM，<sz> = h/Sqrt[h^2+G^2] ── *)
Print["--- 1. exact single-bit TFIM: <sz> = h/Sqrt[h^2+G^2] ---"];
Print["<sz>(h=0.5, G=1.0) = ", fmt[0.5/Sqrt[0.25 + 1.0], 8]];
Print[""];

(* ── ② 独立 PIMC（同 exp62 算法：P 片 + Jperp + 单自旋 Metropolis） ── *)
pimcMag[h_, G_, P_, T_, nSweeps_, seed_] := Module[{s, Jperp, dE, p},
  SeedRandom[seed];
  s = RandomChoice[{-1.0, 1.0}, P];
  Jperp = -0.5*P*T*Log[Tanh[G/(P*T)]];
  Do[
    Do[
      p = RandomInteger[{1, P}];
      dE = 2*h*s[[p]] + 2*Jperp*s[[p]]*(s[[Mod[p, P] + 1]] + s[[Mod[p - 2, P] + 1]]);
      If[dE <= 0 || RandomReal[] < Exp[-dE/T], s[[p]] = -s[[p]]],
      {P}],
    {nSweeps}];
  Mean[s]
  ];

Print["--- 2. independent PIMC <mean s> vs exact THERMAL <sz> (h=0.5, P=16, T=1.0, 2000 sweeps, 15 runs) ---"];
Print["exact thermal: <sz> = h*Tanh[Sqrt[h^2+G^2]/T]/Sqrt[h^2+G^2]"];
Print[StringPadRight["G", 8], StringPadRight["PIMC <s>", 14], StringPadRight["exact <sz>(T=1)", 16], "abs diff"];
Do[
  est = N[Mean[Table[pimcMag[0.5, G, 16, 1.0, 2000, s], {s, 1, 15}]]];
  ex = 0.5*Tanh[Sqrt[0.25 + G^2]/1.0]/Sqrt[0.25 + G^2];
  Print[StringPadRight[fmt[G, 2], 8], StringPadRight[fmt[est, 5], 14], StringPadRight[fmt[ex, 6], 16], fmt[Abs[est - ex], 5]],
  {G, {0.5, 1.0, 2.0}}];
Print["(if diffs are few-%, PIMC is healthy -> exp62 losses point to thermalization budget, not a bug)"];
Print[""];

(* ── ③ 双井量子版 4x4 精确谱：隧穿劈裂 ── *)
Ecl[s1_, s2_] := -2.0*s1*s2 + 0.4*(s1 + s2);
buildH[G_] := Module[{base, idx, H},
  base = {{-1, -1}, {-1, 1}, {1, -1}, {1, 1}};
  idx[s1_, s2_] := First@FirstPosition[base, {s1, s2}];
  H = ConstantArray[0.0, {4, 4}];
  Do[H[[i, i]] = Ecl @@ base[[i]], {i, 4}];
  (* 横场项：-G sx 翻单比特 *)
  Do[
    H[[idx @@ b, idx @@ {(-b[[1]]), b[[2]]}]] = -G;
    H[[idx @@ b, idx @@ {b[[1]], (-b[[2]])}]] = -G,
    {b, base}];
  H
  ];
Print["--- 3. double-well quantum spectrum (4x4): spectral gap E1-E0 ---"];
Print[StringPadRight["G", 8], StringPadRight["E0", 12], StringPadRight["E1", 12], "Delta = E1-E0"];
Do[
  ev = Sort[N[Eigenvalues[buildH[G]]]];
  Print[StringPadRight[fmt[G, 2], 8], StringPadRight[fmt[ev[[1]], 6], 12], StringPadRight[fmt[ev[[2]], 6], 12], fmt[ev[[2]] - ev[[1]], 6]],
  {G, {0.05, 0.2, 0.5, 1.0, 2.0}}];
Print["(classical barrier = +3.2; note E1 tracks the LOCAL minimum, not a tunneling partner — gap != tunneling splitting)"];
