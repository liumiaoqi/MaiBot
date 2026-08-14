/**
 * compareVersions —— 插件域统一的 semver 数值比较纯函数（R4 债清理 P2）。
 *
 * 收编 4 处重复实现（use-plugin-list / use-marketplace-data×2 / detail）：
 * 只按「点分数字段」逐段数值比较（major.minor.patch...），忽略预发布/构建元数据；
 * 缺失段按 0 补齐（'1.0' === '1.0.0'）；兼容常见 'v' 前缀（'v1.2.3' === '1.2.3'）。
 *
 * 返回：left > right → 1；left < right → -1；相等 → 0。
 */
export function compareVersions(left: string, right: string): number {
  const normalize = (version: string) => version.trim().replace(/^[vV]/, '')
  const leftParts = normalize(left).split('.').map(part => Number.parseInt(part, 10) || 0)
  const rightParts = normalize(right).split('.').map(part => Number.parseInt(part, 10) || 0)
  const maxLength = Math.max(leftParts.length, rightParts.length)

  for (let index = 0; index < maxLength; index++) {
    const leftPart = leftParts[index] || 0
    const rightPart = rightParts[index] || 0
    if (leftPart > rightPart) return 1
    if (leftPart < rightPart) return -1
  }

  return 0
}
