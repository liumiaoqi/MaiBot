#!/usr/bin/env Rscript
# probe27_collapse.R — data collapse 折叠图（θ 坐标 vs 名义 β 坐标的对照）
#
# 目的：FSS 的「钱镜头」——如果 θ=β·λ_max 是正确坐标，16 个尺寸的 χ 剖面
#       应在标度变量 (θ-θ_c)·n^(1/ν_θ) 下折叠成一条主曲线；名义 β 坐标
#       （用 1/ν=0.95）则应折得较散。这是「λ 归一是正确坐标」的视觉验证。
#
# 输入：py27bc_fss_output.csv + r27bc_lmax_by_rep.csv
# 输出：probe27_collapse.png（左：名义折叠；右：θ 折叠）
# 用法：Rscript probe27_collapse.R

d <- read.csv("py27bc_fss_output.csv")
lmx <- read.csv("r27bc_lmax_by_rep.csv")

# per (size, rep, beta) 的 mean chi（分析主口径）
agg <- aggregate(chi ~ size + rep + beta, data = d, FUN = mean)
agg <- merge(agg, lmx[, c("size", "rep", "lmax")], by = c("size", "rep"))
sizes <- sort(unique(agg$size))

peak5 <- function(xs, ys) {
  i <- which.max(ys)
  lo <- max(1, i - 2); hi <- min(length(xs), i + 2)
  if (hi - lo >= 2) {
    fitq <- lm(ys[lo:hi] ~ xs[lo:hi] + I(xs[lo:hi]^2))
    cf <- coef(fitq)
    if (is.finite(cf[3]) && cf[3] < 0) {
      xv <- -cf[2] / (2 * cf[3])
      if (xv >= xs[lo] && xv <= xs[hi]) return(unname(xv))
    }
  }
  unname(xs[i])
}

# per (size,rep) 峰位与 θ_c
info <- list()
for (n in sizes) {
  for (r in sort(unique(agg$rep[agg$size == n]))) {
    sub <- agg[agg$size == n & agg$rep == r, ]
    sub <- sub[order(sub$beta), ]
    bp <- peak5(sub$beta, sub$chi)
    info[[length(info) + 1]] <- data.frame(size = n, rep = r, beta_c = bp,
                                           theta_c = bp * sub$lmax[1])
  }
}
I <- do.call(rbind, info)
Im <- aggregate(cbind(beta_c, theta_c) ~ size, data = I, FUN = mean)

# per-size 剖面（跨 rep mean）+ 每 size 的 mean λ
AGG <- aggregate(chi ~ size + beta, data = d, FUN = mean)
lam_mean <- aggregate(lmax ~ size, data = lmx, FUN = mean)
A <- merge(AGG, lam_mean, by = "size")
A <- merge(A, Im, by = "size")
A$theta <- A$beta * A$lmax
A$cb <- A$chi / A$beta
A$cb_pk <- ave(A$cb, A$size, FUN = max)
A$yn <- A$cb / A$cb_pk
A$xn <- (A$beta - A$beta_c) * A$size^0.95     # 名义标度变量（1/nu=0.95）
A$xt <- (A$theta - A$theta_c) * A$size^0.376  # θ 标度变量（1/nu_theta=0.376）

png("probe27_collapse.png", width = 1060, height = 500)
par(mfrow = c(1, 2), mar = c(4.5, 4.5, 3, 1))
cols <- rainbow(length(sizes))

plot(NA, xlim = c(-2.5, 2.5), ylim = c(0, 1.08),
     xlab = "(beta - beta_c) * n^0.95", ylab = "(chi/beta) / peak",
     main = "nominal beta collapse (1/nu = 0.95)")
for (j in seq_along(sizes)) {
  s <- sizes[j]
  sub <- A[A$size == s, ]
  sub <- sub[order(sub$xn), ]
  lines(sub$xn, sub$yn, col = cols[j], lwd = 1.6)
}

plot(NA, xlim = c(-2.5, 2.5), ylim = c(0, 1.08),
     xlab = "(theta - theta_c) * n^0.376", ylab = "(chi/beta) / peak",
     main = "theta = beta*lambda collapse (1/nu_theta = 0.376)")
for (j in seq_along(sizes)) {
  s <- sizes[j]
  sub <- A[A$size == s, ]
  sub <- sub[order(sub$xt), ]
  lines(sub$xt, sub$yn, col = cols[j], lwd = 1.6)
}
legend("topright", legend = sizes, col = cols, lwd = 1.6, cex = 0.58, ncol = 2)
dev.off()
cat("figure: probe27_collapse.png\n")
cat("(16 curves per panel, one per size; colors shared across panels)\n\n")

# ---- collapse-quality scan: s minimizing spread of collapsed curves ----
# 第二个独立的 1/nu 估计器（用全部剖面而非单点峰位——对"小端敏感"的天然对策）
collapse_score <- function(s, coord = "theta") {
  sel <- abs(A$beta - A$beta_c) <= 0.56
  if (coord == "theta") {
    xt <- (A$theta[sel] - A$theta_c[sel]) * A$size[sel]^s
  } else {
    xt <- (A$beta[sel] - A$beta_c[sel]) * A$size[sel]^s
  }
  yn <- A$yn[sel]
  bins <- cut(xt, breaks = 40)
  ss <- 0; cnt <- 0
  for (b in levels(bins)) {
    v <- yn[bins == b]
    if (length(v) >= 3) { ss <- ss + var(v); cnt <- cnt + 1 }
  }
  if (cnt > 0) ss / cnt else NA
}
s_grid <- seq(0.10, 1.20, by = 0.01)
scores_t <- sapply(s_grid, collapse_score, coord = "theta")
scores_b <- sapply(s_grid, collapse_score, coord = "beta")
st <- s_grid[which.min(scores_t)]
sb <- s_grid[which.min(scores_b)]
cat(sprintf("collapse scan (theta): best 1/nu_theta = %.3f  (score %.4f)\n",
            st, min(scores_t, na.rm = TRUE)))
cat(sprintf("collapse scan (nominal): best 1/nu = %.3f  (score %.4f)\n",
            sb, min(scores_b, na.rm = TRUE)))
cat(sprintf("  [peak-drift fits gave: theta 0.376 / nominal 0.950 -- two independent estimators]\n"))
