import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

import { scanHandWrittenPaths } from '../lib/path-scan.mjs'

const created = []

function makeTree(files) {
  const root = mkdtempSync(path.join(tmpdir(), 'contract-path-scan-'))
  created.push(root)
  for (const [relative, content] of Object.entries(files)) {
    const full = path.join(root, relative)
    mkdirSync(path.dirname(full), { recursive: true })
    writeFileSync(full, content, 'utf8')
  }
  return root
}

afterEach(() => {
  while (created.length > 0) rmSync(created.pop(), { recursive: true, force: true })
})

describe('path-scan 口径 v1', () => {
  it('统计单/双引号字符串字面量', () => {
    const root = makeTree({
      'a.ts': `fetch('/api/webui/a')\nfetch("/api/webui/b")\nfetch('https://example.com/api/x')\n`,
    })
    const result = scanHandWrittenPaths({ rootDir: root })
    expect(result.occurrences).toBe(2)
    expect(result.uniqueCount).toBe(2)
    expect(result.measureVersion).toBe('v1')
  })

  it('展开同文件 const 前缀（R3）并规范化 unique 键（R6）', () => {
    const root = makeTree({
      'a.ts': [
        `const API_BASE = '/api/webui/config'`,
        'fetch(`${API_BASE}/list`)',
        'fetch(`${API_BASE}/list/${id}?x=1`)',
        'fetch(`${API_BASE}/list/${other}?y=2`)',
      ].join('\n'),
    })
    const result = scanHandWrittenPaths({ rootDir: root })
    expect(result.occurrences).toBe(4)
    expect(result.uniqueCount).toBe(3)
    expect(result.unique).toContain('/api/webui/config')
    expect(result.unique).toContain('/api/webui/config/list')
    expect(result.unique).toContain('/api/webui/config/list/{param}')
  })

  it('模板字面量直接以 /api/ 起始（R4）', () => {
    const root = makeTree({
      'a.ts': 'fetch(`/api/webui/items/${id}`)\n',
    })
    const result = scanHandWrittenPaths({ rootDir: root })
    expect(result.occurrences).toBe(1)
    expect(result.unique[0]).toBe('/api/webui/items/{param}')
  })

  it('不统计注释与测试目录（R7/R1）', () => {
    const root = makeTree({
      'a.ts': '// fetch("/api/webui/comment")\n/* "/api/webui/block" */\nfetch("/api/webui/real")\n',
      '__tests__/b.ts': 'fetch("/api/webui/test")\n',
    })
    const result = scanHandWrittenPaths({ rootDir: root })
    expect(result.occurrences).toBe(1)
    expect(result.perFile['__tests__/b.ts']).toBeUndefined()
  })

  it('常量命名不匹配模式时不展开', () => {
    const root = makeTree({
      'a.ts': [
        `const OTHER = '/api/webui/a'`,
        'fetch(`${OTHER}/x`)',
        'fetch(`${UNKNOWN_BASE}/y`)',
      ].join('\n'),
    })
    const result = scanHandWrittenPaths({ rootDir: root })
    expect(result.occurrences).toBe(1)
  })

  it('同一代码状态重复扫描结果一致', () => {
    const root = makeTree({ 'a.ts': 'fetch("/api/webui/a")\nfetch("/api/webui/b")\n' })
    expect(scanHandWrittenPaths({ rootDir: root })).toEqual(scanHandWrittenPaths({ rootDir: root }))
  })
})