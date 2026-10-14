(* x65_diffusion_rank_crosscheck.wl —— s5.x（扩散检索/排序）的独立复算
   ① 6 节点路径图热核 p(t=1)：独立特征分解实现（对照 python 谱法）
   ② nDCG@5 公式复算（对照 python 实现）
   Run: wolframscript -file x65_diffusion_rank_crosscheck.wl *)

fmt[x_, d_] := ToString[NumberForm[N[x], {12, d}]];

Print["=== x65: s5.x diffusion/rank cross-check ==="];
Print[""];

(* ① 6 节点路径图：L = D - A，热核 p(t=1)，源 = 节点 1 *)
n = 6;
W = ConstantArray[0, {n, n}];
Do[W[[i, i + 1]] = W[[i + 1, i]] = 1, {i, 1, n - 1}];
deg = Total[W];
L = DiagonalMatrix[deg] - W;
{vals, vecs} = Eigensystem[N[L]];
vecs = Normalize /@ vecs;              (* 归一（防不归一坑） *)
p0 = UnitVector[n, 1];
coef = vecs . p0;
t = 1;
p = Sum[coef[[k]]*Exp[-vals[[k]]*t]*vecs[[k]], {k, 1, n}];
Print["--- 1. path-6 heat kernel p(t=1), source = node1 ---"];
Print["p   = ", Table[fmt[p[[i]], 8], {i, 1, n}]];
Print["sum = ", fmt[Total[p], 8]];
Print[""];

(* ② nDCG@5 公式复算：距离向量 [1,2,2,3,5]（已按距离升序=最优排列） *)
ds = {1, 2, 2, 3, 5};
g = 2.^(-ds);
dcg = Sum[g[[i]]/Log2[i + 1], {i, 1, 5}];
ideal = Sort[2.^(-ds), Greater];
idcg = Sum[ideal[[i]]/Log2[i + 1], {i, 1, 5}];
Print["--- 2. nDCG@5 for dist = [1,2,2,3,5] ---"];
Print["gains = ", g];
Print["DCG = ", fmt[dcg, 8], "  IDCG = ", fmt[idcg, 8], "  nDCG = ", fmt[dcg/idcg, 8]];
Print[""];
Print["(对照 python 侧 x65_py_ref.py 的输出)"];
