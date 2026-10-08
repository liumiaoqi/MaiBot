(* probe6_rank_theory.wls -- theory side of the rank scan:
   predicted signal band vs the MP noise edge, and the K where the weakest
   signal singular value drowns in noise.
   Note: `D` is a protected built-in (derivative) -- use `dim`.
   Ref: probe6_rank_scan.m
   Run: wolframscript -file probe6_rank_theory.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {14, d}]];

tt = 200; dim = 64; noise = 0.3;
mpEdge = noise*(Sqrt[tt] + Sqrt[dim]);

Print["=== probe6 theory: signal band vs noise band (T=", tt, ", dim=", dim, ") ==="];
Print["MP noise edge = sigma*(sqrt(T)+sqrt(dim)) = ", fmt[mpEdge, 3]];
Print[""];

predStrong[k_] := Sqrt[tt/k]*Sqrt[dim]*(1 + Sqrt[Min[k, dim]/dim]);
predWeak[k_] := If[k >= dim, 0.0, Sqrt[tt/k]*Sqrt[dim]*(1 - Sqrt[k/dim])];

Print["--- predicted strongest / weakest signal singular value ---"];
Do[
  Print["K=", k, " : strong ", fmt[predStrong[k], 2], "   weak ", fmt[predWeak[k], 2],
        If[predWeak[k] > mpEdge, "   (cliff intact)", "   (weak signal inside noise band -- cliff gone)"]],
  {k, {8, 16, 32, 64, 128}}];

Print[""];
Print["--- numeric check: K x dim gaussian center spectra (SeedRandom 7) ---"];
Do[
  SeedRandom[7];
  cs = SingularValueList[RandomVariate[NormalDistribution[], {k, dim}]];
  Print["K=", k, " : max ", fmt[Max[cs], 2], "  (pred ", fmt[Sqrt[dim]*(1 + Sqrt[Min[k, dim]/dim]), 2], ")",
        "   min ", fmt[Min[cs], 2], "  (pred ", fmt[If[k >= dim, 0., Sqrt[dim]*(1 - Sqrt[k/dim])], 2], ")   n=", Length[cs]],
  {k, {8, 16, 32, 64, 128}}];

Print[""];
Print["prediction: weakest signal crosses the noise edge between K=16 and K=32;"];
Print["beyond K~dim the signal directions fill the whole space and no cliff remains."];
