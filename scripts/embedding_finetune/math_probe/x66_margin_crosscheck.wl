(* x66_margin_crosscheck.wl —— s5.3 主量复算（§9 约定）
   读 python 导出的 CSV（全量 200 行），独立重算：
     ① base 错误率  ② 分位网格下的（错误拦截率, 保留率）
   与 python 输出逐点对照（预期：分位定义一致时逐点相等）。
   Run: wolframscript -file x66_margin_crosscheck.wl *)

fmt[x_, d_] := ToString[NumberForm[N[x], {12, d}]];

csv = Import["E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x66_margin_sample.csv", "CSV"];
rows = Rest[csv];
margins = N[rows[[All, 1]]];
corrects = rows[[All, 2]];
nTot = Length[margins];
totalErr = Count[corrects, 0];

Print["=== x66: s5.3 margin 主量复算 ==="];
Print["n = ", nTot, " | base 错误率 = ", fmt[(nTot - Total[corrects])/nTot, 6],
      " | errors = ", totalErr];
Print[""];
Print[StringPadRight["θ(分位)", 10], StringPadRight["拦截率", 12], "保留率"];
Do[
  th = Quantile[margins, q];
  rejMask = MapThread[#1 < th &, {margins}];
  rejPairs = Pick[Transpose[{margins, corrects}], rejMask];
  errsRej = Count[rejPairs[[All, 2]], 0];
  keepRate = (nTot - Length[rejPairs])/nTot;
  Print[StringPadRight[fmt[q, 1], 10],
        StringPadRight[fmt[If[totalErr > 0, errsRej/totalErr, 0]*100, 4] <> "%", 12],
        fmt[keepRate*100, 4] <> "%"],
  {q, 0.1, 0.9, 0.1}];
Print[""];
Print["(对照 python 侧 margin_decision_output.txt 同分位点)"];
