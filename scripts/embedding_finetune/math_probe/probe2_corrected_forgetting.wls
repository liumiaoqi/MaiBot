(* probe2_corrected_forgetting.wls -- corrected two-level forgetting model.
   Question: can the "spacing effect" emerge once we fix
     (a) the phase problem (state-level daily decay instead of global-clock curve), and
     (b) give the review gain a structure?
   Two gain variants:
     "stock": L += k*S      (gain proportional to retained short-term stock)
     "gap"  : L += k*(s0-S) (gain proportional to the forgetting gap -> desirable difficulty)
   Reference model = exp29 original semantics (frozen).
   Run: wolframscript -file probe2_corrected_forgetting.wls *)

Off[General::munfl];

s0 = 0.7; L0 = 0.1; taus = 1.0; taul = 200.0; kG = 0.5; nd = 31;

(* --- original exp29 semantics (global clock) --- *)
origObs[reviews_List] := Module[{S = s0, L = L0},
  Do[If[MemberQ[reviews, t], S = s0; L = L + 0.3], {t, 0, nd}];
  S*Exp[-nd/taus] + L*Exp[-nd/taul]];

(* --- corrected model: state-level daily decay + structured gain --- *)
v2Obs[reviews_List, gain_String] := Module[{S = s0, L = L0},
  Do[
    S = S*Exp[-1/taus]; L = L*Exp[-1/taul];         (* one day passes *)
    If[MemberQ[reviews, t],
      If[gain === "stock", L = L + kG*S, L = L + kG*(s0 - S)];
      S = s0],                                       (* review: consolidate + re-activate *)
    {t, 1, nd}];
  S + L];

fmt[x_, d_] := ToString[NumberForm[N[x], {12, d}]];

Print["=== probe2: corrected forgetting model (state dynamics) ==="];
Print["params: s0=", s0, "  L0=", L0, "  taus=", taus, "  taul=", taul, "  k=", kG, "  N=31d, 4 reviews"];
Print[""];

dists = <|
  "cram   {27,28,29,30}" -> {27, 28, 29, 30},
  "spaced {1,3,7,14}"    -> {1, 3, 7, 14},
  "even7  {7,14,21,28}"  -> {7, 14, 21, 28},
  "early  {1,2,3,4}"     -> {1, 2, 3, 4},
  "late   {20,24,28,30}" -> {20, 24, 28, 30}|>;

Print[StringPadRight["distribution", 22], " orig31    v2-stock  v2-gap"];
Do[
  Print[StringPadRight[name, 22], " ", fmt[origObs[dists[name]], 4], "    ",
        fmt[v2Obs[dists[name], "stock"], 4], "    ", fmt[v2Obs[dists[name], "gap"], 4]],
  {name, Keys[dists]}];

(* --- uniform-gap family: first review at f, gap d, 4 reviews --- *)
Print[""];
Print["--- uniform family: {f, f+d, f+2d, f+3d} (keep <=30) ---"];
Print[StringPadRight["(f,d)", 10], " v2-stock  v2-gap"];
Do[
  rv = Select[{f, f + d, f + 2 d, f + 3 d}, # <= 30 &];
  If[Length[rv] == 4,
    Print[StringPadRight["(" <> ToString[f] <> "," <> ToString[d] <> ")", 10], " ",
          fmt[v2Obs[rv, "stock"], 4], "    ", fmt[v2Obs[rv, "gap"], 4]]],
  {d, {1, 2, 4, 7, 9}},
  {f, {1, 8, 15}}];

(* --- what does the phase fix change for a single review? --- *)
Print[""];
Print["--- single review at t=1, observed at t=2 / t=5 ---"];
Print["orig  : ", fmt[origObs[{1}], 4], " (global clock; S collapses)"];
Print["v2 all: ", fmt[v2Obs[{1}, "stock"], 4], " (state; S re-decays from review)"];
