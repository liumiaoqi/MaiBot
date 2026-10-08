(* probe9_symmetry.wls -- ±1 symmetry of the threshold dynamics on the connectome.
   Lemma: W symmetric, zero diagonal, sign(0)=+1 convention.
     If x is a fixed point of T(x) = sgn(W x), then -x is a fixed point
     IFF (Wx) has no zero component.  (At a zero, the convention breaks the
     antisymmetry: sgn(0)=+1 but -sgn(0) would need -1.)
   Verified exhaustively on the 16-node subnet.
   Run: wolframscript -file probe9_symmetry.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {14, d}]];
base = DirectoryName[$InputFileName];

loadCSV[p_] := Module[{raw = Import[p, "Table", "FieldSeparators" -> ","]},
  If[NumericQ[raw[[1, 1]]], raw, Map[ToExpression, raw, {2}]]];

ed = loadCSV[FileNameJoin[{base, "data_exp41", "sub16_edges.csv"}]];
m = 16;
W16 = ConstantArray[0., {m, m}];
Do[
  i = ed[[k, 1]] + 1; j = ed[[k, 2]] + 1; w = ed[[k, 3]];
  W16[[i, j]] = w; W16[[j, i]] = w,
  {k, Length[ed]}];

step[X_] := -1 + 2 UnitStep[X . W16];
X = Developer`ToPackedArray[Tuples[{-1, 1}, m]];
Y = step[X];
fixRows = Total[Unitize[Abs[X - Y]], {2}];
fixIdx = Flatten[Position[fixRows, 0]];
fixStates = X[[fixIdx]];

Print["=== probe9: ±1 symmetry of threshold dynamics (16-node subnet) ==="];
Print["fixed points: ", Length[fixStates]];
Print["--- pairing audit: is -x also fixed? ---"];
Do[
  xf = fixStates[[k]];
  h = W16 . xf;
  nz = Count[h, _?(Abs[#] < 1.0*^-12 &)];
  minh = Min[Abs[h]];
  hasPair = MemberQ[fixStates, -xf];
  Print["FP", k, "  act=", fmt[Mean[xf], 3],
        "  min|h|=", fmt[minh, 6],
        "  zero comps=", nz,
        "  -x also fixed: ", hasPair,
        If[nz == 0 && hasPair, "   (consistent)", If[nz > 0, "   (zero comp: pairing broken by convention)", ""]]],
  {k, Length[fixStates]}];

(* 2-cycle pairing *)
Z = step[Y];
rows2 = Total[Unitize[Abs[X - Z]], {2}];
cycStates = Select[Transpose[{X, fixRows, rows2}], (#[[2]] =!= 0 && #[[3]] == 0) &][[All, 1]];
nPair = Count[cycStates, c_ /; MemberQ[cycStates, -c]];
Print[""];
Print["2-cycle states: ", Length[cycStates], "   paired (-c also in set): ", nPair, " / ", Length[cycStates]];

Print[""];
Print["theorem (antisymmetry): T(-x) = -T(x) wherever Wx has no zero component;"];
Print["=> fixed points and cycles come in ± pairs away from sign-degenerate points."];
