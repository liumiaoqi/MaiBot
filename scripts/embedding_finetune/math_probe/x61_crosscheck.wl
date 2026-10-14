(* x61_crosscheck: exp61 交叉验证（Wolfram 侧）

2D 周期格 CTQW，源 = 节点 0，t = 8 的概率分布。
用于与 x61_python_ref.py（numpy 侧）逐值对拍。
*)

side = 8; n = side*side;
W = ConstantArray[0, {n, n}];
Do[Module[{i, j1, j2},
    i = r*side + c + 1;
    j1 = r*side + Mod[c + 1, side] + 1;
    j2 = Mod[r + 1, side]*side + c + 1;
    W[[i, j1]] = 1; W[[j1, i]] = 1;
    W[[i, j2]] = 1; W[[j2, i]] = 1;],
  {r, 0, side - 1}, {c, 0, side - 1}];

{vals, vecs} = Eigensystem[N[W]];
psi0 = UnitVector[n, 1];
coef = vecs . psi0;
t = 8;
psi = Sum[coef[[k]]*Exp[-I*vals[[k]]*t]*vecs[[k]], {k, 1, n}];
p = Abs[psi]^2;
vs = Sort[vals];

fmt[x_] := ToString[N[x, 10]];
Print["eig:", " ", StringRiffle[fmt /@ vs[[1;;5]], " "]];
Print["p08:", " ", StringRiffle[fmt /@ p[[1;;8]], " "]];
Print["p37:", " ", fmt[p[[37]]]];
Print["sum:", " ", fmt[Total[p]]];
