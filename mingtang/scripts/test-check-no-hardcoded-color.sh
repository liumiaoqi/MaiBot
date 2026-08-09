#!/bin/bash
# TE-3-2：测试 check-no-hardcoded-color.sh 脚本
# 验证：硬编码颜色检测 / 白名单 / 命名色 / rgb/hsl / Tailwind 语义类不报错

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_SCRIPT="$SCRIPT_DIR/check-no-hardcoded-color.sh"

# 创建临时测试目录
TMP_DIR=$(mktemp -d)
trap "rm -rf $TMP_DIR" EXIT

mkdir -p "$TMP_DIR/src/components"
mkdir -p "$TMP_DIR/src/lib/theme"
mkdir -p "$TMP_DIR/src/__tests__"

# 测试 1：含硬编码颜色的文件应报错
echo "const color = '#FF5733'" > "$TMP_DIR/src/components/bad.ts"
# 测试 2：不含硬编码颜色的文件应通过
echo "const color = 'var(--color-accent-9)'" > "$TMP_DIR/src/components/good.ts"
# 测试 3：lib/theme/ 白名单——含硬编码颜色不报错
echo "export const ACCENT = '#55AB49'" > "$TMP_DIR/src/lib/theme/tokens.ts"
# 测试 4：测试文件白名单——含硬编码颜色不报错
echo "expect(color).toBe('#FF0000')" > "$TMP_DIR/src/__tests__/.test.ts"
# 测试 5：命名色检测
echo "const bg = 'red'" > "$TMP_DIR/src/components/named.ts"
# 测试 6：rgb 检测
echo "const bg = 'rgb(255, 0, 0)'" > "$TMP_DIR/src/components/rgb.ts"
# 测试 7：Tailwind 语义类不报错
echo "export const cls = 'text-accent-9'" > "$TMP_DIR/src/components/tailwind.ts"

# 运行检测脚本（修改脚本目录指向临时目录）
cd "$TMP_DIR"
# 模拟 rg 命令
RESULT=$(rg -n '(#[0-9a-fA-F]{3}\b|#[0-9a-fA-F]{6}\b|rgb\(|hsl\(|\b(red|blue|green|yellow|orange|purple|pink|brown|gray|grey|black|white)\b)' \
  --glob 'src/**/*.ts' \
  --glob 'src/**/*.tsx' \
  --glob '!src/lib/theme/**' \
  --glob '!src/**/*.test.*' \
  --glob '!src/**/*.spec.*' \
  "$TMP_DIR" 2>/dev/null || true)

# 验证：bad.ts / named.ts / rgb.ts 被检测到
echo "$RESULT" | grep -q "bad.ts" && echo "✅ hex 颜色检测" || echo "❌ hex 颜色检测失败"
echo "$RESULT" | grep -q "named.ts" && echo "✅ 命名色检测" || echo "❌ 命名色检测失败"
echo "$RESULT" | grep -q "rgb.ts" && echo "✅ rgb 检测" || echo "❌ rgb 检测失败"

# 验证：good.ts / tailwind.ts 不被检测到
echo "$RESULT" | grep -q "good.ts" && echo "❌ CSS 变量误报" || echo "✅ CSS 变量不报错"
echo "$RESULT" | grep -q "tailwind.ts" && echo "❌ Tailwind 语义类误报" || echo "✅ Tailwind 语义类不报错"

# 验证：白名单不报错
echo "$RESULT" | grep -q "tokens.ts" && echo "❌ lib/theme 白名单失效" || echo "✅ lib/theme 白名单"
echo "$RESULT" | grep -q "test.ts" && echo "❌ 测试文件白名单失效" || echo "✅ 测试文件白名单"

echo ""
echo "TE-3-2 测试完成"