% probe3_grover_vs_softmax.m -- exp31 mechanism: cross-check + k-scan + Monte Carlo.
% Companion to probe3_grover_vs_softmax.wls
% Run: matlab -batch "probe3_grover_vs_softmax"

s = [0.9 0.7 0.5 0.3 0.1];
fprintf('=== probe3 MATLAB cross-check (R2025b) ===\n');

% --- 1. three-way check for k = 1, 2, 8 ---
fprintf('--- mechanism check ---\n');
for k = [1 2 8]
  p = s.^k; p = p/sum(p);
  fprintf('k=%d : %s\n', k, sprintf('%.9f  ', p));
end

% --- 2. k-scan: P_main / P_sec / entropy ---
fprintf('--- k-scan (P1=main 0.9, P2=sec 0.7, H=entropy nats) ---\n');
ks = [0.5 1 2 3 4 6 8 12 16];
for k = ks
  p = s.^k; p = p/sum(p);
  H = -sum(p.*log(p));
  fprintf('k=%5.1f : P_main=%.4f  P_sec=%.4f  H=%.4f  P_last=%.6f\n', k, p(1), p(2), H, p(end));
end

% argmax of P_sec over dense k grid
kg = 0.1:0.01:20;
Psec = arrayfun(@(k) ((0.7^k)/sum(s.^k)), kg);
[pm, im] = max(Psec);
fprintf('P_sec argmax: %.4f at k = %.2f\n', pm, kg(im));

% k where P_last falls below 0.001 (effectively gone)
kdrop = kg(find(arrayfun(@(k) (0.1^k)/sum(s.^k), kg) < 0.001, 1));
fprintf('P_last < 0.001 from k = %.2f\n', kdrop);

% --- 3. Monte Carlo inverse-transform sampling, k=2 ---
fprintf('--- Monte Carlo check (k=2, 1e6 draws) ---\n');
p2 = s.^2; p2 = p2/sum(p2);
rng(7);
n = 1e6;
u = rand(n, 1);
edges = [0 cumsum(p2)];
edges(end) = 1;
cnt = histcounts(u, edges);
freq = cnt/n;
fprintf('analytic  : %s\n', sprintf('%.5f  ', p2));
fprintf('MC (1e6)  : %s\n', sprintf('%.5f  ', freq));
fprintf('max |diff| = %.5f  (expected ~ 1/sqrt(n) = %.5f)\n', max(abs(freq - p2)), 1/sqrt(n));

% --- 4. ratio closure form check ---
fprintf('--- ratio P1/P2 vs (0.9/0.7)^k ---\n');
for k = [1 2 4 8]
  p = s.^k; p = p/sum(p);
  fprintf('k=%d : ratio=%.4f   closed form=%.4f\n', k, p(1)/p(2), (0.9/0.7)^k);
end
