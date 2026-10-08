(* probe11_toy_box.wls -- 1-D "box evolution" toy:
   selection + truncated mutation on [0,1]; what trajectory shape results
   when the true optimum lies INSIDE vs OUTSIDE the box?
   Purpose: give the real worm-evolution gene trajectories a reference shape.
   Run: wolframscript -file probe11_toy_box.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {14, d}]];

sim[opt_, gens_, pop_, noise_, seed_] := Module[
  {x, fit, order, surv, newp, hist, besti},
  SeedRandom[seed];
  x = RandomReal[{0.3, 0.7}, pop];
  hist = {};
  Do[
    fit = -(x - opt)^2 + noise*RandomVariate[NormalDistribution[]];
    besti = First[Ordering[fit, -1]];
    AppendTo[hist, {g, Mean[x], x[[besti]], Max[fit]}];
    order = Ordering[fit, -Max[2, Round[pop/5]]];
    surv = x[[order]];
    newp = {First[surv]};
    While[Length[newp] < pop,
      AppendTo[newp, Clip[RandomChoice[surv] + 0.3*0.1*RandomVariate[NormalDistribution[]], {0, 1}]]];
    x = newp,
    {g, 0, gens - 1}];
  hist];

report[name_, hist_, gens_] := Module[{},
  Print["--- ", name, " (mean gene at selected generations) ---"];
  Do[
    row = hist[[g + 1]];
    Print["gen ", StringPadRight[ToString[g], 4], " mean=", fmt[row[[2]], 4],
          "  best-fit=", fmt[row[[4]], 4]],
    {g, Join[Range[0, 40, 10], {gens - 1}]}];
  (* late-stage wall-hitting stats (gen 25..) *)
  late = hist[[26 ;;]];
  wall = Count[late, r_ /; r[[2]] > 0.98];
  Print["late-stage (gen25-49) wall-hits (mean>0.98): ", wall, " / ", Length[late]]];

Print["=== probe11: 1-D box evolution toy (box = [0,1], pop=50, 50 gens) ==="];
Print[""];

Print["scenario A: optimum INSIDE the box (x* = 0.7)"];
report["A", sim[0.7, 50, 50, 0.0, 7], 50];
Print[""];
Print["scenario B: optimum OUTSIDE the box (x* = 1.4)"];
report["B", sim[1.4, 50, 50, 0.0, 7], 50];
Print[""];
Print["scenario C: optimum OUTSIDE + fitness noise (sigma=0.05)"];
report["C", sim[1.4, 50, 50, 0.05, 7], 50];
Print[""];
Print["reading: A settles at the interior optimum; B/С hit the wall and stay"];
Print["=> real gene trajectories pinned at GENE_RANGES bounds = optimum outside the box"];
