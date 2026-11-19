import { describe, expect, it } from 'vitest'

import {
  buildGaps,
  diffOperationSets,
  extractOperations,
  groupByPrefix,
  hasRequestBodySchema,
  hasResponseSchema,
  operationKey,
  prefixGroupOf,
  stableSerialize,
  summarizeCoverage,
} from '../lib/contract-model.mjs'

function operation(responses, requestBody) {
  return { responses, ...(requestBody ? { requestBody } : {}) }
}

const jsonSchema = { type: 'object', properties: { ok: { type: 'boolean' } } }

describe('contract-model', () => {
  it('只提取 HTTP 方法，并按 path/method 稳定排序', () => {
    const schema = {
      paths: {
        '/b': { post: {}, get: {}, parameters: [] },
        '/a': { get: {} },
      },
    }
    const operations = extractOperations(schema)
    expect(operations.map(operationKey)).toEqual(['GET /a', 'GET /b', 'POST /b'])
  })

  it('响应模型只认 2xx + application/json + 非空 schema', () => {
    expect(hasResponseSchema(operation({ 200: { content: { 'application/json': { schema: jsonSchema } } } }))).toBe(true)
    expect(hasResponseSchema(operation({ 200: { content: { 'application/json': { schema: {} } } } }))).toBe(false)
    expect(hasResponseSchema(operation({ 400: { content: { 'application/json': { schema: jsonSchema } } } }))).toBe(false)
    expect(hasResponseSchema(operation({ 204: { description: 'no content' } }))).toBe(false)
  })

  it('请求体模型只认 application/json + 非空 schema', () => {
    expect(hasRequestBodySchema(operation({}, { content: { 'application/json': { schema: jsonSchema } } }))).toBe(true)
    expect(hasRequestBodySchema(operation({}, { content: { 'text/plain': { schema: jsonSchema } } }))).toBe(false)
  })

  it('覆盖四元组满足恒等式，且请求体维度不相加', () => {
    const operations = [
      { method: 'get', path: '/a', operation: operation({ 200: { content: { 'application/json': { schema: jsonSchema } } } }) },
      { method: 'post', path: '/b', operation: operation({}, { content: { 'application/json': { schema: jsonSchema } } }) },
      { method: 'get', path: '/c', operation: operation({ 500: { description: 'error' } }) },
    ]
    const coverage = summarizeCoverage(operations)
    expect(coverage.total).toBe(3)
    expect(coverage.withResponseSchema).toBe(1)
    expect(coverage.withoutResponseSchema).toBe(2)
    expect(coverage.withRequestSchema).toBe(1)
    expect(coverage.total).toBe(coverage.withResponseSchema + coverage.withoutResponseSchema)
  })

  it('前缀分组取前两段，/api 单独成组', () => {
    expect(prefixGroupOf('/api/webui/config')).toBe('/api/webui')
    expect(prefixGroupOf('/api')).toBe('/api')
    expect(prefixGroupOf('/health')).toBe('/health')
    const groups = groupByPrefix([
      { method: 'get', path: '/api/webui/a', operation: operation({}) },
      { method: 'get', path: '/api/webui/b', operation: operation({}) },
      { method: 'get', path: '/api/chat/c', operation: operation({}) },
    ])
    expect(groups.map((group) => [group.prefixGroup, group.total])).toEqual([
      ['/api/chat', 1],
      ['/api/webui', 2],
    ])
  })

  it('缺口只收缺响应模型的操作，排序稳定', () => {
    const operations = [
      { method: 'get', path: '/api/webui/z', operation: operation({}) },
      { method: 'post', path: '/api/chat/a', operation: operation({}) },
      { method: 'get', path: '/api/chat/a', operation: operation({}) },
      { method: 'get', path: '/api/chat/b', operation: operation({ 200: { content: { 'application/json': { schema: jsonSchema } } } }) },
    ]
    const gaps = buildGaps(operations)
    expect(gaps).toEqual([
      { method: 'GET', path: '/api/chat/a', prefixGroup: '/api/chat', missing: 'both' },
      { method: 'POST', path: '/api/chat/a', prefixGroup: '/api/chat', missing: 'both' },
      { method: 'GET', path: '/api/webui/z', prefixGroup: '/api/webui', missing: 'both' },
    ])
  })

  it('稳定序列化对键顺序不敏感', () => {
    expect(stableSerialize({ b: 1, a: { d: 2, c: 3 } })).toBe(stableSerialize({ a: { c: 3, d: 2 }, b: 1 }))
  })

  it('集合差异区分新增/删除/变更', () => {
    const previous = [
      { method: 'get', path: '/a', operation: { summary: 'old' } },
      { method: 'get', path: '/b', operation: {} },
    ]
    const current = [
      { method: 'get', path: '/a', operation: { summary: 'new' } },
      { method: 'get', path: '/c', operation: {} },
    ]
    expect(diffOperationSets(previous, current)).toEqual({ added: 1, removed: 1, changed: 1 })
  })
})