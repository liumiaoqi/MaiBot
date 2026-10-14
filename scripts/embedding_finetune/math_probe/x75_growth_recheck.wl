(* x75_growth_recheck.wl — §9 main-quantity recheck for s6.1 v8
   (all-rejection quality sweep, x71_growth_batches.csv)

   Part 1: read x71 CSV, independently recompute gains and late-means.
   Part 2: edge-balance algebra for the dilution symmetry point:
     a correct node in a display with k true candidates gets local
     signal rate pu/k; tempters (n_t of them in display) absorb
     (1-pu)/n_t. Local edge favors correct nodes iff
        pu/k > (1-pu)/n_t   <->   pu > k/(k+n_t).
     k* = pu*n_t/(1-pu) is the largest k where the local edge holds.
   Output English only; plain-text tables via ExportString. *)

path = "E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x71_growth_batches.csv";
raw = Import[path, "CSV"];
header = First[raw];
data = ToExpression[Rest[raw]];
cols = Transpose[data][[2 ;;]];   (* skip the feedback column *)
names = Rest[header];
fm[x_] := ToString[NumberForm[N[x], {4, 3}]];

Print["=== x75 part 1: independent recomputation from x71 CSV ==="];
Print["columns: ", names];
Print["col    start    last     gain     late-mean"];
Do[
  col = cols[[j]];
  Print[names[[j]], "   ", fm[First[col]], "   ", fm[Last[col]], "   ",
   fm[Last[col] - First[col]], "   ", fm[Mean[Take[col, -4]]]];
  , {j, Length[cols]}];
Print[];
late = Mean[Take[#, -4]] & /@ cols;
mono = And @@ Table[late[[j]] >= late[[j + 1]] - 0.02, {j, Length[late] - 1}];
Print["late-means: ", Row[fm /@ late, " >= "]];
Print["quality-monotone (tol 0.02): ", If[mono, "CONFIRMED", "VIOLATED"]];
Print[];

Print["=== x75 part 2: edge algebra (local-signal symmetry point) ==="];
Print["condition for correct-node edge: pu/k > (1-pu)/n_t  <=>  pu > k/(k+n_t)"];
Print[];
Print["critical pu for candidate-grid (row = #true k, col = #tempter n_t):"];
grid1 = Prepend[
   Table[Prepend[Table[N[k/(k + nt)], {nt, {1, 2}}], k], {k, {3, 4, 5}}],
   {"k-n_t", 1, 2}];
Print[ExportString[grid1, "Table"]];
Print["largest locally-advantaged k at each pu (k* = pu*n_t/(1-pu)):"];
grid2 = Prepend[
   Table[Prepend[Table[N[pu*nt/(1 - pu)], {nt, {1, 2}}], pu],
     {pu, {0.9, 0.8, 0.7, 0.59}}],
   {"pu-n_t", 1, 2}];
Print[ExportString[grid2, "Table"]];
Print[];
Print["reading: pu=0.8 sits exactly at the k=4/n_t=1 critical (0.80): at that"];
Print["edge the correct-node advantage over tempters vanishes locally, so the"];
Print["platform stalls in a mixed regime (~0.85). pu=0.9 clears every critical"];
Print["point -> tempters fully retire -> platform 0.92+ and still climbing."];
Print["pu<=0.59 falls further behind; bad arm (pu=0) collapses to 0.50."];
Print["v8 late-means (0.920/0.855/0.847/0.802/0.605) are ordered exactly as"];
Print["the critical-point ordering predicts."];
Print["(2026-10-14, x75 for s6.1 v8)"];
