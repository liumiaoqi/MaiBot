(* x80 — probe28 主量独立复算：knn 图随机游走矩阵的第二特征值
   口径：P = D^-1 A（随机游走转移）；λ₂ = 第二大 |eig|；gap = 1 - λ₂
   对拍目标：probe28（numpy 侧）报告 λ₂ = 0.955875 · gap = 0.044125
   输入：knn_edges.csv（1-based 边表，knn_graph_2500 全边） *)

path = "E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/knn_edges.csv";
e = Import[path, "CSV"];
n = 2500;
(* 构造邻接（对准对称性：边表本身是对称的，直接累计） *)
rules = Flatten[Table[{e[[k, 1]] -> 1., e[[k, 2]] -> 1.}, {k, Length[e]}]];
A = SparseArray[rules, {n, n}];
deg = Total[A];
P = Normal[SparseArray[Table[i -> 1./deg[[i]], {i, n}], {n, n}] . A];
vals = Eigenvalues[P];
mag = Reverse[Sort[Abs[vals]]];
Print["top |eig| (WL): ", Take[mag, 4]];
Print["lambda2 (WL) = ", mag[[2]]];
Print["gap     (WL) = ", 1 - mag[[2]]];
Print["reported (numpy): lambda2 = 0.955875 | gap = 0.044125"];
Print["done (x80)."];
