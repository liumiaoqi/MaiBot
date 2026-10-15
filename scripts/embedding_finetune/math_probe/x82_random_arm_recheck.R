# x82 — probe29 / probe31 随机臂的分布复算（R 侧，replicate 对拍）
# 起因：§9 复算口径修正——「不可逐位复现 ≠ 不可复算」：随机臂的复算对象是**分布统计量**。
#
# 对象（对拍 python 侧读数）：
#   A) probe29 随机删 50% 的 S 分布     python: 中位 0.9924 · [p10,p90]=[0.990,0.995]（20 次）
#   B) probe31 M3 随机删 85%→随机恢复 35% python: 中位 0.9914 · p10=0.9891（10 次）
#
# 方法：R 侧**独立实现 + 独立重抽样**（R 内置随机源；随机源质量由 python 侧硬随机负责，
#       本复算只对拍「统计量的计算管线」）。
# 预登记判据：**中位数互落对方 [p10,p90] 区间**（两套实现的分布对拍）。
# 输入：knn_edges.csv（1-based 全边表，10634 行——x80 时已导出）

e0 <- as.matrix(read.csv("knn_edges.csv", header = FALSE))
n <- 2500L
M <- nrow(e0)

S_of <- function(kept_rows) {
  e <- e0[kept_rows, , drop = FALSE]
  parent <- 1:n
  for (k in 1:nrow(e)) {
    a <- e[k, 1]; b <- e[k, 2]
    while (parent[a] != a) a <- parent[a]
    while (parent[b] != b) b <- parent[b]
    if (a != b) parent[a] <- b
  }
  roots <- integer(n)
  for (i in 1:n) {
    r <- i
    while (parent[r] != r) r <- parent[r]
    roots[i] <- r
  }
  max(tabulate(roots)) / n
}

NREP_A <- 20L
NREP_B <- 10L
k50 <- round(M * 0.50)
k85 <- round(M * 0.85)
k35 <- k85 - k50

sa <- numeric(NREP_A)
for (rep in 1:NREP_A) {
  drop <- sample.int(M, k50)
  sa[rep] <- S_of(setdiff(1:M, drop))
}
sb <- numeric(NREP_B)
for (rep in 1:NREP_B) {
  d85 <- sample.int(M, k85)
  keep_drop <- setdiff(d85, sample(d85, k35))   # 恢复后仍被删的边
  sb[rep] <- S_of(setdiff(1:M, keep_drop))
}

cat("== x82: random-arm distribution recheck (R side) ==\n")
cat(sprintf("A) random-drop-50%% : median=%.4f  [p10,p90]=[%.4f,%.4f]  (python: 0.9924 [0.990,0.995])\n",
            median(sa), quantile(sa, 0.1), quantile(sa, 0.9)))
cat(sprintf("B) drop85-recover35: median=%.4f  p10=%.4f  (python: 0.9914 p10 0.9891)\n",
            median(sb), quantile(sb, 0.1)))
cat("判据：中位数互落对方 [p10,p90]\n")
cat("done (x82-R).\n")
