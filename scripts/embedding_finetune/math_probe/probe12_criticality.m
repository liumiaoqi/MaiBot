% probe12_criticality.m -- statistical-field-theory pass on the worm connectome:
% Glauber dynamics on E = -1/2 x' W x (signed symmetric W, zero diag).
% Sweep beta; measure chi = N*beta*(<m^2> - <m>^2). A susceptibility peak
% signals a critical point (the "neural criticality" hypothesis probe).
% Controls: random W with same edge count.
% Run: matlab -batch "probe12_criticality"

base = fileparts(mfilename('fullpath'));
Dp = fullfile(base, 'data_exp41');
n = 279;
E = readmatrix(fullfile(Dp, 'edges.csv'));
W = zeros(n);
for k = 1:size(E, 1)
  W(E(k,1)+1, E(k,2)+1) = E(k,3);
  W(E(k,2)+1, E(k,1)+1) = E(k,3);
end

betas = [0.05 0.1 0.15 0.2 0.3 0.4 0.5 0.7 1.0 1.5 2.0 6.0 8.0 10.0];
nrun = 3;
fprintf('=== probe12: Glauber criticality sweep (real connectome, n=%d, %d runs) ===\n', n, nrun);
fprintf('beta   |m|mean    chi          q(EA)\n');
for b = betas
  A_ = zeros(nrun,1); C_ = zeros(nrun,1); Q_ = zeros(nrun,1);
  for r = 1:nrun
    [absm, chi, q, m2] = glauberStats(W, b, 400, 300, 2);
    A_(r) = absm; C_(r) = chi; Q_(r) = q;
  end
  fprintf('%5.2f  %8.4f  %10.2f  %8.4f\n', b, mean(A_), mean(C_), mean(Q_));
end

fprintf('--- random W control ---\n');
rng(7);
ie = nchoosek(1:n, 2);
sel = randperm(size(ie, 1), 1989);
Wr = zeros(n);
for k = 1:1989
  i0 = ie(sel(k),1); j0 = ie(sel(k),2);
  wv = 2*rand() - 1;
  Wr(i0,j0) = wv; Wr(j0,i0) = wv;
end
fprintf('beta   |m|mean    chi          q(EA)      m2\n');
for b = [1 2 3 4 5 6 8]
  [absm, chi, q, m2] = glauberStats(Wr, b, 400, 300, 2);
  fprintf('%5.1f  %8.4f  %10.2f  %8.4f  %8.4f\n', b, absm, chi, q, m2);
end

function [absm, chi, q, m2] = glauberStats(W, beta, nTherm, nSamp, gap)
  n = size(W, 1);
  x = sign(randn(n, 1)); x(x == 0) = 1;
  h = W*x;
  for sw = 1:nTherm
    ord = randperm(n);
    for i = ord
      p = 1.0/(1.0 + exp(-2*beta*h(i)));
      nx = -1; if rand() < p, nx = 1; end
      if nx ~= x(i)
        d = nx - x(i);
        h = h + d*W(:, i);
        x(i) = nx;
      end
    end
  end
  ms = zeros(nSamp, 1); qsw = zeros(nSamp, 1);
  for s = 1:nSamp
    for sw = 1:gap
      ord = randperm(n);
      for i = ord
        p = 1.0/(1.0 + exp(-2*beta*h(i)));
        nx = -1; if rand() < p, nx = 1; end
        if nx ~= x(i)
          d = nx - x(i);
          h = h + d*W(:, i);
          x(i) = nx;
        end
      end
    end
    qsw(s) = mean(x)^2;
    ms(s) = mean(x);
  end
  m2 = mean(qsw);
  absm = mean(abs(ms));
  chi = n*beta*(m2 - mean(ms)^2);
  % EA-like overlap: average of site-magnetization^2 (sample-based, single run)
  q = m2;
end
