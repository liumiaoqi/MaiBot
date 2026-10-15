# x81 — probe29 / 29b / 30 / 31 关键数独立复算（R 侧）
# §9 补账：四件实验的主量（最大分量占比 S / 低-低边占比）此前未配复算
# 对象（两个确定性图——度序删可精确重现）：
#   A) 度序删 50% 的保留图（= probe29 参照A = probe31 的 M1）  目标 S = 0.8880
#   B) 度序删 85% 的保留图（= probe29b 的度序臂 = probe30 解剖对象）目标 S = 0.4148
#   C) B 的剩余边「低-低占比」（两端原度 ≤ 8）                目标 = 1.000
# 输入：deg50_kept_edges.csv · deg85_kept_edges.csv · deg0_vector.csv（均由 python 侧导出，1-based 边表）

comp <- function(path) {
  e <- as.matrix(read.csv(path, header = FALSE))
  n <- 2500
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
  list(S = max(tabulate(roots)) / n, e = e)
}

cat("== x81: probes 29/29b/30/31 recheck (R side) ==\n")
rA <- comp("deg50_kept_edges.csv")
cat(sprintf("A) deg50 kept: S = %.4f   (target 0.8880)\n", rA$S))
rB <- comp("deg85_kept_edges.csv")
cat(sprintf("B) deg85 kept: S = %.4f   (target 0.4148)\n", rB$S))
deg0 <- scan("deg0_vector.csv", sep = ",", quiet = TRUE)
e <- rB$e
lo <- pmin(deg0[e[, 1]], deg0[e[, 2]])
hi <- pmax(deg0[e[, 1]], deg0[e[, 2]])
cat(sprintf("C) deg85 剩余边低-低占比 = %.4f   (target 1.000)\n", mean(hi <= 8)))
cat(sprintf("   (校验: 剩余边数 = %d)\n", nrow(e)))
cat("done (x81-R).\n")
