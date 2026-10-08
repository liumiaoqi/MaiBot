% probe4_hopfield_snr.m -- salience-weighted Hopfield:
% controlled mini-case (cross-check vs Wolfram) + Monte Carlo load scan.
% Run: matlab -batch "probe4_hopfield_snr"

fprintf('=== probe4 MATLAB (R2025b) ===\n');

% --- 1. deterministic mini-case (N=8, M=2, synchronous) ---
s1 = [1 1 1 1 -1 -1 -1 -1]';
s2 = [1 1 -1 -1 1 1 -1 -1]';
Wm = (1.0*(s1*s1') + 0.5*(s2*s2'))/1.5;
Wm(1:9:end) = 0;
x = [1 1 1 1 0 0 0 0]';
for it = 1:50
  x2 = sign(Wm*x);
  x2(x2 == 0) = 1;
  if isequal(x2, x), break; end
  x = x2;
end
fprintf('W row1: %s\n', sprintf('%.7f ', Wm(1,:)));
fprintf('x0    : %s\n', sprintf('%g ', [1 1 1 1 0 0 0 0]));
fprintf('fixed : %s\n', sprintf('%g ', x));
fprintf('recovered s1? %d\n', isequal(x, s1));

% --- 2. Monte Carlo load scan: classic vs weighted ---
Nn = 80;
tiers = [0.3 0.475 0.65 0.825 1.0];
rng(11);
trials = 300;
fprintf('--- load scan (mask 30%%, %d trials each) ---\n', trials);
fprintf('%5s %12s %12s\n', 'M', 'classic', 'weighted');
for M = [5 10 15 20 25 30]
  c = repmat(tiers, 1, M/5);
  okC = 0; okW = 0;
  for tr = 1:trials
    P = 2*(rand(Nn, M) > 0.5) - 1;
    Wc = (P*P')/M; Wc(1:Nn+1:end) = 0;
    Ww = (P .* c)*(P')/sum(c); Ww(1:Nn+1:end) = 0;
    k = randi(M);
    x0 = P(:, k);
    x0(rand(Nn, 1) < 0.3) = 0;
    if isequal(recall(Wc, x0), P(:, k)), okC = okC + 1; end
    if isequal(recall(Ww, x0), P(:, k)), okW = okW + 1; end
  end
  fprintf('%5d %12.3f %12.3f\n', M, okC/trials, okW/trials);
end

% --- 3. per-tier recovery, weighted model, M=20 ---
fprintf('--- per-tier recovery (weighted, M=20, 800 trials) ---\n');
M = 20; c = repmat(tiers, 1, M/5);
hit = zeros(1, 5); tot = zeros(1, 5);
for tr = 1:800
  P = 2*(rand(Nn, M) > 0.5) - 1;
  Ww = (P .* c)*(P')/sum(c); Ww(1:Nn+1:end) = 0;
  k = randi(M);
  x0 = P(:, k);
  x0(rand(Nn, 1) < 0.3) = 0;
  ti = ceil(k/(M/5));
  tot(ti) = tot(ti) + 1;
  if isequal(recall(Ww, x0), P(:, k)), hit(ti) = hit(ti) + 1; end
end
for ti = 1:5
  fprintf('c=%.3f : recovery %.3f  (n=%d)\n', tiers(ti), hit(ti)/tot(ti), tot(ti));
end

function x = recall(W, x)
  Nn = length(x);
  for it = 1:50
    ord = randperm(Nn);
    changed = false;
    for i = ord
      h = W(i, :)*x;
      nv = 1; if h < 0, nv = -1; end
      if nv ~= x(i)
        x(i) = nv;
        changed = true;
      end
    end
    if ~changed, break; end
  end
end
