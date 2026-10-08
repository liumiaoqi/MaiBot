% probe2_corrected_forgetting.m -- exhaustive search over ALL C(30,4)=27405 review
% distributions. Compares: original (exp29) vs corrected v2 (stock / gap gain).
% Runs the same semantics as the Wolfram probe.
% Run: matlab -batch "probe2_corrected_forgetting"

combos = nchoosek(1:30, 4);
M = size(combos, 1);

o  = zeros(M, 1);
vS = zeros(M, 1);
vG = zeros(M, 1);
for i = 1:M
  r = combos(i, :);
  o(i)  = origObs(r);
  vS(i) = v2Obs(r, "stock");
  vG(i) = v2Obs(r, "gap");
end

fprintf('=== probe2 exhaustive: C(30,4) = %d distributions ===\n', M);
u = unique(round(o, 8));
fprintf('orig  unique value count: %d  (value %.4f)\n', numel(u), u(1));
fprintf('stock : min %.4f  max %.4f\n', min(vS), max(vS));
fprintf('gap   : min %.4f  max %.4f\n', min(vG), max(vG));

r = {[27 28 29 30], [1 3 7 14], [7 14 21 28], [1 2 3 4], [20 24 28 30]};
fprintf('--- reference distributions ---\n');
for k = 1:numel(r)
  rr = r{k};
  fprintf('%s : orig %.4f  stock %.4f  gap %.4f\n', mat2str(rr), origObs(rr), v2Obs(rr,"stock"), v2Obs(rr,"gap"));
end

fprintf('--- stock: top5 ---\n');
[~, idx] = sort(vS, 'descend');
for k = 1:5, fprintf('  %s -> %.4f\n', mat2str(combos(idx(k),:)), vS(idx(k))); end
fprintf('--- stock: bottom3 ---\n');
for k = 1:3, fprintf('  %s -> %.4f\n', mat2str(combos(idx(end-k+1),:)), vS(idx(end-k+1))); end

fprintf('--- gap: top5 ---\n');
[~, idx] = sort(vG, 'descend');
for k = 1:5, fprintf('  %s -> %.4f\n', mat2str(combos(idx(k),:)), vG(idx(k))); end
fprintf('--- gap: bottom3 ---\n');
for k = 1:3, fprintf('  %s -> %.4f\n', mat2str(combos(idx(end-k+1),:)), vG(idx(end-k+1))); end

function val = origObs(reviews)
  s0 = 0.7; L0 = 0.1; nd = 31;
  S = s0; L = L0;
  for t = 0:nd
    if any(reviews == t)
      S = s0; L = L + 0.3;
    end
  end
  val = S*exp(-nd/1.0) + L*exp(-nd/200.0);
end

function val = v2Obs(reviews, gain)
  s0 = 0.7; L0 = 0.1; kG = 0.5; nd = 31;
  S = s0; L = L0;
  for t = 1:nd
    S = S*exp(-1/1.0); L = L*exp(-1/200.0);
    if any(reviews == t)
      if gain == "stock"
        L = L + kG*S;
      else
        L = L + kG*(s0 - S);
      end
      S = s0;
    end
  end
  val = S + L;
end
