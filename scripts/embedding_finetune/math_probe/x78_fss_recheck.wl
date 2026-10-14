(* x78_fss_recheck.wl — §9 main-quantity recheck for probe27
   Independent Wolfram re-derivation of the FSS exponents from
   py27_fss_output.csv, cross-checked against the R-side pipeline
   (r27_fss_params.csv). Two independent analysis implementations on
   the same data: agreement = the exponent extraction is implementation-
   robust, not an artifact of one toolchain. *)

ClearAll["Global`*"];
base = "E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/";
rows = Rest[Import[base <> "py27_fss_output.csv", "CSV"]];  (* strings *)
Print["=== x78: independent WL recheck of probe27 FSS ==="];
Print["rows: ", Length[rows]];
Print[];

medianByGroups[selRows_] := Module[{grp},
   grp = GatherBy[selRows, {#[[1]], #[[3]]} &];
   Table[{ToExpression[g[[1, 1]]], ToExpression[g[[1, 3]]],
     Median[ToExpression /@ g[[All, 8]]]}, {g, grp}]];

analyze[sel_, label_] := Module[
  {agg, sizes, pk, fit1, gnu, snus, r2s, sBest, xTr, fit2, betaInf,
   prof, imax, pts, filt, cf, xv, yv, r2a},
  agg = medianByGroups[sel];
  sizes = Union[agg[[All, 1]]];
  pk = Table[
    prof = SortBy[Select[agg, #[[1]] == n &], #[[2]] &];
    imax = Ordering[prof[[All, 3]], -1][[1]];
    If[1 < imax < Length[prof],
     pts = prof[[imax - 1 ;; imax + 1, {2, 3}]];
     filt = Fit[pts, {1, x, x^2}, x];
     cf = CoefficientList[filt, x];
     If[cf[[3]] < 0,
      xv = -cf[[2]]/(2 cf[[3]]);
      yv = (filt /. x -> xv);
      {n, xv, yv},
      {n, prof[[imax, 2]], prof[[imax, 3]]}],
     {n, prof[[imax, 2]], prof[[imax, 3]]}],
    {n, sizes}];
  Print["--- ", label, " ---"];
  Print[TableForm[pk, TableHeadings -> {None, {"n", "beta_c", "chi_max"}}]];
  fit1 = LinearModelFit[Transpose[{Log[pk[[All, 1]]], Log[pk[[All, 3]]]}], x, x];
  gnu = fit1["BestFitParameters"][[2]];
  r2a = fit1["RSquared"];
  Print["gamma/nu = ", NumberForm[gnu, {5, 3}], "  (R2=", NumberForm[r2a, {5, 4}], ")"];
  snus = Range[0.4, 2.4, 0.005];
  r2s = Table[
    xTr = pk[[All, 1]]^(-s);
    LinearModelFit[Transpose[{xTr, pk[[All, 2]]}], x, x]["RSquared"], {s, snus}];
  sBest = snus[[Ordering[r2s, -1][[1]]]];
  xTr = pk[[All, 1]]^(-sBest);
  fit2 = LinearModelFit[Transpose[{xTr, pk[[All, 2]]}], x, x];
  betaInf = fit2["BestFitParameters"][[1]];
  Print["1/nu = ", NumberForm[sBest, {5, 3}], "  beta_inf = ",
   NumberForm[betaInf, {5, 4}], "  (R2=", NumberForm[Max[r2s], {5, 4}], ")"];
  Print[];
  {gnu, sBest, betaInf}];

wlAll = analyze[rows, "all sources (WL)"];
wlP = analyze[Select[rows, #[[4]] == "P" &], "P (WL)"];
wlH = analyze[Select[rows, #[[4]] == "H" &], "H (WL)"];

(* R-side comparison *)
rParams = Rest[Import[base <> "r27_fss_params.csv", "CSV"]];
Print["=== R vs WL parameter comparison ==="];
Print["source |  gnu  R   WL  |  snu  R   WL  |  beta_inf R   WL"];
Do[
  src = rParams[[j, 1]];
  rG = ToExpression[rParams[[j, 2]]]; rS = ToExpression[rParams[[j, 3]]];
  rB = ToExpression[rParams[[j, 4]]];
  wl = Which[src == "all", wlAll, src == "P", wlP, src == "H", wlH];
  Print[PaddedForm[src, {5, Left}], " | ",
   NumberForm[rG, {5, 3}], " ", NumberForm[wl[[1]], {5, 3}], " | ",
   NumberForm[rS, {5, 3}], " ", NumberForm[wl[[2]], {5, 3}], " | ",
   NumberForm[rB, {5, 4}], " ", NumberForm[wl[[3]], {5, 4}]];
  , {j, Length[rParams]}];
Print[];
Print["note: same data, two independent implementations (R lm/aggregate vs"];
Print["WL Median/Fit/LinearModelFit). Agreement checks the exponent"];
Print["extraction is robust to the analysis toolchain."];
Print["(2026-10-14, x78 for probe27)"];
