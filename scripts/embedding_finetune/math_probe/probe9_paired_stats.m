% probe9_paired_stats.m (v2) -- ± pairing under sampling:
%  - collect TRUE fixed points (filter non-converged), with basin counts
%  - three statistics: equal / basin-weighted / pairing-canonical
%  - pairing audit in "sampling view" (both members found) vs structural view
%  - basin asymmetry via symmetric closure (missing partner => count 0)
% Run: matlab -batch "probe9_paired_stats"

base = fileparts(mfilename('fullpath'));
Dp = fullfile(base, 'data_exp41');
n = 279;
E = readmatrix(fullfile(Dp, 'edges.csv'));
W = zeros(n);
for k = 1:size(E, 1)
  W(E(k,1)+1, E(k,2)+1) = E(k,3);
  W(E(k,2)+1, E(k,1)+1) = E(k,3);
end
bg = jsondecode(fileread(fullfile(Dp, 'behavior_groups.json')));
fng = fieldnames(bg);
gidx = cell(numel(fng), 1);
for i = 1:numel(fng), gidx{i} = bg.(fng{i}) + 1; end

fprintf('=== probe9: paired attractor statistics (v2) ===\n');

% --- real W ---
[ks, Us, cnt, nFake] = collectFP(W, n, 1000, 2026);
m = numel(ks);
fprintf('--- real W (1000 inits) ---\n');
fprintf('non-converged (filtered): %d\n', nFake);
fprintf('unique true fixed points: %d\n', m);

% spot check
okAll = true;
for i = 1:min(50, m)
  x = Us(i, :)'; h = W*x; y = ones(n, 1); y(h < 0) = -1;
  if ~isequal(y, x), okAll = false; end
end
fprintf('spot-check 50: all valid fixed points: %d\n', okAll);

% zero-component audit + margin (structural pairing expected iff no zero comp)
nz = 0; mins = zeros(m, 1);
for i = 1:m
  x = Us(i, :)'; h = W*x;
  if any(abs(h) < 1e-12), nz = nz + 1; end
  mins(i) = min(abs(h));
end
fprintf('zero-component fixed points: %d / %d  (structural pairing rate = %.1f%%)\n', ...
  nz, m, 100*(m - nz)/m);
fprintf('margin min|h|: min %.2e  median %.4f\n', min(mins), median(mins));

% canonical representatives (lexicographic, group-agnostic)
cmap = containers.Map('KeyType', 'char', 'ValueType', 'any');
for i = 1:m
  k = ks{i}; nk = mat2str(-Us(i, :)');
  if string(k) > string(nk)
    rep = nk; st = -Us(i, :)';
  else
    rep = k; st = Us(i, :)';
  end
  if ~isKey(cmap, rep), cmap(rep) = st; end
end
ck = keys(cmap); mc = numel(ck);
C = zeros(mc, n);
for i = 1:mc, C(i, :) = cmap(ck{i})'; end
fprintf('canonical representatives: %d\n', mc);

% pairing audit
Umap = containers.Map('KeyType', 'char', 'ValueType', 'logical');
for i = 1:m, Umap(ks{i}) = true; end
paired = 0;
for i = 1:m
  if isKey(Umap, mat2str(-Us(i, :)')), paired = paired + 1; end
end
fprintf('pairing (sampling view): %d / %d = %.1f%%\n', paired, m, 100*paired/m);

% three statistics
wet = cnt/sum(cnt);
fprintf('--- group activation: equal / weighted / canonical ---\n');
fprintf('%-22s %10s %10s %10s\n', 'group', 'equal', 'weighted', 'canonical');
for i = 1:numel(fng)
  e1 = mean(mean(Us(:, gidx{i}), 2));
  e2 = sum(wet .* mean(Us(:, gidx{i}), 2));
  e3 = mean(mean(C(:, gidx{i}), 2));
  fprintf('%-22s %10.4f %10.4f %10.4f\n', fng{i}, e1, e2, e3);
end

% basin asymmetry (symmetric closure: missing partner => count 0)
cMapA = containers.Map('KeyType', 'char', 'ValueType', 'double');
for i = 1:m, cMapA(ks{i}) = cnt(i); end
rats = [];
for i = 1:m
  k = ks{i}; nk = mat2str(-Us(i, :)');
  if string(k) < string(nk)
    if isKey(cMapA, nk), c2 = cMapA(nk); else, c2 = 0; end
    rats(end+1) = log((cnt(i) + 0.5)/(c2 + 0.5)); %#ok<AGROW>
  end
end
fprintf('--- basin asymmetry (%d pairs) ---\n', numel(rats));
fprintf('log-ratio(c,-c): mean %.3f  std %.3f  max|.| %.3f\n', ...
  mean(rats), std(rats), max(abs(rats)));
fprintf('(positive = the lex-smaller member reached more often)\n');

% --- random W control ---
fprintf('--- random W control (300 inits) ---\n');
ie = nchoosek(1:n, 2);
rng(7);
sel = randperm(size(ie, 1), 1989);
Wr = zeros(n);
for k = 1:1989
  i0 = ie(sel(k), 1); j0 = ie(sel(k), 2);
  wv = 2*rand() - 1;
  Wr(i0, j0) = wv; Wr(j0, i0) = wv;
end
[k2, U2, c2, f2] = collectFP(Wr, n, 300, 99);
fprintf('non-converged: %d   unique fixed: %d\n', f2, numel(k2));
w2 = c2/sum(c2);
for i = 1:numel(fng)
  e1 = mean(mean(U2(:, gidx{i}), 2));
  e2 = sum(w2 .* mean(U2(:, gidx{i}), 2));
  fprintf('%-22s equal %8.4f  weighted %8.4f\n', fng{i}, e1, e2);
end

function [ks, Us, cnt, nFake] = collectFP(W, n, Nin, seed)
  rng(seed);
  cmap = containers.Map('KeyType', 'char', 'ValueType', 'any');
  ccnt = containers.Map('KeyType', 'char', 'ValueType', 'double');
  nFake = 0;
  for t = 1:Nin
    if t <= round(Nin*0.6)
      x = 2*(rand(n, 1) > 0.5) - 1;
    else
      p = 0.3 + 0.4*rand();
      x = 2*(rand(n, 1) < p) - 1;
    end
    x = asyncConv(W, x);
    h = W*x; y = ones(n, 1); y(h < 0) = -1;
    if ~isequal(y, x)
      nFake = nFake + 1;
      continue
    end
    k = mat2str(x);
    if ~isKey(cmap, k)
      cmap(k) = x; ccnt(k) = 0;
    end
    ccnt(k) = ccnt(k) + 1;
  end
  ks = keys(cmap); m = numel(ks);
  Us = zeros(m, n); cnt = zeros(m, 1);
  for i = 1:m
    Us(i, :) = cmap(ks{i})';
    cnt(i) = ccnt(ks{i});
  end
end

function x = asyncConv(W, x)
  n = length(x);
  for it = 1:200
    ord = randperm(n); changed = false;
    for i = ord
      h = W(i, :)*x;
      nv = 1; if h < 0, nv = -1; end
      if nv ~= x(i), x(i) = nv; changed = true; end
    end
    if ~changed, break; end
  end
end
