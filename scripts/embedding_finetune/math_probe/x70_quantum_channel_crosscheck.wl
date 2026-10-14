(* x70_quantum_channel_crosscheck.wl —— s5.7 主量复算：从计数 CSV 独立重算三臂率
   Run: wolframscript -file x70_quantum_channel_crosscheck.wl *)

csv = Import["E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x70_quantum_channel_counts.csv", "CSV"];
rows = Rest[csv];
K = 5;

Print["=== x70: s5.7 rate cross-check (from counts) ==="];
Print[StringPadRight["arm", 6], StringPadRight["noise_rate", 14], StringPadRight["hit_rate", 12], "diff_slot_hit"];
Do[
  arm = rows[[i, 1]];
  noise = ToExpression[rows[[i, 2]]]; hit = ToExpression[rows[[i, 3]]];
  kept = ToExpression[rows[[i, 4]]];
  dh = ToExpression[rows[[i, 5]]]; dt = ToExpression[rows[[i, 6]]];
  nq = ToExpression[rows[[i, 7]]];
  nRate = If[kept*K > 0, N[noise]/(kept*K), 0.];
  hRate = N[hit]/(nq*K);
  dRate = If[dt > 0, N[dh]/dt, 0.];
  Print[StringPadRight[ToString[arm], 6],
        StringPadRight[ToString[NumberForm[nRate, 6]], 14],
        StringPadRight[ToString[NumberForm[hRate, 6]], 12],
        NumberForm[dRate, 6]],
  {i, 1, Length[rows]}];
Print["(compare python: a 0.5256/0.4744/- - b 0.4448/0.5552/1.0 - c 0.3580/0.6420/0.996)"];
