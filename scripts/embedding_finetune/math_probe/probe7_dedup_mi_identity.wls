(* probe7_dedup_mi_identity.wls -- exp30 "entanglement-entropy dedup":
   identity check of its mutual_information() implementation.
   Claim: the implementation reduces to a closed form
     mi = (1/V) * Sum_{w in x∩y} [ Log[4V] - Log[(cx+1)(cy+1)] ]
   (V = vocab size; cx, cy = in-memory counts; contribution shrinks as counts grow)
   Run: wolframscript -file probe7_dedup_mi_identity.wls *)

Off[General::munfl];
fmt[x_, d_] := ToString[NumberForm[N[x], {16, d}]];
base = DirectoryName[$InputFileName];

loadCSV[p_] := Module[{raw = Import[p, "Table", "FieldSeparators" -> ","]},
  If[NumericQ[raw[[1, 1]]], raw, Map[ToExpression, raw, {2}]]];

sp = Flatten[loadCSV[FileNameJoin[{base, "data_exp30", "sample_pair.csv"}]]];
xp = sp[[1 ;; 15]]; yp = sp[[16 ;; 30]];

miExp30[x_List, y_List, v_: 200] := (1/v)*Total[
  Map[Log[4 v] - Log[(Count[x, #] + 1)*(Count[y, #] + 1)] &, Intersection[x, y]]];

Print["=== probe7: identity of exp30 mutual_information() ==="];
Print["x: ", xp];
Print["y: ", yp];
Print[""];
Print["closed form    : ", fmt[miExp30[xp, yp], 12]];
Print["python exp30   : 0.170989249040   (from py run of exp30 itself)"];
Print["diff           : ", fmt[Abs[miExp30[xp, yp] - 0.170989249040], 6]];
Print[""];
Print["--- per-word contributions (ln(4V) - ln((cx+1)(cy+1))) ---"];
Do[
  Print["w=", w, " cx=", Count[xp, w], " cy=", Count[yp, w],
        "  ->  ", fmt[Log[4*200] - Log[(Count[xp, w] + 1)*(Count[yp, w] + 1)], 6]],
  {w, Intersection[xp, yp]}];
Print[""];
Print["baseline if all counts were 1: a * (ln(4V)-ln4)/V = ",
      fmt[Length[Intersection[xp, yp]]*(Log[800] - Log[4])/200, 6],
      "  (actual = baseline minus freq corrections)"];
