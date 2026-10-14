(* x77_integrated_recheck.wl — §9 main-quantity recheck for s7.1
   (growth feedback x integrated system, x76_growth_integrated_rounds.csv)

   Recompute per-arm mean hit/noise over the 10 rounds and compare with the
   python-printed totals (python totals are slot-weighted; each round has
   exactly 250 slots per arm -> uniform mean == weighted mean).
   Output plain text (pipe-safe). *)

path = "E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x76_growth_integrated_rounds.csv";
raw = Import[path, "CSV"];
header = First[raw];
data = ToExpression[Rest[raw]];
cols = Transpose[data];        (* round, hit_a, noise_a, hit_b, noise_b, hit_c, noise_c *)
names = header;
fm[x_] := ToString[NumberForm[N[x], {4, 4}]];

Print["=== x77: independent recomputation from x76 CSV ==="];
Print["columns: ", names];
Print["rounds: ", Length[data]];
Print[];
Print["col       round-mean   (python total)"];
py = <|"hit_a" -> 0.4744, "noise_a" -> 0.5256, "hit_b" -> 0.8048,
   "noise_b" -> 0.1952, "hit_c" -> 0.8312, "noise_c" -> 0.1688|>;
Do[
  col = cols[[j + 1]];   (* skip round column *)
  m = Mean[col];
  diff = N[m - py[names[[j + 1]]]];
  Print[names[[j + 1]], "   ", fm[m], "   (", fm[py[names[[j + 1]]]],
   ")   diff ", ToString[NumberForm[diff, {5, 4}]]];
  , {j, 6}];
Print[];
(* spot check: first and last rounds *)
Print["round-0 row: ", Row[fm /@ Rest[data[[1]]], "  "]];
Print["round-9 row: ", Row[fm /@ Rest[data[[10]]], "  "]];
Print[];
(* growth contrast: late vs early (rounds 7-9 mean vs rounds 2-3 mean) *)
Do[
  col = cols[[j + 1]];
  early = Mean[col[[3 ;; 4]]];
  late = Mean[col[[8 ;; 10]]];
  Print[names[[j + 1]], ": rounds 2-3 mean ", fm[early], "  ->  rounds 7-9 mean ", fm[late]];
  , {j, 6}];
Print["(2026-10-14, x77 for s7.1)"];
