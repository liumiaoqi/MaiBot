% probe1_forgetting.m -- exp29 quantum forgetting models: MATLAB numerical cross-check
% vs Wolfram probe1_forgetting.wls and the original Python exp29.
% Run: matlab -batch "probe1_forgetting"
s0 = 1.0; ts = 1.0; tl = 200.0; c0 = 0.1; cons = 0.3;
EBB = [0 1.00; 0.33 0.58; 1 0.44; 9 0.36; 24 0.33; 48 0.28; 144 0.25; 744 0.21];

t = 0:31;
g  = arrayfun(@(x) max(0.2, s0*exp(-x/24)), t);
qa = arrayfun(@(x) max(0.2, s0*0.95^x), t);
q2 = arrayfun(@(x) 0.7*s0*exp(-x/ts) + c0*s0*exp(-x/tl), t);

fprintf('=== MATLAB cross-check (R2025b) ===\n');
fprintf('granular : MAE %.5f   31d %.2f%%\n', maeOf(g, EBB), g(32)*100);
fprintf('ampdamp  : MAE %.5f   31d %.2f%%\n', maeOf(qa, EBB), qa(32)*100);
fprintf('twolevel : MAE %.5f   31d %.2f%%\n', maeOf(q2, EBB), q2(32)*100);

r1 = reviewCurve([1], 31);
r4 = reviewCurve([1 3 7 14], 31);
fprintf('review{1}        31d %.4f\n', r1(32));
fprintf('review{1,3,7,14} 31d %.4f\n', r4(32));

fprintf('--- strategy independence (4 reviews, different distributions) ---\n');
cram = reviewCurve([27 28 29 30], 31);
midb = reviewCurve([14 15 16 17], 31);
fprintf('crammed  {27,28,29,30} 31d %.4f\n', cram(32));
fprintf('midblock {14,15,16,17} 31d %.4f\n', midb(32));

rng(42);
for k = 1:5
  rev = sort(randperm(30, 4));
  rc = reviewCurve(rev, 31);
  fprintf('random4 #%d %s -> 31d %.4f\n', k, mat2str(rev), rc(32));
end

fprintf('--- closed form ret31(n) = 0.7e-31 + (0.1+0.3n)e-31/200 ---\n');
for n = 0:5
  fprintf('n=%d -> %.4f\n', n, 0.7*exp(-31) + (0.1 + 0.3*n)*exp(-31/200));
end

function m = maeOf(curve, EBB)
  v = zeros(size(EBB, 1), 1);
  for i = 1:size(EBB, 1)
    day = EBB(i, 1)/24;
    i0 = floor(day);
    i1 = min(i0 + 1, numel(curve) - 1);
    frac = day - i0;
    val = curve(i0 + 1)*(1 - frac) + curve(i1 + 1)*frac;
    v(i) = abs(val - EBB(i, 2));
  end
  m = mean(v);
end

function out = reviewCurve(reviews, n)
  S = 0.7; L = 0.1;
  out = zeros(1, n + 1);
  for t = 0:n
    if any(reviews == t)
      S = 0.7; L = L + 0.3;
    end
    out(t + 1) = S*exp(-t/1.0) + L*exp(-t/200.0);
  end
end
