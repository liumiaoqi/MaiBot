/**
 * 报告渲染模块
 *
 * 输出两类产物：
 * - coverage-report.md：人读（覆盖度 / 分组 / 缺口 / 路径基线 / 历史纠偏）
 * - gaps.json / path-baseline.json / meta.json：机读（稳定序列化，无时间戳）
 *
 * 明确禁止在报告里出现「路径字面量已下降 / 收益达成」类结论——
 * 本期只记录基线，下降目标不在本期验收范围。
 */

export const REPORT_VERSION = 'v1'
export const RULES = Object.freeze([
  'R1 范围：src/lib/**/*.{ts,tsx}（递归，排除任意 __tests__ 目录与 *.d.ts 声明/生成文件）',
  'R2 单元 1：单/双引号字符串字面量且值以 /api/ 起始',
  'R3 单元 2：模板字面量首段为 ${CONST}，CONST 匹配 ^[A-Z][A-Z0-9_]*(BASE|PREFIX|ROOT|URL)$，且同文件存在 const 定义 → 用展开值判定',
  'R4 单元 3：模板字面量整体文本以 /api/ 起始',
  'R5 计数：按出现次数计；unique 在全范围合并后去重',
  'R6 去重键：展开常量后，${...} → {param}，去掉 ? 后的查询串',
  'R7 不统计：非 /api/ 起始的外部地址、注释文本、测试文件',
  'R8 规则变更须升 measureVersion，报告双列新旧口径',
])

function formatNumber(value) {
  return Number.isFinite(value) ? String(value) : 'unknown'
}

function renderCoverageSection(coverage) {
  return [
    '## 覆盖度四元组',
    '',
    '| 指标 | 数值 |',
    '|---|---|',
    `| 操作总数 | ${formatNumber(coverage.total)} |`,
    `| 有响应模型 | ${formatNumber(coverage.withResponseSchema)} |`,
    `| 无响应模型 | ${formatNumber(coverage.withoutResponseSchema)} |`,
    `| 有请求体模型 | ${formatNumber(coverage.withRequestSchema)} |`,
    '',
    `恒等式校验：total = withResponseSchema + withoutResponseSchema → ${formatNumber(coverage.withResponseSchema)} + ${formatNumber(coverage.withoutResponseSchema)} = ${formatNumber(coverage.total)}`,
    '',
  ].join('\n')
}

function renderGroupSection(groups) {
  const rows = groups.map(
    (group) =>
      `| ${group.prefixGroup} | ${group.total} | ${group.withResponseSchema} | ${group.total - group.withResponseSchema} |`,
  )
  return [
    '## 前缀分组',
    '',
    '| 分组 | 操作数 | 有响应模型 | 无响应模型 |',
    '|---|---|---|---|',
    ...rows,
    '',
  ].join('\n')
}

function renderGapSection(gaps) {
  return [
    '## 响应模型缺口',
    '',
    `缺口条目数：${gaps.length}（仅统计缺响应模型的操作；missing=both 表示同时缺请求体模型）`,
    '',
    gaps.length === 0
      ? '本期末发现响应模型缺口。'
      : gaps
          .slice(0, 50)
          .map((gap) => `- \`${gap.method} ${gap.path}\`（${gap.prefixGroup}，missing=${gap.missing}）`)
          .join('\n'),
    gaps.length > 50 ? `\n… 其余 ${gaps.length - 50} 条见 gaps.json` : '',
    '',
  ].join('\n')
}

function renderShapeSection(title, description, operations) {
  return [
    `## ${title}`,
    '',
    description,
    '',
    operations.length === 0
      ? '本期末发现。'
      : operations.slice(0, 50).map((operation) => `- \`${operation}\``).join('\n'),
    '',
  ].join('\n')
}

