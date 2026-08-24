# 批量拉取开源克隆仓库更新（2026-08-24 立）
#
# 用法：
#   .pull_all_clones.ps1                    # 拉取 importantClone 下全部（默认）
#   .pull_all_clones.ps1 -Root D:somedir  # 指定目录
#   .pull_all_clones.ps1 -Only linuxclone,letta  # 只拉指定仓库
#   .pull_all_clones.ps1 -NoPull            # 只检查不拉（dry-run 报告）
#   .pull_all_clones.ps1 -Strict            # 脏工作区阻断（默认提示继续）
#
# 说明：
#   - 用 git rev-parse 判断是否 git 仓库（权威——.git 可能是文件/目录/指针，不依赖结构）
#   - 无 remote：跳过（本地备份性质）
#   - fetch --all + pull --ff-only（快速前进安全——有本地提交会失败并报告）

param(
  [string]$Root = "E:\Users\lmq\importantClone",
  [string[]]$Only = @(),
  [switch]$NoPull,
  [switch]$Strict
)

$ErrorActionPreference = "Continue"

$repos = Get-ChildItem $Root -Directory -ErrorAction SilentlyContinue
if ($Only.Count -gt 0) { $repos = $repos | Where-Object { $_.Name -in $Only } }

$results = @(); $skipped = @(); $failed = @()
Write-Host "=== 批量拉取克隆池（根：$Root）===" -ForegroundColor Cyan
Write-Host ""

foreach ($repo in $repos) {
  $name = $repo.Name; $path = $repo.FullName
  Write-Host ("--- {0} ---" -f $name) -ForegroundColor Yellow

  # ① 是否 git 仓库（git rev-parse 权威判断——不依赖 .git 结构）
  $isGit = git -C $path rev-parse --is-inside-work-tree 2>$null
  if ($LASTEXITCODE -ne 0 -or $isGit -ne "true") {
    Write-Host "  [跳过] 非 git 仓库" -ForegroundColor DarkGray
    $skipped += $name; continue
  }

  # ② remote 检查
  $remote = (git -C $path remote 2>$null | Select-Object -First 1);
  if (-not $remote) {
    Write-Host "  [跳过] 无 remote（本地备份）" -ForegroundColor DarkGray
    $skipped += $name; continue
  }

  # ③ 本地脏工作区
  $dirty = (git -C $path status --porcelain 2>$null | Measure-Object).Count;
  if ($dirty -gt 0) {
    if ($Strict) {
      Write-Host "  [阻断] 脏工作区 $dirty 项（-Strict）——跳过" -ForegroundColor Red
      $failed += $name; continue;
    }
    Write-Host "  [提示] 脏工作区 $dirty 项——继续（-Strict 可阻断）" -ForegroundColor DarkYellow
  }

  # ④ dry-run 或实际拉取
  if ($NoPull) {
    $fetchOut = git -C $path fetch --dry-run 2>&1 | Select-Object -First 3;
    if ($fetchOut) {
      Write-Host "  [待更新] $($fetchOut[0])" -ForegroundColor Green;
      $results += "$name|pending|$($fetchOut[0])"
    } else {
      Write-Host "  [最新] 无更新" -ForegroundColor Green;
      $results += "$name|up-to-date|-"
    }
    continue;
  }

  # ⑤ 拉取
  $fetchOut = git -C $path fetch --all --prune 2>&1 | Select-Object -First 3;
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  [失败] fetch：$($fetchOut -join "; ")" -ForegroundColor Red
    $failed += $name; continue;
  }
  $pullOut = git -C $path pull --ff-only 2>&1 | Select-Object -First 4;
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  [失败] pull（ff-only）：$($pullOut -join "; ")" -ForegroundColor Red
    $failed += $name; continue;
  }
  Write-Host "  [OK] $($pullOut -join "; ")" -ForegroundColor Green;
  $results += "$name|updated|-"
}

Write-Host ""; Write-Host "=== 汇总 ===" -ForegroundColor Cyan
Write-Host ("共 {0} 仓库 | 拉取/检查 {1} | 跳过 {2} | 失败 {3}" -f $repos.Count, $results.Count, $skipped.Count, $failed.Count)
if ($results) { Write-Host "已处理：" -ForegroundColor Green; $results | ForEach-Object { Write-Host "  $_" -ForegroundColor Green } }
if ($skipped) { Write-Host "跳过：" -ForegroundColor DarkGray; $skipped | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray } }
if ($failed) { Write-Host "失败：" -ForegroundColor Red; $failed | ForEach-Object { Write-Host "  $_" -ForegroundColor Red } }