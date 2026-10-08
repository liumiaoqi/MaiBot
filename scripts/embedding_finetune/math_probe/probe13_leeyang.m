% probe13_leeyang.m (v2) -- Lee-Yang zeros, nested design:
% one mother graph (n=10), induced subgraphs are automatically nested.
% Plus a complete-ferro control. Check: (i) no positive-real roots (finite
% size), (ii) does min|Im| shrink as n grows?
% Run: matlab -batch "probe13_leeyang"

fprintf('=== probe13-B v2: Lee-Yang zeros, NESTED design ===\n');
rng(11);
% mother graph on 10 nodes
I = []; J = [];
for a = 1:10
  for b = a+1:10
    if rand() < 0.5
      I(end+1,:) = [a b]; %#ok<AGROW>
      J(end+1) = (rand() < 0.5)*2 - 1; %#ok<AGROW>
    end
  end
end
fprintf('--- nested glass subgraphs (mother n=10) ---\n');
scanLeeYang(I, J, [4 6 8 10], 'glass-nested');

fprintf('--- complete ferro graphs ---\n');
I2 = []; J2 = [];
for a = 1:10
  for b = a+1:10
    I2(end+1,:) = [a b]; %#ok<AGROW>
    J2(end+1) = 1; %#ok<AGROW>
  end
end
scanLeeYang(I2, J2, [4 6 8 10], 'ferro-complete');

function scanLeeYang(Iall, Jall, ns, tag)
  for n = ns
    sel = Iall(:,1) <= n & Iall(:,2) <= n;
    I = Iall(sel,:); J = Jall(sel);
    m = size(I, 1);
    S = zeros(2^n, 1);
    for st = 0:(2^n - 1)
      x = double(bitget(st, 1:n))*2 - 1;
      s = 0;
      for e = 1:m
        s = s + J(e)*x(I(e,1))*x(I(e,2));
      end
      S(st+1) = s;
    end
    Smin = min(S);
    ks = round((S - Smin)/2);
    K = max(ks);
    c = zeros(1, K+1);
    for i = 1:numel(ks)
      c(ks(i)+1) = c(ks(i)+1) + 1;
    end
    r = roots(flip(c));
    r = r(abs(r) > 1e-12);
    pos = r(real(r) > 0);
    if isempty(pos)
      dmin = NaN;
    else
      dmin = min(abs(imag(pos)));
    end
    onaxis = any(abs(imag(r)) < 1e-9 & real(r) > 1e-9);
    fprintf('%-15s n=%2d: edges %2d, roots %3d | Re>0: %3d | min|Im|: %8.4f | pos-real: %d\n', ...
      tag, n, m, numel(r), numel(pos), dmin, onaxis);
    if n == 10
      [~, si] = sort(abs(imag(pos)), 'ascend');
      pp = pos(si);
      ks2 = min(4, numel(pp));
      fprintf('    closest-to-axis zeros: ');
      for q = 1:ks2
        fprintf('(%.3f %+.3fi) ', real(pp(q)), imag(pp(q)));
      end
      fprintf('\n');
    end
  end
end
