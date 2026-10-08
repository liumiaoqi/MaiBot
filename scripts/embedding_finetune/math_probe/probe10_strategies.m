% probe10_strategies.m -- exp32 strategy zoo + threshold scan:
% replicates the four original strategies, adds two candidates
% (hrrn = largest h/rate first; round = strict rotation), compares against
% the theoretical floor 252 = STEPS * sum(rates).
% Run: matlab -batch "probe10_strategies"

STEPS = 168; RATES = [0.8 0.4 0.3]; IB = 1.2; SC = 0.2; TP = 0.05;
floor_ = STEPS*sum(RATES);
fprintf('=== probe10: strategy zoo (floor = %.0f) ===\n', floor_);

rng(2026);
modes = {'greedy', 'inertia', 'anneal', 'quantum', 'hrrn', 'round', 'wrr'};
fprintf('%-9s %8s %6s %6s %10s\n', 'mode', 'hunger', 'max', 'sw', 'vs_floor');
for mi = 1:numel(modes)
  R = zeros(200, 3);
  for t = 1:200
    R(t, :) = simOne(modes{mi}, STEPS, RATES, IB, SC, TP, 5.0);
  end
  mh = mean(R(:, 1));
  fprintf('%-9s %8.0f %6.1f %6.1f %9.2fx\n', modes{mi}, mh, mean(R(:, 2)), mean(R(:, 3)), mh/floor_);
end

fprintf('--- inertia threshold scan ---\n');
fprintf('%6s %8s %6s %6s\n', 'thr', 'hunger', 'max', 'sw');
for thr = [0 1 2 3 5 8 12 20]
  R = zeros(200, 3);
  for t = 1:200
    R(t, :) = simOne('inertia', STEPS, RATES, IB, SC, TP, thr);
  end
  fprintf('%6g %8.0f %6.1f %6.1f\n', thr, mean(R(:, 1)), mean(R(:, 2)), mean(R(:, 3)));
end

function out = simOne(mode, STEPS, RATES, IB, SC, TP, THR)
  h = zeros(1, 3); cur = 1; th = 0; mh = 0; sw = 0; T = 10;
  last = zeros(1, 3); K = [2.3195 3.2800 3.7878];
  for st = 1:STEPS
    h = h + RATES;
    h = min(h, 30);
    th = th + sum(h);
    mh = max(mh, max(h));
    others = setdiff(1:3, cur);
    switch mode
      case 'greedy'
        [~, nxt] = max(h);
      case 'inertia'
        if any(h(others) > h(cur)*IB + THR)
          [~, im] = max(h(others)); nxt = others(im);
        else
          nxt = cur;
        end
      case 'anneal'
        gain = max(h(others) - h(cur));
        if gain > 0 && rand() < exp(-SC/max(T, 0.1))
          [~, im] = max(h(others)); nxt = others(im);
        else
          nxt = cur;
        end
        T = T*0.985;
      case 'quantum'
        swt = any(h(others) > h(cur)*IB + THR);
        if swt || rand() < TP
          v = h(others)./RATES(others);
          [~, im] = max(v); nxt = others(im);
        else
          nxt = cur;
        end
      case 'hrrn'
        v = h./RATES;
        [~, nxt] = max(v);
      case 'round'
        nxt = mod(cur, 3) + 1;
      case 'wrr'
        v = last + K;
        [~, nxt] = min(v);
    end
    if nxt ~= cur, sw = sw + 1; end
    eff = IB; if nxt ~= cur, eff = 1 - SC; end
    h(nxt) = max(0, h(nxt) - 6*eff);
    last(nxt) = st;
    cur = nxt;
  end
  out = [th, mh, sw];
end
