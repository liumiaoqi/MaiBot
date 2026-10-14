(* probe23_interference_identity.wls -- exp61 audit (symbolic part):
   1. 3-node toy: exact CTQW closed forms — where does "interference" live?
   2. two-source identity (symbolic): p_q(2src) = incoherent + Re[conj(psi_a)*psi_b]
   Run: wolframscript -file probe23_interference_identity.wls *)

fmt[x_, d_] := ToString[NumberForm[N[x], {16, d}]];

Print["=== probe23: exp61 interference identities (symbolic) ==="];
Print[""];

(* --- 1. 3-node line: A = [[0,1,0],[1,0,1],[0,1,0]] --- *)
Aline = {{0, 1, 0}, {1, 0, 1}, {0, 1, 0}};
{ev, evec} = Eigensystem[Aline];
evec = Normalize /@ evec;
Print["--- 1. 3-node line, source at node 0 ---"];
Print["eigenvalues (exact): ", ev];
psi0 = {1, 0, 0};
coef = evec . psi0;
psi[t_] := Sum[coef[[k]] Exp[-I ev[[k]] t] evec[[k]], {k, 1, 3}];
p = Abs[psi[t]]^2 // ComplexExpand // Simplify;
Print["p0(t) = ", p[[1]]];
Print["p1(t) = ", p[[2]]];
Print["p2(t) = ", p[[3]]];
Print["=> interference = cross terms between eigenvalues; here beats at |lambda_i - lambda_j|"];
Print[""];

(* --- 2. two-source identity (3-line, sources 0 and 1) --- *)
psia[t_] := Sum[(evec[[k]] . UnitVector[3, 1]) Exp[-I ev[[k]] t] evec[[k]], {k, 1, 3}];
psib[t_] := Sum[(evec[[k]] . UnitVector[3, 2]) Exp[-I ev[[k]] t] evec[[k]], {k, 1, 3}];
pq = Abs[(psia[t] + psib[t])/Sqrt[2]]^2 // ComplexExpand // Simplify;
pinc = (Abs[psia[t]]^2 + Abs[psib[t]]^2)/2 // ComplexExpand // Simplify;
interf = Re[Conjugate[psia[t]] psib[t]] // ComplexExpand // Simplify;
res = Table[(pq[[i]] - pinc[[i]] - interf[[i]]) // Simplify, {i, 1, 3}];
Print["--- 2. two-source identity: p_q = p_incoherent + interference ---"];
Print["residual (should be 0 for all nodes): ", res];
Print[""];
Print["interference term per node:"];
Do[Print["  node ", i - 1, ": ", interf[[i]]], {i, 1, 3}];
Print[""];
Print["=> identity holds exactly; the interference term is a RE part of a product of"];
Print["   two coherent amplitudes -- real, oscillatory, can be negative."];
Print[""];

(* --- 3. triangle for contrast --- *)
Atri = {{0, 1, 1}, {1, 0, 1}, {1, 1, 0}};
{ev3, evec3} = Eigensystem[Atri];
evec3 = Orthogonalize[evec3];
psi0b = {1, 0, 0};
coefb = evec3 . psi0b;
psib2[t_] := Sum[coefb[[k]] Exp[-I ev3[[k]] t] evec3[[k]], {k, 1, 3}];
pb = Abs[psib2[t]]^2 // ComplexExpand // Simplify;
Print["--- 3. triangle (contrast): eigenvalues ", ev3, " ---"];
Print["p0(t) = ", pb[[1]]];
Print["=> on a degenerate/compact graph the interference pattern differs (different beat set)"];
