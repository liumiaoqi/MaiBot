/**
 * 手写路径基线口径 v1 扫描器
 *
 * R1 范围：src/lib 递归扫描 .ts / .tsx；排除任意 __tests__ 目录与 .d.ts 声明文件
 *   含 .tsx 的依据：restart-context.tsx 等同样直接消费 /api/ 路径；排除会漏计真实手写路径
 *   （实测差 1 处，决定 211 与 210、26 与 25 文件）。
 * R2 单元 1：单/双引号字符串字面量且值以 /api/ 起始
 * R3 单元 2：模板字面量首段为 ${CONST}，CONST 匹配 ^[A-Z][A-Z0-9_]*(BASE|PREFIX|ROOT|URL)$，
 *            且同文件存在 const CONST = '<字面量>'，用展开值参与判定
 * R4 单元 3：模板字面量整体文本以 /api/ 起始
 * R5 计数：按出现次数计；unique 全范围合并去重
 * R6 去重键：展开常量后，${...} → {param}，去掉 ? 后的查询串
 * R7 不统计：非 /api/ 起始的外部地址、注释文本、测试文件
 * R8 规则变更须升 measureVersion
 */

import { readFileSync, readdirSync } from 'node:fs'
import path from 'node:path'

export const MEASURE_VERSION = 'v1'

const CONST_PREFIX_RE = /^[A-Z][A-Z0-9_]*(BASE|PREFIX|ROOT|URL)$/
const CONST_DEFINITION_RE = /(?:export\s+)?const\s+([A-Z][A-Z0-9_]*)\s*=\s*(['"])([^'"]*)\2/g

const ESCAPE_MAP = { n: '\n', t: '\t', r: '\r', b: '\b', f: '\f', v: '\v', 0: '\0' }

function unescapeLiteral(raw) {
  let out = ''
  for (let i = 0; i < raw.length; i += 1) {
    if (raw[i] === '\\' && i + 1 < raw.length) {
      const next = raw[i + 1]
      out += next in ESCAPE_MAP ? ESCAPE_MAP[next] : next
      i += 1
      continue
    }
    out += raw[i]
  }
  return out
}

function collectConstants(source) {
  const constants = new Map()
  for (const match of source.matchAll(CONST_DEFINITION_RE)) {
    constants.set(match[1], unescapeLiteral(match[3]))
  }
  return constants
}

/**
 * 逐字符状态机扫描，区分代码 / 注释 / 字符串 / 模板。
 * 只收集字面量，不解释 TypeScript 语义。
 */
function scanLiterals(source) {
  const literals = []
  let index = 0
  let mode = 'code'
  let buffer = ''

  while (index < source.length) {
    const current = source[index]
    const next = source[index + 1]

    if (mode === 'code') {
      if (current === '/' && next === '/') {
        mode = 'line-comment'
        index += 2
        continue
      }
      if (current === '/' && next === '*') {
        mode = 'block-comment'
        index += 2
        continue
      }
      if (current === "'") {
        mode = 'single-quote'
        buffer = ''
        index += 1
        continue
      }
      if (current === '"') {
        mode = 'double-quote'
        buffer = ''
        index += 1
        continue
      }
      if (current === '`') {
        mode = 'template'
        buffer = ''
        index += 1
        continue
      }
      index += 1
      continue
    }

    if (mode === 'line-comment') {
      if (current === '\n') mode = 'code'
      index += 1
      continue
    }

    if (mode === 'block-comment') {
      if (current === '*' && next === '/') {
        mode = 'code'
        index += 2
        continue
      }
      index += 1
      continue
    }

    if (mode === 'single-quote' || mode === 'double-quote') {
      if (current === '\\') {
        buffer += source.slice(index, index + 2)
        index += 2
        continue
      }
      const quote = mode === 'single-quote' ? "'" : '"'
      if (current === quote) {
        literals.push({ kind: 'string', value: unescapeLiteral(buffer) })
        mode = 'code'
        index += 1
        continue
      }
      buffer += current
      index += 1
      continue
    }

    if (mode === 'template') {
      if (current === '\\') {
        buffer += source.slice(index, index + 2)
        index += 2
        continue
      }
      if (current === '`') {
        literals.push({ kind: 'template', value: buffer })
        mode = 'code'
        index += 1
        continue
      }
      if (current === '$' && next === '{') {
        let depth = 1
        let cursor = index + 2
        while (cursor < source.length && depth > 0) {
          const inner = source[cursor]
          if (inner === '\\') {
            cursor += 2
            continue
          }
          if (inner === '{') depth += 1
          else if (inner === '}') depth -= 1
          cursor += 1
        }
        buffer += source.slice(index, cursor)
        index = cursor
        continue
      }
      buffer += current
      index += 1
      continue
    }
  }

  return literals
}

function normalizeKey(expanded) {
  let key = expanded.replace(/\$\{[^}]*\}/g, '{param}')
  const queryIndex = key.indexOf('?')
  if (queryIndex >= 0) key = key.slice(0, queryIndex)
  return key
}

function walkTypeScriptFiles(directory, extensions, output = []) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.name === '__tests__') continue
    const fullPath = path.join(directory, entry.name)
    if (entry.isDirectory()) {
      walkTypeScriptFiles(fullPath, extensions, output)
      continue
    }
    if (entry.name.endsWith('.d.ts')) continue
    if (entry.isFile() && extensions.some((extension) => entry.name.endsWith(extension))) {
      output.push(fullPath)
    }
  }
  return output
}

function collectFileHits(source) {
  const constants = collectConstants(source)
  const literals = scanLiterals(source)
  const hits = []

  for (const literal of literals) {
    if (literal.kind === 'string') {
      if (!literal.value.startsWith('/api/')) continue
      hits.push(normalizeKey(literal.value))
      continue
    }

    if (literal.value.startsWith('/api/')) {
      hits.push(normalizeKey(literal.value))
      continue
    }

    const prefixMatch = literal.value.match(/^\$\{([A-Za-z_$][A-Za-z0-9_$]*)\}/)
    if (!prefixMatch) continue
    const constantName = prefixMatch[1]
    if (!CONST_PREFIX_RE.test(constantName)) continue
    const base = constants.get(constantName)
    if (base === undefined) continue
    const expanded = `${base}${literal.value.slice(prefixMatch[0].length)}`
    if (!expanded.startsWith('/api/')) continue
    hits.push(normalizeKey(expanded))
  }

  return hits
}

/**
 * 扫描手写路径。
 * @param {{rootDir: string, extensions?: string[]}} options
 * @returns {{measureVersion: string, scope: string, occurrences: number, uniqueCount: number, perFile: Record<string, number>, unique: string[]}}
 */
export function scanHandWrittenPaths(options) {
  const rootDir = options.rootDir
  const extensions = options.extensions ?? ['.ts', '.tsx']
  const files = walkTypeScriptFiles(rootDir, extensions)
  const perFile = {}
  const uniqueKeys = new Set()
  let occurrences = 0

  for (const file of files.sort()) {
    const relative = path.relative(rootDir, file).replaceAll('\\', '/')
    const hits = collectFileHits(readFileSync(file, 'utf8'))
    if (hits.length === 0) continue
    perFile[relative] = hits.length
    occurrences += hits.length
    for (const key of hits) uniqueKeys.add(key)
  }

  const unique = [...uniqueKeys].sort()
  return {
    measureVersion: MEASURE_VERSION,
    scope: 'src/lib/**（排除 __tests__）',
    occurrences,
    uniqueCount: unique.length,
    perFile,
    unique,
  }
}