# x80 — probe28 主量独立复算（R 侧）
# 口径：P = D^-1 A（随机游走转移）；λ₂ = 第二大 |eig|；gap = 1 - λ₂
# 对拍目标：probe28（numpy 侧）λ₂ = 0.955875 · gap = 0.044125
# 输入：knn_edges.csv（1-based 全边表，10634 行）
# 注：WL 路线首次尝试超时（2500×2500 数值特征值对 Wolfram 太重）——本脚本为替代复算路线

e <- as.matrix(read.csv("knn_edges.csv", header = FALSE))
n <- 2500
A <- matrix(0, n, n)
for (k in 1:nrow(e)) {
  A[e[k, 1], e[k, 2]] <- 1
  A[e[k, 2], e[k, 1]] <- 1
}
deg <- rowSums(A)
P <- A / deg
ev <- eigen(P, only.values = TRUE)$values
mag <- sort(Mod(ev), decreasing = TRUE)
cat("top |eig| (R):", mag[1:4], "\n")
cat(sprintf("lambda2 (R) = %.6f\n", mag[2]))
cat(sprintf("gap     (R) = %.6f\n", 1 - mag[2]))
cat("reported (numpy): lambda2 = 0.955875 | gap = 0.044125\n")
cat("done (x80-R).\n")
