(* probe10_annealing_identity.wls -- exp32 mechanism identities:
   1. the "annealing" switch probability vs standard Metropolis
   2. the temperature schedule actually reached
   3. the inertia freeze-zone / idle-window accounting
   Run: wolframscript -file probe10_annealing_identity.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {16, d}]];

Print["=== probe10: exp32 mechanism identities ==="];
Print[""];
Print["--- 1. switch probability: implementation vs standard Metropolis ---"];
Print["implementation: P = exp(-SWITCH_COST/T) with SWITCH_COST = 0.2 (constant!)"];
Print["standard      : P = exp(-gain/T)         (gain = candidate improvement)"];
Print[""];
Print[StringPadRight["T", 8], StringPadRight["P_impl", 12], "P_std(gain=1)  P_std(5)      P_std(20)"];
Do[
  Print[StringPadRight[ToString[T], 8],
        StringPadRight[fmt[Exp[-0.2/T], 6], 12],
        fmt[Exp[-1/T], 6], "      ", fmt[Exp[-5/T], 6], "      ", fmt[Exp[-20/T], 6]],
  {T, {10, 5, 2, 1, 0.5, 0.2, 0.1}}];
Print["=> implementation is gain-INDEPENDENT: a temperature-scheduled noise injector;"];
Print["   'gain > 0' acts only as a gate."];
Print[""];
Print["--- 2. temperature schedule actually reached: T(t) = 10 * 0.985^t ---"];
Do[
  Print["t=", StringPadRight[ToString[t], 5],
        "T = ", StringPadRight[fmt[10*0.985^t, 4], 9],
        "P_impl = ", fmt[Exp[-0.2/(10*0.985^t)], 4]],
  {t, {0, 50, 100, 168}}];
Print["T_min over run = ", fmt[10*0.985^168, 4],
      "  => the max(T, 0.1) clamp NEVER triggers (dead code);"];
Print["P_impl falls only from 0.980 to 0.776 -- there is NO late-stage freeze."];
Print[""];
Print["--- 3. inertia freeze zone & idle window ---"];
Print["switch requires: any h_other > 1.2 * h_cur + 5    (h capped at 30)"];
Print["freeze region (no switch possible): h_cur > (30-5)/1.2 = ", fmt[25/1.2, 3]];
Print["observed max hunger = 7.2  => freeze region never entered."];
Print[""];
Print["real inertia cost = idle window: after the target is drained (h=0),"];
Print["the rule keeps feeding it until some other desire crosses 5:"];
Print["  fastest ramp = 0.8/step -> idle window ~", fmt[5/0.8, 2], " steps"];
Print["  budget burned ~", fmt[6*1.2, 2], "/step  -> ~", fmt[5/0.8*6*1.2, 1], " per window (scaled per window size)"];
Print["ledger says: inertia idle_waste = 906 vs greedy 560 over 168 steps."];
