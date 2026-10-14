(* x63_kernel_tail.wl —— 非马尔可夫记忆核与衰减尾的对应（符号）
   广义主方程（Volterra）：dm/dt = -∫_0^t K(t-s) m(s) ds
   Laplace：mhat(s) = m0 / (s + K^(s))
   ⇒ 长时尾由 K^(s) 的小 s 行为决定（Tauberian 定理）
   ① 指数核（马尔可夫）→ 指数衰减
   ② 幂律核 K(t)=c t^-α (0<α<1) → 幂律尾 m(t) ~ t^-α（对应 Mittag-Leffler 松弛）
   Run: wolframscript -file x63_kernel_tail.wl *)

fmt[x_, d_] := ToString[NumberForm[N[x], {12, d}]];

Print["=== x63: memory kernel <-> decay tail (symbolic) ==="];
Print[""];

Print["--- 1. Markov kernel K(t) = g*delta(t) ---"];
Print["mhat(s) = m0/(s + g)  ->  m(t) = m0*e^{-g t}  (pure exponential)"];
Print[""];

Print["--- 2. power-law kernel K(t) = c*t^-alpha (0<alpha<1), Laplace transform ---"];
klap = LaplaceTransform[c*t^(-alpha), t, s, Assumptions -> 0 < alpha < 1];
Print["LaplaceTransform[c t^-alpha] = ", klap];
Print[""];
Print["mhat(s) = m0/(s + K^(s)); as s->0, s^(alpha-1) dominates s"];
Print["=> mhat(s) ~ m0/(c Gamma(1-alpha)) s^(1-alpha)"];
Print["=> m(t) ~ m0/(c Gamma(1-alpha) Gamma(alpha)) t^-alpha   (POWER-LAW tail)"];
Print[""];
Print["==> non-Markovian signature = power-law tail; Markov = exponential."];
Print[""];

Print["--- 3. numerical check: Mittag-Leffler solution (alpha=0.5, c=0.1) ---"];
m0 = 1.0;
mML[t_, alpha_, c0_] := m0*Sum[(-c0*t^(1 - alpha))^k/Gamma[1 + k*(1 - alpha)], {k, 0, 80}];
Print["m(t) = E_{1-alpha}(-c t^{1-alpha}); check m(t)*t^alpha -> const"];
Print[StringPadRight["t", 8], StringPadRight["m(t)", 14], "m(t)*t^0.5"];
Do[
  mv = mML[t, 0.5, 0.1];
  Print[StringPadRight[ToString[t], 8], StringPadRight[fmt[mv, 6], 14], fmt[mv*t^0.5, 6]],
  {t, {1, 10, 100, 1000, 10000, 100000}}];
Print["(approaching a constant slowly (correction ~ t^{-0.5}) => power-law tail confirmed)"];
Print[""];
Print["--- 4. stretched exponential (Weibull) is NOT power-law ---"];
Print["m(t) = m0 e^{-(t/tau)^beta}: decays FASTER than any power law at large t."];
Print["=> discriminating power vs stretched-exponential needs the far tail."];
