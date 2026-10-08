% probe7_dedup_metrics.m -- exp30 dedup: five metrics compared on fixed data.
% Cross-check (jaccard/cosine/mi30 vs python), plus two NEW metrics:
%   MI2  : standard 2x2 contingency-table mutual information
%   idfJ : idf-weighted Jaccard
% Plus the corrected test: constrained same-topic low-overlap pairs.
% Run: matlab -batch "probe7_dedup_metrics"

base = fileparts(mfilename('fullpath'));
Dp = fullfile(base, 'data_exp30');
V = 200;
names = {'redundant', 'independent', 'syn00', 'syn10', 'syn30', 'syn50', 'constrained'};
P = struct();
for i = 1:numel(names)
  P.(names{i}) = readmatrix(fullfile(Dp, [names{i} '.csv']));
end
PY = readmatrix(fullfile(Dp, 'py_metrics.csv'));

fprintf('=== probe7: exp30 dedup metric audit ===\n');

% --- 1. cross-check vs python ---
fprintf('--- cross-check vs python (max abs diff) ---\n');
for i = 1:numel(names)
  P_ = P.(names{i});
  j = zeros(100, 1); c = zeros(100, 1); m = zeros(100, 1);
  for k = 1:100
    x = P_(k, 1:15); y = P_(k, 16:30);
    j(k) = fJaccard(x, y); c(k) = fCosine(x, y, V); m(k) = fMi(x, y, V);
  end
  fprintf('%-12s j=%.1e  c=%.1e  mi=%.1e\n', names{i}, ...
    max(abs(j - PY(i, 1:100)')), max(abs(c - PY(i, 101:200)')), max(abs(m - PY(i, 201:300)')));
end

% --- 2. idf from pool ---
allA = [];
for i = 1:6
  P_ = P.(names{i});
  allA = [allA; P_(:, 1:15); P_(:, 16:30)];
end
Ndoc = size(allA, 1); df = zeros(V, 1);
for i = 1:Ndoc
  uw = unique(allA(i, :));
  df(uw + 1) = df(uw + 1) + 1;
end
idf = log(Ndoc./df);

% --- 3. five metrics per dataset ---
store = cell(numel(names), 1);
fprintf('--- metric means ---\n');
fprintf('%-12s %9s %9s %9s %9s %9s\n', 'dataset', 'jaccard', 'cosine', 'mi30', 'MI2', 'idfJ');
for i = 1:numel(names)
  P_ = P.(names{i}); A = zeros(100, 5);
  for k = 1:100
    x = P_(k, 1:15); y = P_(k, 16:30);
    A(k, :) = [fJaccard(x, y), fCosine(x, y, V), fMi(x, y, V), fMI2(x, y, V), fIdfJ(x, y, idf)];
  end
  store{i} = A;
  fprintf('%-12s %9.4f %9.4f %9.4f %9.4f %9.4f\n', names{i}, mean(A));
end

% --- 4. separation d vs independent ---
ind = store{2};
mnames = {'jaccard', 'cosine', 'mi30', 'MI2', 'idfJ'};
fprintf('--- separation d (vs independent, pooled std) ---\n');
for src = [1 7]
  fprintf('%s:\n', names{src});
  for mm = 1:5
    a1 = store{src}(:, mm); a2 = ind(:, mm);
    d = (mean(a1) - mean(a2))/sqrt((var(a1) + var(a2))/2);
    fprintf('  %-8s mean %8.4f  d=%6.2f\n', mnames{mm}, mean(a1), d);
  end
end

% --- 5. correlation of mi30 with jaccard ---
pool = [store{1}; store{2}];
cc = corrcoef(pool(:, 1), pool(:, 3));
fprintf('corr(jaccard, mi30) on red+ind pool = %.4f\n', cc(1, 2));
cc2 = corrcoef(pool(:, 1), pool(:, 4));
fprintf('corr(jaccard, MI2)  on red+ind pool = %.4f\n', cc2(1, 2));

function v = fJaccard(x, y)
  v = numel(intersect(x, y))/numel(union(x, y));
end

function v = fCosine(x, y, V)
  cx = accumarray(x(:) + 1, 1, [V 1]);
  cy = accumarray(y(:) + 1, 1, [V 1]);
  v = (cx'*cy)/(norm(cx)*norm(cy));
end

function v = fMi(x, y, V)
  w = intersect(x, y);
  tot = 0;
  for k = 1:numel(w)
    cx = sum(x == w(k)); cy = sum(y == w(k));
    tot = tot + log(4*V) - log((cx + 1)*(cy + 1));
  end
  v = tot/V;
end

function v = fMI2(x, y, V)
  sx = unique(x); sy = unique(y);
  a = numel(intersect(sx, sy)); b = numel(sx) - a; c = numel(sy) - a; d = V - a - b - c;
  n = a + b + c + d;
  cells = [a b; c d]; r = sum(cells, 2); cl = sum(cells, 1);
  v = 0;
  for i = 1:2
    for j = 1:2
      p = cells(i, j)/n;
      if p > 0
        v = v + p*log(p/((r(i)/n)*(cl(j)/n)));
      end
    end
  end
end

function v = fIdfJ(x, y, idf)
  v = sum(idf(intersect(x, y) + 1))/sum(idf(union(x, y) + 1));
end
