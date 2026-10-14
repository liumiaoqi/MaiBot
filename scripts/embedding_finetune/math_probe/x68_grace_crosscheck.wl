(* x68_grace_crosscheck.wl —— s5.5 主量复算：从计数 CSV 独立重算 noise/hit 率
   Run: wolframscript -file x68_grace_crosscheck.wl *)

csv = Import["E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x68_grace_aggregate.csv", "CSV"];
rows = Rest[csv];

Print["=== x68: s5.5 rate cross-check (from counts) ==="];
Print[StringPadRight["G", 6], StringPadRight["noise_rate", 14], "hit_rate"];
Do[
  g = ToExpression[rows[[i, 1]]]; nt = ToExpression[rows[[i, 2]]];
  ht = ToExpression[rows[[i, 3]]]; tot = ToExpression[rows[[i, 4]]];
  Print[StringPadRight[ToString[g], 6],
        StringPadRight[ToString[NumberForm[N[nt/tot], 6]], 14],
        NumberForm[N[ht/tot], 6]],
  {i, 1, Length[rows]}];
Print["(compare python grace_period_output.txt: 0.7092 0.6220 0.5256 0.4380 0.2672 / 0.2908 0.3780 0.4744 0.5620 0.7328)"];
