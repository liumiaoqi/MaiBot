(* x67_hebbian_crosscheck.wl —— s5.4 主量复算：CSV 重算两个 Spearman（独立手写秩相关）
   Run: wolframscript -file x67_hebbian_crosscheck.wl *)

csv = Import["E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x67_hebbian_sample.csv", "CSV"];
rows = Rest[csv];
freq = rows[[All, 1]];
coact = rows[[All, 2]];
rel = rows[[All, 3]];

rho[a_, b_] := Module[{ra, rb, n, mr, mb},
  n = Length[a];
  ra = N[Ordering[Ordering[a]]];
  rb = N[Ordering[Ordering[b]]];
  mr = Mean[ra]; mb = Mean[rb];
  Total[(ra - mr) (rb - mb)] / Sqrt[Total[(ra - mr)^2] * Total[(rb - mb)^2]]
  ];

Print["=== x67: s5.4 Spearman cross-check (n=" <> ToString[Length[freq]] <> ") ==="];
Print["rho_freq  = ", NumberForm[rho[freq, rel], 6]];
Print["rho_coact = ", NumberForm[rho[coact, rel], 6]];
Print["(对照 python 侧 hebbian_strength_output.txt 主档：0.8381 / 0.8122)"];
