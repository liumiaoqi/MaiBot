#!/usr/bin/env Rscript
# probe27_fss.R — FSS 普适性分析（R 侧）：峰定位 → χ_max 标度（γ/ν）→
#   β_c(n) 漂移（1/ν、β_∞）→ 硬/伪随机源对照（P vs H）。
#
# 输入 : py27_fss_output.csv（每 run 一行：size,rep,beta,source,run,seed,absm,chi,q）
# 输出 : 控制台报告 + 两张 png
# 用法 : Rscript probe27_fss.R [csv路径] [--selftest]
#
# 方法注：临界区 χ 分布重尾 ⇒ 主统计量用 median（附 IQR）；
#   峰定位 = 剖面 argmax + 三点抛物线顶点细化；
#   1/ν 估计 = 网格扫描 n^{-s} 线性化 R² 最大（FSS 文献常用鲁棒法）。

args <- commandArgs(trailingOnly = TRUE)
selftest <- "--selftest" %in% args
args <- setdiff(args, "--selftest")
csv_path <- if (length(args) >= 1) args[1] else "py27_fss_output.csv"

if (selftest) {
  cat("=== SELFTEST: synthetic data (known exponents) ===\n")
  set.seed(42)
  sizes_s <- c(40, 60, 90, 130, 190, 279)
  A0 <- 2.0; gnu_true <- 1.8
  b0 <- 0.8; b1 <- 10.0; snu_true <- 0.6   # beta_c = b0 + b1 * n^{-snu_true}
  rows <- list()
  for (n in sizes_s) {
    bc <- b0 + b1 * n^(-snu_true)
    cm <- A0 * n^gnu_true
    betas <- bc + seq(-0.5, 0.5, length.out = 15)
    for (b in betas) {
      cval <- cm / (1 + ((b - bc) / 0.15)^2) * exp(rnorm(20, 0, 0.02))
      rows[[length(rows) + 1]] <- data.frame(size = n, rep = 1, beta = b,
        source = "P", run = 1:20, seed = 1, absm = 0, chi = cval, q = 0)
    }
  }
  d <- do.call(rbind, rows)
  cat(sprintf("true: gamma/nu=%.2f  1/nu=%.2f  beta_inf=%.2f\n\n",
              gnu_true, snu_true, b0))
} else {
  d <- read.csv(csv_path, stringsAsFactors = FALSE)
}

sizes <- sort(unique(d$size))
cat("=== probe27 FSS analysis (R) ===\n")
cat("rows:", nrow(d), "| sizes:", sizes, "| sources:", unique(d$source), "\n\n")

agg_src <- function(dd) {
  a <- aggregate(chi ~ size + beta, data = dd,
    FUN = function(x) c(med = median(x), mean = mean(x),
                        q25 = unname(quantile(x, .25)),
                        q75 = unname(quantile(x, .75)),
                        n = length(x)))
  M <- data.frame(size = a$size, beta = a$beta, med = a$chi[, "med"],
                  mean = a$chi[, "mean"], q25 = a$chi[, "q25"],
                  q75 = a$chi[, "q75"], n = a$chi[, "n"])
  M[order(M$size, M$beta), ]
}

peak_of <- function(sub) {
  i <- which.max(sub$med)
  x <- sub$beta; y <- sub$med
  if (i > 1 && i < length(x)) {
    xs <- x[(i - 1):(i + 1)]; ys <- y[(i - 1):(i + 1)]
    fitq <- lm(ys ~ xs + I(xs^2))     # 三点二次插值（lm 版，数值稳健）
    cf <- coef(fitq)
    if (is.finite(cf[3]) && cf[3] < 0) {
      xv <- -cf[2] / (2 * cf[3])
      if (xv >= xs[1] && xv <= xs[3]) {
        yv <- cf[1] + cf[2] * xv + cf[3] * xv^2
        return(c(beta_c = unname(xv), chi_max = unname(yv),
                 chi_max_obs = unname(y[i])))
      }
    }
  }
  c(beta_c = unname(x[i]), chi_max = unname(y[i]), chi_max_obs = unname(y[i]))
}

