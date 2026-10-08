(* probe4_hopfield_snr.wls -- salience-weighted Hopfield: SNR analysis.
   Ref: trading/exp35_quantum_hopfield.py

   Model: W = (Sum c_m s_m s_m^T)/C, diag 0.  Probe input s_k (complete):
     signal_i = c_k (N-1)/C * s_ki
     noise_i  ~ std = sqrt(N * Sum_{m!=k} c_m^2)/C
   =>  SNR_k = c_k (N-1) / sqrt(N * Sum_{m!=k} c_m^2)
   one-shot component accuracy ~ Phi(SNR_k), whole pattern ~ Phi(SNR_k)^N.
   Q: why is the weighted model WORSE at low load (M=10) and better at high load?
   Run: wolframscript -file probe4_hopfield_snr.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {14, d}]];
phiN[z_, n_] := CDF[NormalDistribution[], z]^n;

Nn = 80;
tiers = {0.3, 0.475, 0.65, 0.825, 1.0};
csM[m_] := Flatten[Table[tiers, {m/5}]];

snrUnif[m_] := (Nn - 1)/Sqrt[Nn*(m - 1)];
snrW[ck_, cs_] := ck*(Nn - 1)/Sqrt[Nn*(Total[cs^2] - ck^2)];

Print["=== probe4: salience-weighted Hopfield, SNR analysis ==="];

Print["--- per-tier SNR & one-shot estimate (M=20, c = 5 tiers x4) ---"];
Do[
  Print["c=", c, " : uniform SNR=", fmt[snrUnif[20], 4], "  Phi^N=", fmt[phiN[snrUnif[20], Nn], 4],
        "   | weighted SNR=", fmt[snrW[c, csM[20]], 4], "  Phi^N=", fmt[phiN[snrW[c, csM[20]], Nn], 6]],
  {c, tiers}];

Print[""];
Print["--- load scan: uniform vs weighted (ensemble mean over tiers) ---"];
Print[StringPadRight["M", 4], " uniform SNR/est      weighted mean est  [per-tier est]"];
Do[
  cs = csM[m];
  u = phiN[snrUnif[m], Nn];
  wEst = Mean[Table[phiN[snrW[c, cs], Nn], {c, tiers}]];
  wTiers = Table[fmt[phiN[snrW[c, cs], Nn], 4], {c, tiers}];
  Print[StringPadRight[ToString[m], 4], " ", fmt[snrUnif[m], 3], " / ", fmt[u, 4], "      ",
        fmt[wEst, 4], "  ", Row[wTiers, " "]],
  {m, {5, 10, 15, 20, 25, 30}}];

(* the crossover: where weighted mean estimate overtakes uniform *)
Print[""];
Print["--- crossover search (M=5..40 by 5, same 5-tier c) ---"];
cross = Reap[
   Do[
     cs = csM[m];
     u = phiN[snrUnif[m], Nn];
     w = Mean[Table[phiN[snrW[c, cs], Nn], {c, tiers}]];
     If[w > u, Sow[m]],
     {m, 5, 40, 5}]][[2]];
If[cross === {}, Print["no crossover in range"],
  Print["weighted est > uniform est for M = ", cross, "  (first: ", First[cross], ")"]];

(* deterministic mini-case for cross-platform check *)
s1 = {1., 1, 1, 1, -1, -1, -1, -1};
s2 = {1., 1, -1, -1, 1, 1, -1, -1};
Wm = (1.0*Outer[Times, s1, s1] + 0.5*Outer[Times, s2, s2])/1.5;
Wm = Wm - DiagonalMatrix[Diagonal[Wm]];
step[x_] := Map[If[# >= 0, 1., -1.] &, Wm.x];
x0 = {1., 1, 1, 1, 0, 0, 0, 0};
fp = FixedPoint[step, x0, 50];
Print[""];
Print["--- mini-case (N=8, M=2, synchronous) for cross-check ---"];
Print["W row1: ", Row[Map[fmt[#, 7] &, Wm[[1]]], " "]];
Print["x0    : ", x0];
Print["fixed : ", fp];
Print["recovered s1? ", fp == s1];
