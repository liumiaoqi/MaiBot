#!/usr/bin/env Rscript
# probe27_theta.R — probe27 θ 口径正式分析（R 侧，与 python 分析器交叉验证）
#
# 输入: py27b_fss_output.csv（v2 主数据，10 尺寸）+ r27b_lmax_by_rep.csv（λ 表）
# 流程: merge → θ=β·λ → 每 (size,rep) 五点二次拟合峰 → 跨 rep 平均
#       → 名义 / θ 双口径 1/ν 扫描拟合 + χ/β ~ λ^a
# 定位: ① lmq 指定 R 为分析工具——θ 口径进 R 正式流程；
#       ② 与 python 分析器（probe27b_analyze.py）形成独立实现交叉验证。
#
# 用法: Rscript probe27_theta.R [csv_path] [lmax_csv]   （默认 py27b 数据）

args <- commandArgs(trailingOnly = TRUE)
csv_path  <- if (length(args) >= 1) args[1] else "py27b_fss_output.csv"
lmax_path <- if (length(args) >= 2) args[2] else "r27b_lmax_by_rep.csv"

d <- read.csv(csv_path)
lmx <- read.csv(lmax_path)
d <- merge(d, lmx[, c("size", "rep", "lmax")], by = c("size", "rep"))
d$theta <- d$beta * d$lmax
sizes <- sort(unique(d$size))
reps <- sort(unique(d$rep))
cat("=== probe27 theta-space analysis (R) ===\n")
cat("rows:", nrow(d), "| sizes:", sizes, "| reps:", reps, "\n\n")

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

rows <- list()
for (n in sizes) {
  bc <- numeric(0); tc <- numeric(0); cp <- numeric(0); lams <- numeric(0)
  for (r in reps) {
    sub <- d[d$size == n & d$rep == r, ]
    if (nrow(sub) == 0) next
    betas <- sort(unique(sub$beta))
    if (length(betas) < 5) next
    means <- sapply(betas, function(b) mean(sub$chi[sub$beta == b]))
    lam <- sub$lmax[1]
    lams <- c(lams, lam)
    bp <- peak5(betas, means)
    bc <- c(bc, bp); tc <- c(tc, bp * lam); cp <- c(cp, max(means))
  }
  rows[[length(rows) + 1]] <- data.frame(size = n, beta_c = mean(bc),
    theta_c = mean(tc), chi_pk = mean(cp), lmax = mean(lams))
}
P <- do.call(rbind, rows)
print(P, row.names = FALSE)

scan_fit <- function(sz, vals) {
  best <- c(-1, NA)
  for (s in seq(0.05, 2.5, by = 0.002)) {
    x <- sz^(-s)
    r2 <- summary(lm(vals ~ x))$r.squared
    if (r2 > best[1]) best <- c(r2, s)
  }
  best
}
fn <- scan_fit(P$size, P$beta_c)
ft <- scan_fit(P$size, P$theta_c)
cat(sprintf("\nnominal: 1/nu = %.3f  (R2=%.4f)\n", fn[2], fn[1]))
cat(sprintf("theta  : 1/nu = %.3f  (R2=%.4f)\n", ft[2], ft[1]))
fA <- lm(log(P$chi_pk / P$beta_c) ~ log(P$lmax))
cat(sprintf("chi/beta ~ lam^%.3f  (R2=%.4f)\n", coef(fA)[2], summary(fA)$r.squared))
cat("(2026-10-14, R-side theta analysis for probe27)\n")