function renderBaselineSection(baseline) {
  return [
    '## 手写路径基线（口径 v1，本期只记录基线）',
    '',
    `- 口径版本：\`${baseline.measureVersion}\``,
    `- 覆盖范围：${baseline.scope}`,
    `- 出现次数：**${formatNumber(baseline.occurrences)}**`,
    `- unique 数：**${formatNumber(baseline.uniqueCount)}**`,
    `- 复算命令：\`NODE_OPTIONS= pnpm run contract:report\``,
    '',
    '> 历史记录 107 / 93 为口径未固化时期的数字，**不可复算、不可与新值直接比较**，仅作留档。',
    '> 本期验收只要求基线记录完整（spec §9 第 5 条）；「路径字面量减少」不在本期验收范围。',
    '',
    '### 分文件出现次数',
    '',
    '| 文件 | 次数 |',
    '|---|---|',
    ...Object.entries(baseline.perFile)
      .sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0))
      .map(([file, count]) => `| ${file} | ${count} |`),
    '',
  ].join('\n')
}

function renderHistorySection() {
  return [
    '## 历史数字纠偏',
    '',
    '- 决策文档 `webui_contract_codegen_1019.md` 的「315 个端点」已失效：当前实测为 405 paths / 448 operations / 339 schemas。',
    '- 决策文档的「9 个域手抄 fetch」不成立：裸 fetch 仅 5 处 / 4 文件；真实痛点是路径字面量与手写类型规模。',
    '- 旧路径基线 107 / 93 因口径未固化不可复算，已由口径 v1 取代。',
    '',
  ].join('\n')
}

/**
 * 渲染人读报告。
 * @param {{meta: object, coverage: object, groups: object[], gaps: object[], baseline: object, noShapeOperations: string[], wideObjectOperations: string[]}} input
 */
export function renderCoverageReport(input) {
  const { meta, coverage, groups, gaps, baseline, noShapeOperations, wideObjectOperations } = input
  return [
    `# WebUI 契约层报告（${REPORT_VERSION}）`,
    '',
    '> 本文件由 `contract:report` 自动生成，请勿手改。',
    '',
    '## 契约来源与规模',
    '',
    `- 来源：\`${meta.sourceId}\``,
    `- 快照取得时间：${meta.fetchedAt}`,
    `- OpenAPI 版本：${meta.openapiVersion}`,
    `- paths：${meta.pathCount}`,
    `- operations：${meta.operationCount}`,
    `- schemas：${meta.schemaCount}`,
    `- normalized-sha256：\`${meta.normalizedSha256}\``,
    `- 口径规则：见下方「统计规则」，共 ${RULES.length} 条`,
    '',
    '## 统计规则',
    '',
    ...RULES.map((rule) => `- ${rule}`),
    '',
    '## CI 与后端漂移的分工',
    '',
    'CI 只能守「快照 vs 产物一致」——防的是「改了快照没重生成产物」；「后端真的变了」只在本地后端运行时可见。',
    '',
    '**「CI 绿 = 后端没漂移」是误读。**',
    '',
    renderCoverageSection(coverage),
    renderGroupSection(groups),
    renderGapSection(gaps),
    renderShapeSection(
      '无形状端点',
      '有 2xx 响应但 application/json schema 为空或缺失的端点（生成器无法据此产出类型）。',
      noShapeOperations,
    ),
    renderShapeSection(
      '宽对象端点',
      '响应 schema 为 object 且没有 properties 的端点（类型只能退化为 Record<string, unknown>）。',
      wideObjectOperations,
    ),
    renderBaselineSection(baseline),
    renderHistorySection(),
  ].join('\n')
}

export function stableStringify(value) {
  const sortValue = (input) => {
    if (Array.isArray(input)) return input.map(sortValue)
    if (input && typeof input === 'object') {
      const out = {}
      for (const key of Object.keys(input).sort()) out[key] = sortValue(input[key])
      return out
    }
    return input
  }
  return `${JSON.stringify(sortValue(value), null, 2)}\n`
}