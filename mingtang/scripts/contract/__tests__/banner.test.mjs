import { describe, expect, it } from 'vitest'

import {
  BANNER_END,
  BANNER_START,
  applyBanner,
  computeArtifactSha256,
  isHandEdited,
  parseBanner,
  renderBanner,
} from '../lib/banner.mjs'

const fields = {
  generator: 'openapi-typescript',
  generatorVersion: '7.13.0',
  source: 'snapshot:openapi/openapi.json',
  fetchedAt: '2026-11-19T00:00:00.000Z',
  normalizedSha256: 'a'.repeat(64),
  pathCount: 405,
  operationCount: 448,
  schemaCount: 339,
  artifactSha256: 'b'.repeat(64),
}

describe('banner', () => {
  it('round-trip 还原全部字段', () => {
    const text = applyBanner('export type A = string\n', fields)
    const parsed = parseBanner(text)
    expect(parsed.found).toBe(true)
    expect(parsed.missing).toEqual([])
    expect(parsed.fields).toEqual(fields)
    expect(parsed.body).toBe('export type A = string\n')
  })

  it('同一输入渲染两次字节一致', () => {
    expect(renderBanner(fields)).toBe(renderBanner(fields))
  })

  it('字段键顺序不影响渲染结果', () => {
    const reordered = Object.fromEntries(Object.entries(fields).reverse())
    expect(renderBanner(fields)).toBe(renderBanner(reordered))
  })

  it('正文改一行则 artifact-sha256 变化', () => {
    const first = computeArtifactSha256('export type A = string\n')
    const second = computeArtifactSha256('export type A = number\n')
    expect(first).not.toBe(second)
  })

  it('缺字段时如实报告缺失项，不填充默认值', () => {
    const text = `${BANNER_START}\n{"generator":"x"}\n${BANNER_END}\n`
    const parsed = parseBanner(text)
    expect(parsed.found).toBe(true)
    expect(parsed.missing).toContain('artifactSha256')
    expect(parsed.fields.generatorVersion).toBeUndefined()
  })

  it('正文与头注摘要不一致判定为手改', () => {
    const body = 'export type A = string\n'
    const text = applyBanner(body, { ...fields, artifactSha256: computeArtifactSha256(body) })
    expect(isHandEdited(text)).toBe(false)
    expect(isHandEdited(text.replace('string', 'number'))).toBe(true)
  })
})