(* probe12_thermo_sampling.wls -- thermodynamics of the exp31 selection system.
   p_i ∝ s_i^β  is a Boltzmann distribution with E_i = -ln s_i and β = k.
   Compute Z, F, U, S, C(β); locate the heat-capacity peak; compare with the
   empirical "secondary-item probability peak" at k* ≈ 1.88 (probe3).
   Run: wolframscript -file probe12_thermo_sampling.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {16, d}]];

s = {0.9, 0.7, 0.5, 0.3, 0.1};
e = -Log[s];               (* energies *)
Z[b_] := Total[s^b];
p[b_] := s^b/Z[b];
U[b_] := p[b] . e;
F[b_] := -Log[Z[b]]/b;
S[b_] := b*U[b] + Log[Z[b]];
Cv[b_] := b^2*(p[b] . (e^2) - U[b]^2);

Print["=== probe12-B: thermodynamics of selection (scores ", s, ") ==="];
Print["energies E = -ln s : ", Row[Map[fmt[#, 4] &, e], "  "]];
Print[""];
Print[StringPadRight["beta", 6], StringPadRight["P_main", 10], StringPadRight["P_sec", 10],
      StringPadRight["U", 10], StringPadRight["S", 10], "C"];
Do[
  Print[StringPadRight[fmt[b, 2], 6],
        StringPadRight[fmt[p[b][[1]], 4], 10],
        StringPadRight[fmt[p[b][[2]], 4], 10],
        StringPadRight[fmt[U[b], 4], 10],
        StringPadRight[fmt[S[b], 4], 10],
        fmt[Cv[b], 4]],
  {b, {0.5, 1, 1.5, 2, 2.5, 3, 4, 5}}];

(* locate the heat-capacity peak numerically *)
grid = Range[0.1, 6.0, 0.02];
cv = Map[Cv, grid];
mx = Max[cv];
pk = First[Flatten[Position[cv, mx]]];
Print[""];
Print["heat-capacity peak: C_max = ", fmt[mx, 4], " at beta = ", fmt[grid[[pk]], 3]];

(* where does P_main cross 0.5 / 0.9 / 0.99 *)
cross[th_] := Module[{},
  pos = Select[grid, p[#][[1]] >= th &];
  If[pos === {}, ">6", fmt[First[pos], 3]]];
Print["P_main crosses 0.5 at beta = ", cross[0.5],
      " | 0.9 at ", cross[0.9], " | 0.99 at ", cross[0.99]];
Print["(probe3 reference: P_secondary peak at k* = 1.88; P_last<0.001 from k = 2.91)"];
