(* probe1_forgetting.wls -- exp29 quantum forgetting models:
   numerical replay (cross-check vs Python) + symbolic analysis (new properties).
   Ref: trading/exp29_quantum_forgetting.py (2026)
   Run: wolframscript -file probe1_forgetting.wls *)

s0 = 1.0; nd = 31; ts = 1.0; tl = 200.0; c0 = 0.1; cons = 0.3;
Off[Solve::ifun, General::munfl];

granular[t_] := Max[0.2, s0*Exp[-t/24.0]];
ampdamp[t_] := Max[0.2, s0*0.95^t];
twolevel[t_] := 0.7*s0*Exp[-t/ts] + c0*s0*Exp[-t/tl];

reviewCurve[reviews_List, n_Integer] := Module[{S = 0.7, L = c0, out = {}, t},
  Do[
    If[MemberQ[reviews, t], S = 0.7*s0; L = L + cons*s0];
    AppendTo[out, S*Exp[-t/ts] + L*Exp[-t/tl]],
    {t, 0, n}];
  out
];

EBB = {{0, 1.00}, {0.33, 0.58}, {1, 0.44}, {9, 0.36}, {24, 0.33}, {48, 0.28}, {144, 0.25}, {744, 0.21}};

maeOf[curve_List] := Mean[
  Table[
    Module[{h = pair[[1]], ref = pair[[2]], day, i0, i1, frac, v},
      day = h/24.0;
      i0 = Floor[day];
      i1 = Min[i0 + 1, Length[curve] - 1];
      frac = day - i0;
      v = curve[[i0 + 1]]*(1 - frac) + curve[[i1 + 1]]*frac;
      Abs[v - ref]],
    {pair, EBB}]];

fmt[x_, d_] := ToString[NumberForm[N[x], {12, d}]];

Print["=== A. exp29 replay (Wolfram ", $Version, ") ==="];
g  = Table[granular[t], {t, 0, nd}];
qa = Table[ampdamp[t],  {t, 0, nd}];
q2 = Table[twolevel[t], {t, 0, nd}];
Print["granular : MAE ", fmt[maeOf[g], 5], "   31d ", fmt[g[[32]]*100, 2], "%"];
Print["ampdamp  : MAE ", fmt[maeOf[qa], 5], "   31d ", fmt[qa[[32]]*100, 2], "%"];
Print["twolevel : MAE ", fmt[maeOf[q2], 5], "   31d ", fmt[q2[[32]]*100, 2], "%"];

r1 = reviewCurve[{1}, nd];
r4 = reviewCurve[{1, 3, 7, 14}, nd];
Print["review{1}        7d ", fmt[r1[[8]], 4], "   31d ", fmt[r1[[32]], 4]];
Print["review{1,3,7,14} 7d ", fmt[r4[[8]], 4], "   31d ", fmt[r4[[32]], 4]];

Print[""];
Print["=== B. symbolic analysis ==="];

(* B1: crossover time: solve S0 e^{-t/ts} == L0 e^{-t/tl} *)
sol = Solve[S0*Exp[-t/ts0] == L0*Exp[-t/tl0], t];
Print["B1 crossover (general): t* = ", Simplify[t /. First[sol]]];
tStar = (t /. First[sol]) /. {S0 -> 0.7, L0 -> 0.1, ts0 -> ts, tl0 -> tl};
Print["B1 crossover (exp29):   t* = ", fmt[tStar, 4], " days"];

(* B2: strategy-independence of 31d retention.
   In the original implementation the exponential factors use the GLOBAL t,
   so S collapses to 'last review amplitude' and L to a review counter:
   ret31(n) = 0.7 e^{-31/ts} + (c0 + cons*n) e^{-31/tl}. *)
pred[n_] := 0.7*Exp[-31/ts] + (c0 + cons*n)*Exp[-31/tl];
Print["B2 closed form: ret31(n) = 0.7 e^{-31} + (0.1 + 0.3 n) e^{-31/200}"];
Do[
  Print["B2 n=", n, " -> ret31 = ", fmt[pred[n], 4],
        "   (sim {1,3,7,14}: ", fmt[reviewCurve[{1, 3, 7, 14}, nd][[32]], 4], ")"],
  {n, 0, 5}];

cr = reviewCurve[{27, 28, 29, 30}, nd];
mb = reviewCurve[{14, 15, 16, 17}, nd];
Print["B2 spaced  {1,3,7,14}   ret31 = ", fmt[r4[[32]], 4]];
Print["B2 crammed {27,28,29,30} ret31 = ", fmt[cr[[32]], 4]];
Print["B2 midblock{14,15,16,17} ret31 = ", fmt[mb[[32]], 4]];

(* B3: long-run behaviour under periodic review (original semantics):
   L grows ~ (cons/dt) t while the curve carries e^{-t/tl} => peak near t ~ tl. *)
c7 = reviewCurve[Table[7 k, {k, 0, 100}], 730];
peak = Max[c7]; pos = Position[c7, peak][[1, 1]] - 1;
Print["B3 periodic (dt=7d, 2y): peak ", fmt[peak, 3], " at t = ", pos, " d"];

(* B4: steady state if L decayed between reviews (phase-correct variant):
   L* = cons e^{-dt/tl} / (1 - e^{-dt/tl}) *)
Lss[dt_] := cons*Exp[-dt/tl]/(1 - Exp[-dt/tl]);
Print["B4 phase-correct steady state  L*(dt) = 0.3 e^{-dt/200}/(1 - e^{-dt/200})"];
Do[Print["B4 dt=", dt, " d -> L* = ", fmt[Lss[dt], 4]], {dt, {1, 3, 7, 14, 30, 60}}];

(* B5: phase-reset quantification for the S component *)
Print["B5 S after review at t=14, evaluated at t=15:"];
Print["   no phase reset: 0.7 e^{-15} = ", ToString[CForm[N[0.7*Exp[-15.0], 12]]]];
Print["   phase reset   : 0.7 e^{-1}  = ", fmt[0.7*Exp[-1.0], 8]];
