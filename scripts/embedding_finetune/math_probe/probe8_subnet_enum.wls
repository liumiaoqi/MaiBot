(* probe8_subnet_enum.wls -- 16-node subnet exhaustive enumeration:
   exact counts of fixed points / 2-cycles under synchronous dynamics.
   Run: wolframscript -file probe8_subnet_enum.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {14, d}]];
base = DirectoryName[$InputFileName];

loadCSV[p_] := Module[{raw = Import[p, "Table", "FieldSeparators" -> ","]},
  If[NumericQ[raw[[1, 1]]], raw, Map[ToExpression, raw, {2}]]];

ed = loadCSV[FileNameJoin[{base, "data_exp41", "sub16_edges.csv"}]];
nodes = Flatten[loadCSV[FileNameJoin[{base, "data_exp41", "sub16_nodes.csv"}]]];
m = 16;
W16 = ConstantArray[0., {m, m}];
Do[
  i = ed[[k, 1]] + 1; j = ed[[k, 2]] + 1; w = ed[[k, 3]];
  W16[[i, j]] = w; W16[[j, i]] = w,
  {k, Length[ed]}];

Print["=== probe8: 16-node subnet (" , Length[ed], " edges) exhaustive enumeration ==="];
Print["nodes: ", nodes];

step[X_] := -1 + 2 UnitStep[X . W16];

X = Developer`ToPackedArray[Tuples[{-1, 1}, m]];
Print["states: ", Length[X]];

Y = step[X];
fixRows = Total[Unitize[Abs[X - Y]], {2}];
Z = step[Y];
rows2 = Total[Unitize[Abs[X - Z]], {2}];

nFix = Count[fixRows, 0];
pairs = Transpose[{fixRows, rows2}];
nBack2 = Count[pairs, {_, 0}];       (* states with T(T(x)) = x *)
n2cycle = nBack2 - nFix;             (* exactly period 2 (states) *)

Print["fixed points      : ", nFix];
Print["2-cycle states    : ", n2cycle, "  (", n2cycle/2, " cycles)"];
Print["other (period>=3) : ", Length[X] - nBack2];

(* is all-ones a fixed point in the subnet? *)
one16 = ConstantArray[1.0, m];
Print["all-ones fixed in subnet: ", (step[{one16}][[1]] == one16)];

(* what do the fixed points look like? show a few *)
fixIdx = Flatten[Position[fixRows, 0]];
If[Length[fixIdx] > 0,
  Print["first fixed points (up to 5):"];
  Do[Print["  ", X[[fixIdx[[k]]]], "  act=", fmt[Mean[X[[fixIdx[[k]]]]], 3]],
    {k, 1, Min[5, Length[fixIdx]]}]];
