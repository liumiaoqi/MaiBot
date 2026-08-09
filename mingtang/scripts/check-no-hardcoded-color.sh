#!/bin/bash
# TE-3-2：检测硬编码颜色——禁止 hex / rgb / hsl / 命名色，强制使用 CSS 变量 token
# 白名单：src/lib/theme/**（token 定义源头）/ src/**/*.test.*（测试断言）
# 退出码：0=通过 / 1=有违规

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# 正则匹配硬编码颜色
# hex: #FFF / #FFFFFF
# rgb: rgb(...)
# hsl: hsl(...)
# 命名色: red blue green yellow orange purple pink brown gray grey black white
PATTERN='(#[0-9a-fA-F]{3}\b|#[0-9a-fA-F]{6}\b|rgb\(|hsl\(|\b(red|blue|green|yellow|orange|purple|pink|brown|gray|grey|black|white)\b)'

# 扫描 src/ 下 .ts/.tsx 文件，排除白名单
# 白名单：lib/theme/（token 定义）/ 测试文件
RESULT=$(rg -n "$PATTERN" \
  --glob 'src/**/*.ts' \
  --glob 'src/**/*.tsx' \
  --glob '!src/lib/theme/**' \
  --glob '!src/**/*.test.*' \
  --glob '!src/**/*.spec.*' \
  "$PROJECT_DIR" 2>/dev/null || true)

if [ -z "$RESULT" ]; then
  echo "✅ 未检测到硬编码颜色"
  exit 0
else
  echo "❌ 检测到硬编码颜色（应使用 CSS 变量 token）："
  echo "$RESULT"
  exit 1
fi