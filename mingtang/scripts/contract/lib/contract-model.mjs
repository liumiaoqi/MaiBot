/**
 * 契约计数模型（纯函数）
 *
 * 输入：OpenAPI 3.x schema 对象
 * 输出：操作枚举 / 覆盖四元组 / 前缀分组 / 缺口清单 / 集合差异
 *
 * 约束：本模块不做任何文件 I/O、不访问网络、不读取当前时间。
 */

export const HTTP_METHODS = Object.freeze([
  'get',
  'post',
  'put',
  'patch',
  'delete',
  'head',
  'options',
])

const HTTP_METHOD_SET = new Set(HTTP_METHODS)

function compareText(a, b) {
  if (a < b) return -1
  if (a > b) return 1
  return 0
}

/**
 * 从 schema.paths 提取「方法 + 路径」全集，并按 path、method 稳定排序。
 */
export function extractOperations(schema) {
  const operations = []
  const paths = schema?.paths ?? {}
  for (const path of Object.keys(paths)) {
    const item = paths[path]
    if (!item || typeof item !== 'object') continue
    for (const method of Object.keys(item)) {
      if (!HTTP_METHOD_SET.has(method)) continue
      const operation = item[method]
      operations.push({
        method,
        path,
        operation: operation && typeof operation === 'object' ? operation : {},
      })
    }
  }
  return operations.sort((a, b) => compareText(a.path, b.path) || compareText(a.method, b.method))
}

export function operationKey(operation) {
  return `${operation.method.toUpperCase()} ${operation.path}`
}

function hasJsonSchema(media) {
  const schema = media?.content?.['application/json']?.schema
  return Boolean(schema && typeof schema === 'object' && Object.keys(schema).length > 0)
}

/**
 * 「有响应模型」判据：存在 2xx 响应且其 application/json schema 非空。
 * 不做启发式猜测——没有显式 schema 就是没有。
 */
export function hasResponseSchema(operation) {
  const responses = operation?.responses
  if (!responses || typeof responses !== 'object') return false
  for (const status of Object.keys(responses)) {
    if (!/^2\d\d$/.test(status)) continue
    if (hasJsonSchema(responses[status])) return true
  }
  return false
}

/**
 * 「有请求体模型」判据：requestBody 的 application/json schema 非空。
 */
export function hasRequestBodySchema(operation) {
  return hasJsonSchema(operation?.requestBody)
}

/**
 * 覆盖四元组。恒等式：total = withResponseSchema + withoutResponseSchema。
 * withRequestSchema 是独立维度，不与前者相加。
 */
export function summarizeCoverage(operations) {
  let withResponseSchema = 0
  let withRequestSchema = 0
  for (const operation of operations) {
    if (hasResponseSchema(operation.operation)) withResponseSchema += 1
    if (hasRequestBodySchema(operation.operation)) withRequestSchema += 1
  }
  return {
    total: operations.length,
    withResponseSchema,
    withoutResponseSchema: operations.length - withResponseSchema,
    withRequestSchema,
  }
}

/**
 * 取路径前两段作为前缀分组；/api 自身单独成组。
 */
export function prefixGroupOf(path) {
  const segments = path.split('/').filter(Boolean)
  if (segments.length === 0) return '/'
  if (segments[0] !== 'api') return `/${segments[0]}`
  return segments.length >= 2 ? `/${segments[0]}/${segments[1]}` : '/api'
}

export function groupByPrefix(operations) {
  const groups = new Map()
  for (const operation of operations) {
    const prefixGroup = prefixGroupOf(operation.path)
    const row = groups.get(prefixGroup) ?? { prefixGroup, total: 0, withResponseSchema: 0 }
    row.total += 1
    if (hasResponseSchema(operation.operation)) row.withResponseSchema += 1
    groups.set(prefixGroup, row)
  }
  return [...groups.values()].sort((a, b) => compareText(a.prefixGroup, b.prefixGroup))
}

/**
 * 缺口清单：只收录「缺响应模型」的操作（条目数 = 总数 − 有响应模型数）。
 * missing 为 response 或 both（both = 同时缺请求体）。
 */
export function buildGaps(operations) {
  const gaps = []
  for (const operation of operations) {
    if (hasResponseSchema(operation.operation)) continue
    const missingRequest = !hasRequestBodySchema(operation.operation)
    gaps.push({
      method: operation.method.toUpperCase(),
      path: operation.path,
      prefixGroup: prefixGroupOf(operation.path),
      missing: missingRequest ? 'both' : 'response',
    })
  }
  return gaps.sort(
    (a, b) =>
      compareText(a.prefixGroup, b.prefixGroup) ||
      compareText(a.path, b.path) ||
      compareText(a.method, b.method),
  )
}

/**
 * 对象键递归排序后的稳定序列化（用于「变更」判定）。
 */
export function stableSerialize(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableSerialize(item)).join(',')}]`
  }
  if (value && typeof value === 'object') {
    const keys = Object.keys(value).sort(compareText)
    const entries = keys.map((key) => `${JSON.stringify(key)}:${stableSerialize(value[key])}`)
    return `{${entries.join(',')}}`
  }
  return JSON.stringify(value)
}

/**
 * 集合差异三类计数：新增 / 删除 / 变更。
 */
export function diffOperationSets(previous, current) {
  const previousMap = new Map(previous.map((operation) => [operationKey(operation), operation]))
  const currentMap = new Map(current.map((operation) => [operationKey(operation), operation]))
  let added = 0
  let removed = 0
  let changed = 0
  for (const key of currentMap.keys()) {
    if (!previousMap.has(key)) added += 1
  }
  for (const key of previousMap.keys()) {
    if (!currentMap.has(key)) removed += 1
  }
  for (const [key, currentOperation] of currentMap) {
    const previousOperation = previousMap.get(key)
    if (!previousOperation) continue
    if (stableSerialize(previousOperation.operation) !== stableSerialize(currentOperation.operation)) {
      changed += 1
    }
  }
  return { added, removed, changed }
}