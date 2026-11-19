/**
 * 契约取源与结构校验
 *
 * 支持三种来源模式：http（运行中后端）、snapshot（归档快照）、auto（http 失败回落快照）。
 * 本模块只负责「取到文本 + 校验 + 归一化 + 摘要」，写盘职责留在 CLI。
 */

/* global fetch, AbortSignal */

import { readFile } from 'node:fs/promises'
import { Buffer } from 'node:buffer'
import { createHash } from 'node:crypto'

export const DEFAULT_OPENAPI_URL = 'http://127.0.0.1:18001/openapi.json'
export const DEFAULT_TIMEOUT_MS = 5000
export const SOURCE_MODES = Object.freeze(['http', 'snapshot', 'auto'])

export function normalizeLineEndings(text) {
  return text.replace(/\r\n?/g, '\n')
}

export function computeSha256(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex')
}

export function validateSchema(schema) {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) {
    return { ok: false, kind: 'invalid-json', message: '根节点不是 JSON 对象' }
  }
  if (typeof schema.openapi !== 'string') {
    return { ok: false, kind: 'missing-openapi', message: '缺少 openapi 版本字段' }
  }
  if (!/^3\./.test(schema.openapi)) {
    return { ok: false, kind: 'unsupported-openapi', message: `不支持的 OpenAPI 版本：${schema.openapi}` }
  }
  if (!schema.paths || typeof schema.paths !== 'object' || Array.isArray(schema.paths)) {
    return { ok: false, kind: 'missing-paths', message: '缺少 paths 对象' }
  }
  return { ok: true }
}

function snippetOf(text) {
  return text.slice(0, 200)
}

function parseAndValidate(text) {
  let schema
  try {
    schema = JSON.parse(text)
  } catch (error) {
    return {
      ok: false,
      kind: 'invalid-json',
      message: `JSON 解析失败：${error instanceof Error ? error.message : String(error)}`,
      rawSnippet: snippetOf(text),
    }
  }
  const validation = validateSchema(schema)
  if (!validation.ok) return { ...validation, rawSnippet: snippetOf(text) }
  return { ok: true, schema }
}

async function tryHttp(url, timeoutMs) {
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(timeoutMs),
      headers: { accept: 'application/json' },
    })
    if (!response.ok) {
      return {
        ok: false,
        kind: 'http-status',
        message: `契约端点返回 HTTP ${response.status}`,
        attempted: url,
      }
    }
    const text = await response.text()
    return { ok: true, sourceKind: 'http', sourceId: `http:${url}`, text, fetchedAt: new Date().toISOString() }
  } catch (error) {
    return {
      ok: false,
      kind: 'unreachable',
      message: `契约来源不可达：${error instanceof Error ? error.message : String(error)}`,
      attempted: url,
    }
  }
}

async function readSnapshot(snapshotPath) {
  try {
    const text = await readFile(snapshotPath, 'utf8')
    return { ok: true, sourceKind: 'snapshot', sourceId: `snapshot:${snapshotPath}`, text }
  } catch (error) {
    return {
      ok: false,
      kind: 'snapshot-missing',
      message: `快照不可读：${error instanceof Error ? error.message : String(error)}`,
      attempted: snapshotPath,
    }
  }
}

/**
 * 解析契约来源。
 * @param {{mode?: string, url?: string, snapshotPath: string, timeoutMs?: number, snapshotMetaPath?: string}} options
 */
export async function resolveSource(options) {
  const mode = options.mode ?? 'auto'
  const url = options.url ?? DEFAULT_OPENAPI_URL
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS

  if (!SOURCE_MODES.includes(mode)) {
    return { ok: false, kind: 'invalid-mode', message: `非法的 --source：${mode}（可选 http / snapshot / auto）` }
  }

  const attempts = []
  let loaded = null

  if (mode === 'http' || mode === 'auto') {
    const result = await tryHttp(url, timeoutMs)
    if (result.ok) loaded = result
    else attempts.push(result)
  }

  if (!loaded && (mode === 'snapshot' || mode === 'auto')) {
    const result = await readSnapshot(options.snapshotPath)
    if (result.ok) loaded = result
    else attempts.push(result)
  }

  if (!loaded) {
    return {
      ok: false,
      kind: 'no-source',
      message: '无可用来源：HTTP 与快照均不可用',
      attempts,
    }
  }

  const normalized = normalizeLineEndings(loaded.text)
  const parsed = parseAndValidate(normalized)
  if (!parsed.ok) return { ...parsed, attempts, sourceKind: loaded.sourceKind }

  const fetchedAt = loaded.fetchedAt ?? options.snapshotFetchedAt ?? 'unknown'

  return {
    ok: true,
    sourceKind: loaded.sourceKind,
    sourceId: loaded.sourceId,
    fetchedAt,
    text: normalized,
    byteLength: Buffer.byteLength(normalized, 'utf8'),
    normalizedSha256: computeSha256(normalized),
    schema: parsed.schema,
  }
}