(* x74_v6_design.wl — s6.1 v6 feedback-shape design (M-first)
   Motivation: v5 failed (0.98 -> 0.88 on all arms). Diagnosis:
     (1) ceiling: temptation nodes (sigma=0.45, sim=0.91) never enter top5
         -> pure sim already scores 0.98, no room to grow;
     (2) feedback imbalance: rated-good nodes drop to conf=0.74 while
         never-rated tempters keep conf=1.0 -> rated-good nodes get
         overtaken by unrated tempters. Deadlock: only top1 is rated,
         so tempters (never top1) are never rated.

   v6 prescriptions to validate here:
     A. calibrate tempter strength so initial top5 hit ~ 0.6
        (tempters occupy ~2 of 5 slots)
     B. change feedback shape to "show top5 + choose":
        candidates shown *before* the pick get a rejection (+1 tot, +0 pos)
        -> tempters eat rejections whenever they rank above the pick

   Output English only (pipe-safe). *)

ClearAll["Global`*"];
d = 32; nc = 10; nn = 100; ntempTotal = 20; kShow = 5;
SeedRandom[20261014];

centers = RandomVariate[NormalDistribution[0, 1], {nc, d}];
labels = RandomInteger[{1, nc}, nn];
(* real nodes: cluster center + N(0,0.35); sim to own center ~ 0.94 *)
nodes = Table[
   Normalize[centers[[labels[[i]]]] + RandomVariate[NormalDistribution[0, 0.35], d]],
   {i, nn}];
qvec[k_] := Normalize[centers[[k]]];

(* ---------- part A: tempter sigma vs initial top5 hit ---------- *)
Print["=== x74 part A: tempter sigma vs initial top5 hit (real sigma 0.35) ==="];
Do[
  h = Mean@Flatten@Table[
     Module[{tgt, tem},
      SeedRandom[sd*100 + 7];
      tgt = RandomInteger[{1, nc}, ntempTotal];
      tem = Table[
        Normalize[centers[[tgt[[j]]]] + RandomVariate[NormalDistribution[0, sT], d]],
        {j, ntempTotal}];
      Table[
       Module[{qk, simsAll, isT, ord},
        qk = qvec[k];
        simsAll = Join[Table[nodes[[i]] . qk, {i, nn}],
           Table[tem[[j]] . qk, {j, ntempTotal}]];
        isT = Join[Table[labels[[i]] == k, {i, nn}],
           Table[False, {ntempTotal}]];
        ord = Reverse@Ordering[simsAll];
        N[Count[isT[[ord[[1 ;; kShow]]]], True]/kShow]
        ], {k, nc}]
      ], {sd, {11, 22, 33}}];
  Print["sigma_temp=", NumberForm[N@sT, {4, 2}],
   "  mean top5 hit = ", NumberForm[h, {4, 3}]];
  , {sT, {0.25, 0.30, 0.35, 0.40, 0.45}}];
Print[];

(* ---------- part B: feedback dynamics on the marginal top5 world ----------
   10 candidates competing at the top5 margin:
     5 near-true (sim 0.960..0.940), 2 tempters (0.953, 0.948),
     3 far-true (0.925..0.905). Initial top5 = 3 true + 2 tempters -> hit 0.6.
   modes:
     "top1"   : v5 legacy, only the top1 gets rated (+pos)
     "before" : show top5, pick one; shown-before-pick get +tot (rejection)
     "all"    : show top5, pick one; every shown-but-unpicked gets +tot
   conf = (pos + 2)/(tot + 2); hit recorded every 25 rounds over 300. *)
sims = {0.960, 0.955, 0.950, 0.945, 0.940, 0.953, 0.948, 0.925, 0.915, 0.905};
isTrue = {1, 1, 1, 1, 1, 0, 0, 1, 1, 1};
nCand = 10;

