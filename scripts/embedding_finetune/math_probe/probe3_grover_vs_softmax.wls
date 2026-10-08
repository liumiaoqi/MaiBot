(* probe3_grover_vs_softmax.wls -- exp31 "Grover-style goal amplification":
   exact math of the mechanism, vs what real Grover iteration is.
   Ref: trading/exp31_grover_goal_amplification.py
   Run: wolframscript -file probe3_grover_vs_softmax.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {14, d}]];
row[v_] := StringRiffle[Map[ToString[NumberForm[N[#], {12, 9}]] &, v], "  "];

scores = {0.9, 0.7, 0.5, 0.3, 0.1};

(* the exp31 mechanism: P_i = clip(s_i,0,inf)^k / total *)
probs[s_List, k_] := Module[{c = Clip[s, {0, Infinity}]^k}, c/Total[c]];

Print["=== probe3: exp31 mechanism (Wolfram ", $Version, ") ==="];

Print["--- 1. mechanism check: scores = {0.9, 0.7, 0.5, 0.3, 0.1} ---"];
Do[Print["k=", k, " : ", row[probs[scores, k]]], {k, {1, 2, 8}}];

(* 2. duality: score^k sampling == softmax with logits k*log(score) *)
alt[s_List, k_] := Module[{e = Exp[k*Log[s]]}, e/Total[e]];
Print["--- 2. duality: max |P - softmax(k log s)| over k = 1..8 ---"];
d = Max[Table[Max[Abs[probs[scores, k] - alt[scores, k]]], {k, 1, 8}]];
Print["max abs diff = ", fmt[d, 18], "   (exact identity; k is an inverse temperature)"];

(* 3. real Grover iteration: uniform prior, single marked item.
   amplitude after k iterations = sin((2k+1) theta), sin(theta) = 1/sqrt(N) *)
theta[n_] := ArcSin[1/Sqrt[n]];
gp[n_, k_] := Sin[(2 k + 1) theta[n]]^2;
Print["--- 3. real Grover (N=5): P(marked) after k iterations ---"];
Do[Print["k=", k, " : ", fmt[gp[5, k], 6]], {k, 0, 4}];
Print["k_opt(N=5) = pi/(4 theta) - 1/2 = ", fmt[Pi/(4 theta[5]) - 1/2, 4],
      "  -> sin^2 oscillates (overshoot visible: k=2 < k=1)"];
Print["grover k_opt for N: ", Table[{n, fmt[Pi/(4 theta[n]) - 1/2, 3]}, {n, {4, 16, 64, 256}}]];

(* 4. score^k family: monotone sharpening; k -> infinity = greedy *)
Print["--- 4. sharpening P_main(k) vs k (monotone, unlike Grover) ---"];
Do[Print["k=", k, " : P_main = ", fmt[probs[scores, k][[1]], 6]], {k, {1, 2, 4, 8, 16, 64}}];
Print["closed form ratio P1/P2 = (0.9/0.7)^k : ",
      Table[{k, fmt[(0.9/0.7)^k, 4]}, {k, {1, 2, 4, 8}}]];

(* 4b. subtlety: the middle tier can RISE with k (mass reshuffles) *)
Print["--- 4b. P_secondary(0.7) vs k: rises then falls ---"];
Do[Print["k=", k, " : P_sec = ", fmt[probs[scores, k][[2]], 6]], {k, {1, 2, 3, 5, 8}}];

(* 5. frustration semantics: s3 = -0.5, k = 2 *)
sF = {0.9, 0.7, -0.5, 0.3, 0.1};
Print["--- 5. frustrated item (s3 = -0.5), k=2 ---"];
Print["clip(0) hard-exclusion : ", row[probs[sF, 2]]];
Print["keep-|s| (phase-like)  : ", row[Module[{c = Abs[sF]^2}, c/Total[c]]]];
