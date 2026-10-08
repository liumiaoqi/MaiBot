% probe5_tn_compression.m -- exp37 tensor-network compression:
% spectrum + Eckart-Young + exact replay of the retrieval table + r-scan.
% Run: matlab -batch "probe5_tn_compression"

base = fileparts(mfilename('fullpath'));
Dp = fullfile(base, 'data_exp37');
X = readmatrix(fullfile(Dp, 'X.csv'));
Q = readmatrix(fullfile(Dp, 'queries.csv'));
L = readmatrix(fullfile(Dp, 'labels.csv'));
Cen = readmatrix(fullfile(Dp, 'centers.csv'));

fprintf('=== probe5 MATLAB (R2025b) ===\n');
sv = svd(X);
fprintf('--- spectrum (top 16) ---\n');
fprintf('%.3f  ', sv(1:16));
fprintf('\nsigma8/sigma9 = %.3f   MP noise edge ~ %.3f\n', sv(8)/sv(9), 0.3*(sqrt(200)+sqrt(64)));
fprintf('centers singular values (8): ');
fprintf('%.3f  ', svd(Cen));
fprintf('\n');

fprintf('--- Eckart-Young predicted error ---\n');
for r = [3 6 15 30]
  e = sqrt(sum(sv(r+1:end).^2)/sum(sv.^2));
  fprintf('r=%d : %.3f\n', r, e);
end

[U, S, V] = svd(X, 'econ');

fprintf('--- retrieval replay (fixed data) ---\n');
cfgs = { 'full', 0, 0; 'trunc K=100', 100, 100; 'tn r=15', 15, 0; 'trunc K=40', 40, 160; 'tn r=6', 6, 0 };
for i = 1:size(cfgs, 1)
  acc = runCfg(X, Q, L, U, S, V, cfgs{i,1}, cfgs{i,2}, cfgs{i,3});
  fprintf('%-14s  %3.0f   %3.0f   %3.0f\n', cfgs{i,1}, acc(1)*100, acc(2)*100, acc(3)*100);
end

fprintf('--- r-scan: retrieval accuracy vs r (tn, r=1..30) ---\n');
for r = 1:30
  acc = runCfg(X, Q, L, U, S, V, 'tn', r, 0);
  fprintf('r=%2d : new %3.0f%%  mid %3.0f%%  old %3.0f%%\n', r, acc(1)*100, acc(2)*100, acc(3)*100);
end

function acc = runCfg(X, Q, L, U, S, V, name, param, off)
  T = size(X, 1); N = 8;
  if strcmp(name, 'full')
    cand = X; proj = @(q) q;
  elseif startsWith(name, 'trunc')
    cand = X(end-param+1:end, :); proj = @(q) q;
  else
    r = param;
    cand = U(:, 1:r)*S(1:r, 1:r); proj = @(q) V(:, 1:r)'*q;
  end
  a = zeros(1, 3); c = zeros(1, 3);
  for qi = 1:numel(L)
    lab = L(qi); q = Q(qi, :)';
    sc = cand*proj(q);
    [~, b] = max(sc);
    idx0 = (b - 1) + off;
    tt = min(N - 1, floor(idx0*N/T));
    ok = (tt == lab);
    if lab >= 5, bi = 1; elseif lab >= 2, bi = 2; else, bi = 3; end
    a(bi) = a(bi) + ok; c(bi) = c(bi) + 1;
  end
  acc = a./c;
end
