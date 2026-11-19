import { describe, expect, it } from 'vitest'

import {
  computeSha256,
  normalizeLineEndings,
  validateSchema,
} from '../lib/source.mjs'

describe('source', () => {
  it('行尾归一化为 LF', () => {
    expect(normalizeLineEndings('a\r\nb\rc\n')).toBe('a\nb\nc\n')
  })

  it('同一内容不同行尾得到相同摘要', () => {
    expect(computeSha256(normalizeLineEndings('a\r\nb'))).toBe(computeSha256(normalizeLineEndings('a\nb')))
  })

  it('合法 OpenAPI 3.x 通过校验', () => {
    expect(validateSchema({ openapi: '3.1.0', paths: {} })).toEqual({ ok: true })
  })

  it('缺 openapi 字段报独立错误', () => {
    const result = validateSchema({ paths: {} })
    expect(result.ok).toBe(false)
    expect(result.kind).toBe('missing-openapi')
  })

  it('非 3.x 主版本报独立错误', () => {
    const result = validateSchema({ openapi: '2.0.0', paths: {} })
    expect(result.ok).toBe(false)
    expect(result.kind).toBe('unsupported-openapi')
  })

  it('缺 paths 报独立错误', () => {
    const result = validateSchema({ openapi: '3.1.0' })
    expect(result.ok).toBe(false)
    expect(result.kind).toBe('missing-paths')
  })
})