(* x69_integrated_crosscheck.wl —— s5.6 主量复算：从计数 CSV 独立重算三臂率
   Run: wolframscript -file x69_integrated_crosscheck.wl *)

csv = Import["E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x69_integrated_counts.csv", "CSV"];
rows = Rest[csv];
K = 5;

Print["=== x69: s5.6 rate cross-check (from counts) ==="];
Print[StringPadRight["arm", 6], StringPadRight["noise_rate", 14], StringPadRight["hit_rate", 12], "reject%"];
Do[
  arm = rows[[i, 1]];
  noise = ToExpression[rows[[i, 2]]]; hit = ToExpression[rows[[i, 3]]];
  kept = ToExpression[rows[[i, 4]]]; rej = ToExpression[rows[[i, 5]]];
  nq = ToExpression[rows[[i, 6]]];
  nRate = If[kept*K > 0, N[noise]/(kept*K), 0.];
  hRate = N[hit]/(nq*K);
  rRate = 100.0*N[rej]/nq;
  Print[StringPadRight[ToString[arm], 6],
        StringPadRight[ToString[NumberForm[nRate, 6]], 14],
        StringPadRight[ToString[NumberForm[hRate, 6]], 12],
        NumberForm[rRate, 5]],
  {i, 1, Length[rows]}];
Print["(compare python: a 0.7092/0.2908/0 - b 0.5256/0.4744/0 - c 0.5286/0.4252/9.8)"];
