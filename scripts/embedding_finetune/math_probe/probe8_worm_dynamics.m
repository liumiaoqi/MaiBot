% probe8_worm_dynamics.m -- worm connectome dynamics audit:
% synchronous vs asynchronous, fixed-point validity, collapse-to-all-ones test.
% Run: matlab -batch "probe8_worm_dynamics"

base = fileparts(mfilename('fullpath'));
Dp = fullfile(base, 'data_exp41');
n = 279;
E = readmatrix(fullfile(Dp, 'edges.csv'));
W = zeros(n);
for k = 1:size(E, 1)
  W(E(k,1)+1, E(k,2)+1) = E(k,3);
  W(E(k,2)+1, E(k,1)+1) = E(k,3);
end
rs = readmatrix(fullfile(Dp, 'rowsum.csv'));
inits = readmatrix(fullfile(Dp, 'inits.csv'));
bg = jsondecode(fileread(fullfile(Dp, 'behavior_groups.json')));
fn = fieldnames(bg);

fprintf('=== probe8: worm connectome dynamics audit ===\n');
fprintf('rowsum: min %.4f  all>=0: %d\n', min(rs), all(rs >= 0));

% --- 0. is all-ones a fixed point? ---
h1 = W*ones(n, 1);
step1 = ones(n, 1); step1(h1 < 0) = -1;
fprintf('all-ones fixed point: %d\n', isequal(step1, ones(n, 1)));

% --- 1. synchronous converge (exp41b semantics, 200 iters) ---
Fin = zeros(size(inits, 1), n);
for t = 1:size(inits, 1)
  x = inits(t, :)';
  for it = 1:200
    h = W*x;
    xn = ones(n, 1); xn(h < 0) = -1;
    if isequal(xn, x), x = xn; break; end
    x = xn;
  end
  Fin(t, :) = x';
end

isFix = false(size(inits, 1), 1);
for t = 1:size(inits, 1)
  x = Fin(t, :)'; h = W*x;
  y = ones(n, 1); y(h < 0) = -1;
  isFix(t) = isequal(y, x);
end
act = mean(Fin, 2);
Hneg = sum(Fin < 0, 2);
u = unique(Fin, 'rows');

fprintf('--- sync dynamics (100 inits) ---\n');
fprintf('true fixed points : %d / %d\n', sum(isFix), numel(isFix));
fprintf('final activation  : mean %.4f  min %.4f  max %.4f\n', mean(act), min(act), max(act));
fprintf('-1 count per final: mean %.2f  min %d  max %d  (n=279)\n', mean(Hneg), min(Hneg), max(Hneg));
fprintf('unique final states: %d\n', size(u, 1));

fprintf('--- behavior group activation (replicate exp41b) ---\n');
for i = 1:numel(fn)
  idx = bg.(fn{i}) + 1;
  fprintf('%-22s mean %8.4f\n', fn{i}, mean(mean(Fin(:, idx), 2)));
end

% --- 2. energy non-monotonicity along synchronous trajectories ---
nonmono = 0; steps = 0;
for t = 1:20
  x = inits(t, :)';
  for it = 1:60
    h = W*x;
    xn = ones(n, 1); xn(h < 0) = -1;
    if isequal(xn, x), break; end
    E1 = -0.5*(x'*W*x); E2 = -0.5*(xn'*W*xn);
    steps = steps + 1;
    if E2 > E1 + 1e-12, nonmono = nonmono + 1; end
    x = xn;
  end
end
fprintf('--- energy ---\n');
fprintf('sync energy-increase steps: %d / %d (%.1f%%)\n', nonmono, steps, 100*nonmono/steps);

% --- 3. asynchronous contrast (50 inits) ---
rng(1);
m = 50;
FinA = zeros(m, n);
for t = 1:m
  x = inits(t, :)';
  for it = 1:100
    ord = randperm(n); changed = false;
    for i = ord
      h = W(i, :)*x;
      nv = 1; if h < 0, nv = -1; end
      if nv ~= x(i), x(i) = nv; changed = true; end
    end
    if ~changed, break; end
  end
  FinA(t, :) = x';
end
actA = mean(FinA, 2);
uA = unique(FinA, 'rows');
isFixA = true(m, 1);
for t = 1:m
  x = FinA(t, :)'; h = W*x;
  y = ones(n, 1); y(h < 0) = -1;
  isFixA(t) = isequal(y, x);
end
fprintf('--- async dynamics (50 inits) ---\n');
fprintf('true fixed     : %d / %d\n', sum(isFixA), m);
fprintf('activation     : mean %.4f  min %.4f  max %.4f\n', mean(actA), min(actA), max(actA));
fprintf('unique finals  : %d\n', size(uA, 1));
fprintf('--- async behavior group activation (true fixed points) ---\n');
for i = 1:numel(fn)
  idx = bg.(fn{i}) + 1;
  fprintf('%-22s mean %8.4f\n', fn{i}, mean(mean(FinA(:, idx), 2)));
end