simulate[mode_, reject_, pu_, rounds_, seed_] := Module[
  {pos, tot, conf, score, order, shown, tr, pick, pickPos, rejSet, curve,
   ord2},
  SeedRandom[seed];
  pos = ConstantArray[0., nCand]; tot = ConstantArray[0., nCand];
  curve = {};
  Do[
    conf = (pos + 2.)/(tot + 2.);
    score = sims*conf;
    order = Reverse@Ordering[score];
    shown = order[[1 ;; kShow]];
    tr = Select[shown, isTrue[[#]] == 1 &];
    (* pick *)
    pick = Which[
      mode === "top1", shown[[1]],
      Length[tr] > 0 && RandomReal[] < pu, RandomChoice[tr],
      Length[tr] > 0,
        With[{nt = Select[shown, isTrue[[#]] == 0 &]},
         If[Length[nt] > 0, First[nt], shown[[1]]]],
      True, shown[[1]]
      ];
    (* rejections *)
    If[mode =!= "top1",
      pickPos = FirstPosition[shown, pick][[1]];
      rejSet = Which[
        reject === "before", shown[[1 ;; pickPos - 1]],
        reject === "all", Delete[shown, pickPos],
        True, {}];
      Scan[(tot[[#]] += 1.) &, rejSet]];
    tot[[pick]] += 1.; pos[[pick]] += 1.;
    If[Mod[t, 25] == 0,
      conf = (pos + 2.)/(tot + 2.);
      ord2 = Reverse@Ordering[sims*conf];
      AppendTo[curve, N[Count[isTrue[[ord2[[1 ;; kShow]]]], 1]/kShow]]];
    , {t, 0, rounds - 1}];
  $lastPos = pos; $lastTot = tot;
  curve];

runMean[mode_, reject_, pu_] := Module[{rs},
  rs = Table[simulate[mode, reject, pu, 300, sd], {sd, {11, 22, 33}}];
  N[Mean[rs]]];

Print["=== x74 part B: feedback dynamics (mean over 3 seeds, 13 checkpoints t=0..300) ==="];
Print["checkpoints every 25 rounds; initial hit = 0.60"];
Print[];
m1 = runMean["top1", "before", 0.8];
m2 = runMean["before", "before", 0.8];
m3 = runMean["all", "all", 0.8];
Print["top1  (v5 legacy)      : ", Row[NumberForm[#, {4, 3}] & /@ m1, "  "]];
Print["before-pick rejections : ", Row[NumberForm[#, {4, 3}] & /@ m2, "  "]];
Print["all-shown rejections   : ", Row[NumberForm[#, {4, 3}] & /@ m3, "  "]];
Print[];
Print["first/last -> delta:"];
Print["  top1  : ", NumberForm[m1[[1]], {4, 3}], " -> ", NumberForm[m1[[-1]], {4, 3}]];
Print["  before: ", NumberForm[m2[[1]], {4, 3}], " -> ", NumberForm[m2[[-1]], {4, 3}]];
Print["  all   : ", NumberForm[m3[[1]], {4, 3}], " -> ", NumberForm[m3[[-1]], {4, 3}]];
Print[];
(* pu sensitivity for the winning mode *)
Do[
  mm = runMean["before", "before", pu];
  Print["before, pu=", NumberForm[pu, {3, 2}],
   " : ", NumberForm[mm[[1]], {4, 3}], " -> ", NumberForm[mm[[-1]], {4, 3}]]
  , {pu, {0.6, 0.8, 0.9}}];
Print[];
(* final-state audit: which candidates hold the top5 at the end *)
simulate["before", "before", 0.8, 300, 33];
Print["=== final-state audit (mode=before pu=0.8, seed=33) ==="];
Print["idx  sim    true  pos   tot   conf"];
Do[
  Print[PaddedForm[j, 2], "  ", NumberForm[sims[[j]], {3, 3}], "  ",
   isTrue[[j]], "   ", NumberForm[$lastPos[[j]], {3, 0}], "   ",
   NumberForm[$lastTot[[j]], {3, 0}], "   ",
   NumberForm[($lastPos[[j]] + 2.)/($lastTot[[j]] + 2.), {4, 3}]]
  , {j, nCand}];
Print["(2026-10-14, x74 for s6.1 v6)"];
