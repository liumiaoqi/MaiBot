% probe13_spectrum.m -- complex-analysis pass #1: spectral audit of spreading activation.
% The A_memorix spreading kernel iterates act <- 0.85 * W * act (plus factors).
% Linear convergence requires 0.85 * rho(W) < 1, i.e. g* = 1/rho(W) is the
% critical propagation coefficient. Audit on the real connectome W.
% Run: matlab -batch "probe13_spectrum"

base = fileparts(mfilename('fullpath'));
Dp = fullfile(base, 'data_exp41');
n = 279;
E = readmatrix(fullfile(Dp, 'edges.csv'));
W = zeros(n);
for k = 1:size(E, 1)
  W(E(k,1)+1, E(k,2)+1) = E(k,3);
  W(E(k,2)+1, E(k,1)+1) = E(k,3);
end

fprintf('=== probe13-A: spectral audit of propagation (real connectome) ===\n');
ev = eig(W);                    % symmetric -> real
rho = max(abs(ev));
gstar = 1/rho;
fprintf('rho(W)          = %.4f\n', rho);
fprintf('g* = 1/rho(W)   = %.4f   (critical propagation coefficient)\n', gstar);
fprintf('0.85 * rho(W)   = %.4f   -> linear framework: %s\n', 0.85*rho, ...
  ternary(0.85*rho < 1, 'CONVERGENT', 'DIVERGENT (thresholds/factors will damp it in practice)'));
fprintf('safety margin   = %.2fx  (0.85 vs g*)\n', 0.85/gstar);

fprintf('--- eigenvalue structure ---\n');
fprintf('lambda min %8.3f  max %8.3f  |negative count %d / %d\n', ...
  min(ev), max(ev), sum(ev < 0), n);
fprintf('top 6 |lambda|: ');
[srt, ~] = sort(abs(ev), 'descend');
fprintf('%.3f  ', srt(1:6)); fprintf('\n');

% compare with probe12 Ising beta_c ~ 0.5
fprintf('--- cross-check vs probe12 Ising ---\n');
fprintf('Ising beta_c ~ 0.50 (measured); 1/rho(W) = %.3f -- same order (both O(1) linear-response scales)\n', gstar);

% Gershgorin bound
rs = sum(abs(W), 2);
fprintf('Gershgorin bound: rho <= max row |sum| = %.3f (actual %.3f)\n', max(rs), rho);

% random control
rng(7);
ie = nchoosek(1:n, 2);
sel = randperm(size(ie, 1), 1989);
Wr = zeros(n);
for k = 1:1989
  i0 = ie(sel(k),1); j0 = ie(sel(k),2);
  wv = 2*rand() - 1;
  Wr(i0,j0) = wv; Wr(j0,i0) = wv;
end
evr = eig(Wr); rhor = max(abs(evr));
fprintf('--- random W control ---\n');
fprintf('rho(random) = %.4f  (g*_rand = %.4f)  vs real %.4f\n', rhor, 1/rhor, rho);

fprintf('--- what does g=0.85 mean here? ---\n');
fprintf('real:    0.85/rho = %.3f  -> %s\n', 0.85/rho, ternary(0.85 < gstar, 'BELOW critical', 'ABOVE critical'));
fprintf('random:  0.85/rho = %.3f  -> %s\n', 0.85/rhor, ternary(0.85 < 1/rhor, 'BELOW critical', 'ABOVE critical'));

function s = ternary(c, a, b)
  if c, s = a; else, s = b; end
end
