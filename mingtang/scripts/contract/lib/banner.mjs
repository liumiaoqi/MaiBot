/**
 * 确定性头注模块
 *
 * 头注只承载确定性字段：生成器与版本、快照来源、快照取得时间、
 * normalized-sha256、规模计数、artifact-sha256。
 * 当前时刻（wall-clock）不得进入头注——只允许出现在 meta.json 与报告。
 */

import { createHash } from 'node:crypto'

export const BANNER_START = '/* @contract:start'
export const BANNER_END = '@contract:end */'

const REQUIRED_FIELDS = Object.freeze([
  'generator',
  'generatorVersion',
  'source',
  'fetchedAt',
  'normalizedSha256',
  'pathCount',
  'operationCount',
  'schemaCount',
  'artifactSha256',
])

export function computeArtifactSha256(body) {
  return createHash('sha256').update(body, 'utf8').digest('hex')
}

function sortKeys(fields) {
  const out = {}
  for (const key of Object.keys(fields).sort()) out[key] = fields[key]
  return out
}

export function renderBanner(fields) {
  const payload = JSON.stringify(sortKeys(fields), null, 2)
  return `${BANNER_START}\n${payload}\n${BANNER_END}\n`
}

export function applyBanner(body, fields) {
  return `${renderBanner(fields)}${body}`
}

/**
 * 解析头注。缺字段时如实返回缺失项，不填充默认值。
 */
export function parseBanner(text) {
  const startIndex = text.indexOf(BANNER_START)
  if (startIndex === -1) {
    return { found: false, fields: null, body: text, missing: [...REQUIRED_FIELDS] }
  }
  const payloadStart = startIndex + BANNER_START.length
  const endIndex = text.indexOf(BANNER_END, payloadStart)
  if (endIndex === -1) {
    return { found: false, fields: null, body: text, missing: [...REQUIRED_FIELDS] }
  }
  const payload = text.slice(payloadStart, endIndex).trim()
  let fields
  try {
    fields = JSON.parse(payload)
  } catch {
    return { found: false, fields: null, body: text, missing: [...REQUIRED_FIELDS] }
  }
  const missing = REQUIRED_FIELDS.filter((key) => !(key in fields))
  const body = text.slice(endIndex + BANNER_END.length).replace(/^\r?\n/, '')
  return { found: true, fields, body, missing }
}

/**
 * 手改判定：正文摘要与头注声明不一致即视为手改。
 * 注意：这里只比较正文，不比较头注——避免摘要自指。
 */
export function isHandEdited(text) {
  const parsed = parseBanner(text)
  if (!parsed.found || parsed.missing.length > 0) return true
  return computeArtifactSha256(parsed.body) !== parsed.fields.artifactSha256
}