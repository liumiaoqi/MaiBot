(* x64_modelfit_compare.wls —— exp64: ModelFit（WL 15 原生框架）重做 exp63 形状辨识
   对照：python curve_fit + AIC（exp63 结论：power 赢 −58.3；biexp −45.6）
   四模型：指数 / 双指数 / PowerModel / Wixted 幂律；外加多模型交叉验证自动选择。
   Run: wolframscript -file x64_modelfit_compare.wls *)

fmt[x_, d_] := ToString[NumberForm[N[x], {12, d}]];

data = Transpose[{{0.33, 1, 9, 24, 48, 144, 744}/24.0,
                  {0.58, 0.44, 0.36, 0.33, 0.28, 0.25, 0.21}}];

Print["=== x64/exp64: ModelFit (WL 15) redo of exp63 shape ID ==="];
Print["data: Ebbinghaus 7 points (days, retention)"];
Print["python exp63 reference: AIC -> power -58.3 < stretch -51.9 < biexp -45.6 < exp -22.5"];
Print[""];

Print["--- 1. single-model fits (expression) ---"];
m1 = ModelFit[data, ExponentialModel[], "Expression"];
Print["1 exp      : ", m1];
m2 = ModelFit[data, FormulaModel[a Exp[-t/t1] + b Exp[-t/t2], t], "Expression"];
Print["2 biexp    : ", m2];
m3 = ModelFit[data, PowerModel[], "Expression"];
Print["3 power(+c): ", m3];
m4 = ModelFit[data, FormulaModel[m0 (1 + t/tau)^(-alpha), t], "Expression"];
Print["4 wixted   : ", m4];
Print[""];

Print["--- 2. auto selection by cross-validation over the four models ---"];
mBest = ModelFit[data, {ExponentialModel[],
                        FormulaModel[a Exp[-t/t1] + b Exp[-t/t2], t],
                        PowerModel[],
                        FormulaModel[m0 (1 + t/tau)^(-alpha), t]}];
Print["auto-selected: ", Normal[mBest]];
Print[""];
Print["--- 3. verdict vs python ---"];
Print["Compare the auto-selected family with python AIC winner (power)."];
Print["NOTE: FormulaModel has no parameter constraints - the Wixted fit runs"];
Print["      into the complex plane and gets wrongly auto-selected; use classical"];
Print["      NonlinearModelFit when constraints are needed."];
Print["(2026-10-14, WL 15 ModelFit first use)"];
