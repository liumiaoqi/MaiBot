# 批量拉取克隆池顶层（2026-08-24 直拉版——无检查）
param([string]$Root = "E:\Users\lmq\importantClone")
Get-ChildItem $Root -Directory -ErrorAction SilentlyContinue | ForEach-Object {
  Write-Host ("- {0}" -f $_.Name) -ForegroundColor Yellow
  $out = git -C $_.FullName pull --ff-only 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Host "  [跳过/失败] $($out | Select-Object -First 1)" -ForegroundColor DarkGray }
  else { Write-Host "  [OK] $(if ($out) { ($out | Select-Object -Last 1) } else { "已最新" })" -ForegroundColor Green }
}