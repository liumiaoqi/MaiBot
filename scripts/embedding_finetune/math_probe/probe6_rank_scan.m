% probe6_rank_scan.m -- exp37 follow-up: how does low-rank (tensor-network)
% compression behave as conversation rank rises?
% Fix (v2): label lookup via the stored per-message topic array Xlab
% (the "row -> topic" block mapping is only valid for block layout).
% Run: matlab -batch "probe6_rank_scan"

T = 200; D = 64; klist = [8 16 32 64 128];
fprintf('=== probe6: conversation rank scan (T=%d, D=%d, noise=0.3) ===\n', T, D);
modes = {'block', 'inter'};
fprintf('%8s %4s %8s %6s %8s %8s %8s %8s\n', 'mode', 'K', 'gap', 'i*', 'TN r*', 'TN', 'tr100', 'full');
for mi = 1:2
  mode = modes{mi};
  for K = klist
    rng(20260818 + K + 1000*mi);
    Cen = randn(K, D);
    X = zeros(T, D); Xlab = zeros(T, 1);
    for t = 1:T
      if strcmp(mode, 'block')
        k = min(K, floor((t-1)*K/T) + 1);
      else
        k = randi(K);
      end
      Xlab(t) = k;
      X(t, :) = Cen(k, :) + 0.3*randn(1, D);
    end
    nq = 96; Q = zeros(nq, D); L = zeros(nq, 1);
    for i = 1:nq
      k = min(K, ceil(i*K/nq));
      L(i) = k;
      Q(i, :) = Cen(k, :) + 0.3*randn(1, D);
    end

    sv = svd(X);
    [gap, is] = max(sv(1:40)./sv(2:41));

    [U, S, V] = svd(X, 'econ');
    ok = zeros(1, 64);
    for r = 1:64
      ok(r) = accTN(U, S, V, Q, L, r, Xlab);
    end
    [tnAcc, rbest] = max(ok);
    aTr = accTrunc(X, Q, L, 100, Xlab);
    aFull = accTrunc(X, Q, L, T, Xlab);
    fprintf('%8s %4d %8.2f %6d %8d %8.3f %8.3f %8.3f\n', mode, K, gap, is, rbest, tnAcc, aTr, aFull);
  end
end

function a = accTN(U, S, V, Q, L, r, Xlab)
  cand = U(:, 1:r)*S(1:r, 1:r);
  Vr = V(:, 1:r)';
  ok = 0;
  for i = 1:size(Q, 1)
    sc = cand*(Vr*Q(i, :)');
    [~, b] = max(sc);
    ok = ok + (Xlab(b) == L(i));
  end
  a = ok/size(Q, 1);
end

function a = accTrunc(X, Q, L, Kc, Xlab)
  T = size(X, 1);
  cand = X(end-Kc+1:end, :);
  off = T - Kc;
  ok = 0;
  for i = 1:size(Q, 1)
    sc = cand*Q(i, :)';
    [~, b] = max(sc);
    ok = ok + (Xlab(b + off) == L(i));
  end
  a = ok/size(Q, 1);
end