analyze <- function(dd, label) {
  M <- agg_src(dd)
  pk <- do.call(rbind, lapply(sizes, function(n) peak_of(M[M$size == n, ])))
  P <- data.frame(size = sizes, beta_c = pk[, "beta_c"], chi_max = pk[, "chi_max"])
  cat(sprintf("--- %s ---\n", label))
  print(P, row.names = FALSE)
  fit1 <- lm(log(chi_max) ~ log(size), data = P)
  a <- coef(fit1)[2]; a_se <- summary(fit1)$coefficients[2, 2]
  cat(sprintf("chi_max ~ n^a : a = %.3f +- %.3f  (R2=%.4f)\n",
              a, a_se, summary(fit1)$r.squared))
  snus <- seq(0.4, 2.4, by = 0.005)
  r2s <- sapply(snus, function(s) {
    xx <- P$size^(-s)
    summary(lm(P$beta_c ~ xx))$r.squared
  })
  s_best <- snus[which.max(r2s)]
  xx <- P$size^(-s_best)
  fit2 <- lm(P$beta_c ~ xx)
  cat(sprintf("beta_c drift: 1/nu = %.3f (R2=%.4f) | beta_inf = %.4f\n\n",
              s_best, max(r2s), coef(fit2)[1]))
  list(P = P, M = M, fit1 = fit1, fit2 = fit2, gnu = a, snu = s_best,
       beta_inf = coef(fit2)[1])
}

r_all <- analyze(d, "all sources")
r_P <- analyze(d[d$source == "P", ], "P (pseudo)")
r_H <- if ("H" %in% d$source) analyze(d[d$source == "H", ], "H (hardware)") else NULL
if (!is.null(r_H)) {
  cat("=== P vs H parameter contrast ===\n")
  cat(sprintf("gamma/nu:  P=%.3f  H=%.3f  |diff|=%.3f\n",
              r_P$gnu, r_H$gnu, abs(r_P$gnu - r_H$gnu)))
  cat(sprintf("1/nu:      P=%.3f  H=%.3f  |diff|=%.3f\n",
              r_P$snu, r_H$snu, abs(r_P$snu - r_H$snu)))
  cat(sprintf("beta_inf:  P=%.3f  H=%.3f  |diff|=%.3f\n\n",
              r_P$beta_inf, r_H$beta_inf, abs(r_P$beta_inf - r_H$beta_inf)))
} else {
  cat("(no H-source data; P vs H contrast skipped)\n\n")
}

if (!selftest) {
  param_rows <- data.frame(
    source = c("all", "P", if (!is.null(r_H)) "H"),
    gnu = c(r_all$gnu, r_P$gnu, if (!is.null(r_H)) r_H$gnu),
    snu = c(r_all$snu, r_P$snu, if (!is.null(r_H)) r_H$snu),
    beta_inf = c(r_all$beta_inf, r_P$beta_inf, if (!is.null(r_H)) r_H$beta_inf))
  write.csv(param_rows, "r27_fss_params.csv", row.names = FALSE)
  cat("params -> r27_fss_params.csv\n\n")
}

if (!selftest) {
  png("probe27_fss_peaks.png", width = 1000, height = 560)
  cols <- rainbow(length(sizes))
  M <- r_all$M
  ymax <- max(M$q75)
  plot(NA, xlim = range(M$beta), ylim = c(0, ymax), xlab = "beta",
       ylab = "chi (median)", main = "probe27: susceptibility profiles (config-model ensemble)")
  for (j in seq_along(sizes)) {
    sub <- M[M$size == sizes[j], ]
    lines(sub$beta, sub$med, col = cols[j], lwd = 2)
    points(sub$beta, sub$med, col = cols[j], pch = 20, cex = 0.6)
  }
  legend("topright", legend = paste("n =", sizes), col = cols, lwd = 2, cex = 0.9)
  dev.off()

  png("probe27_fss_scaling.png", width = 1000, height = 480)
  par(mfrow = c(1, 2))
  P <- r_all$P
  plot(log(P$size), log(P$chi_max), pch = 19, xlab = "log n", ylab = "log chi_max",
       main = sprintf("chi_max scaling (a=%.2f)", r_all$gnu))
  abline(r_all$fit1, col = "red")
  xx <- P$size^(-r_all$snu)
  plot(xx, P$beta_c, pch = 19, xlab = sprintf("n^(-%.2f)", r_all$snu),
       ylab = "beta_c", main = sprintf("beta_c drift (1/nu=%.2f)", r_all$snu))
  abline(r_all$fit2, col = "red")
  dev.off()
  cat("figures: probe27_fss_peaks.png | probe27_fss_scaling.png\n")
}
cat("(2026-10-14, R-side analysis for probe27)\n")
