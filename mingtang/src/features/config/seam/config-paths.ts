/**
 * 配置路径代数 —— `src/webui/config_paths.py` 的前端镜像（**唯一解析入口**）。
 *
 * 为什么要镜像而不是"前端自己定一套"：读写接缝的 `path` 是**跨端契约**——
 * 前端拼错一个下标，后端要么 400、要么更糟：**写到别的键上**。
 * 所以这里逐分支对齐后端的 `parse_path` / `format_path` / `is_redaction_sentinel`。
 *
 * 语法：`a.b[0].c`——键用 `.` 分隔、下标用 `[n]`（非负整数），根必须是键。
 * 声明语法里的 `[]`（"任意下标"）是**后端专有**的，运行时路径不接受（同后端）。
 */

import type { ConfigPathToken, ConfigSecretMarker } from '@/lib/config-api'

/** 路径语法错误（对应后端 `ConfigPathError` 的**语法**分支，不含"数据上走不通"） */
export class ConfigPathFormatError extends Error {
  readonly path: string

  constructor(message: string, path: string) {
    super(path ? `${message}（路径：${path}）` : message)
    this.name = 'ConfigPathFormatError'
    this.path = path
  }
}

/**
 * 键名字符集：后端用 Python 的 `\w`（Unicode 字母 / 数字 / 下划线）**外加**显式 `-`。
 * JS 的 `\w` 只有 ASCII ⇒ 用 `\p{L}\p{N}` 保持同样的宽口径（配置键实际是 ASCII snake_case，
 * 放宽只是不误判成下标，与后端一致）。
 */
const KEY_PATTERN = /^[\p{L}\p{N}_-]+/u

/** 路径文本 → token 数组（`"api_providers[1].api_key"` ⇒ `['api_providers', 1, 'api_key']`） */
export function parseConfigPath(path: string): ConfigPathToken[] {
  if (typeof path !== 'string' || !path.trim()) {
    throw new ConfigPathFormatError('配置路径不能为空', String(path))
  }

  const text = path.trim()
  const tokens: ConfigPathToken[] = []
  let cursor = 0
  // 每读到一个元素后置 true：下一个位置必须是 `.` / `[` / 结尾，不能再直接接键名
  let expectingSeparator = false

  while (cursor < text.length) {
    const char = text[cursor]

    if (char === '.') {
      if (!expectingSeparator) {
        throw new ConfigPathFormatError("路径里出现多余的分隔符 '.'", path)
      }
      cursor += 1
      expectingSeparator = false
      if (cursor >= text.length) {
        throw new ConfigPathFormatError("路径不能以 '.' 结尾", path)
      }
      continue
    }

    if (char === '[') {
      if (!expectingSeparator) {
        throw new ConfigPathFormatError("下标 '[' 只能跟在键名或另一个下标之后", path)
      }
      const closing = text.indexOf(']', cursor)
      if (closing < 0) {
        throw new ConfigPathFormatError("下标缺少配对的 ']'", path)
      }
      const rawIndex = text.slice(cursor + 1, closing)
      if (!rawIndex) {
        throw new ConfigPathFormatError("运行时路径的下标不能留空（'[]' 只用于声明）", path)
      }
      if (!/^\d+$/.test(rawIndex)) {
        throw new ConfigPathFormatError(`下标必须是非负整数，收到 '${rawIndex}'`, path)
      }
      tokens.push(Number(rawIndex))
      cursor = closing + 1
      continue
    }

    if (expectingSeparator) {
      throw new ConfigPathFormatError(`位置 ${cursor} 缺少分隔符 '.' 或下标`, path)
    }

    const matched = KEY_PATTERN.exec(text.slice(cursor))
    if (matched === null) {
      throw new ConfigPathFormatError(`位置 ${cursor} 不是合法的键名`, path)
    }
    tokens.push(matched[0])
    cursor += matched[0].length
    expectingSeparator = true
  }

  if (tokens.length === 0) {
    throw new ConfigPathFormatError('配置路径不能为空', path)
  }
  if (typeof tokens[0] === 'number') {
    throw new ConfigPathFormatError('路径的根必须是键名（配置文件根是表，不是数组）', path)
  }
  return tokens
}

/** token 数组 → 路径文本（`parseConfigPath` 的逆） */
export function formatConfigPath(tokens: ConfigPathToken[]): string {
  const parts: string[] = []
  for (const token of tokens) {
    if (typeof token === 'number') {
      if (parts.length === 0) {
        throw new ConfigPathFormatError('路径的根不能是下标', '')
      }
      parts[parts.length - 1] = `${parts[parts.length - 1]}[${token}]`
      continue
    }
    parts.push(token)
  }
  return parts.join('.')
}

/**
 * 判断一个值是不是**秘密占位**（镜像后端 `is_redaction_sentinel`）。
 *
 * 后端认两种形状：本版 `{$secret, path, set}` 与上一版遗留的 `{path, set}`
 * （老客户端手里的占位不该因为服务端升级就变成废纸）——这里同样都认。
 *
 * ⚠️ 比后端**多做了类型检查**（`path` 必须 string、`set` 必须 boolean）：后端那边
 * 形状判定只用于"是不是自己刚发出去的占位"，而前端还会拿它判"这张表能不能当普通数据写回去"，
 * 严格一点才不会被恰好长成 `{path, set}` 的**普通配置表**骗到（后端 F6 的同款顾虑）。
 */
export function isSecretMarker(value: unknown): value is ConfigSecretMarker {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }
  const record = value as Record<string, unknown>
  if (typeof record.path !== 'string' || typeof record.set !== 'boolean') {
    return false
  }
  if (!('$secret' in record)) {
    return true
  }
  return record.$secret === true
}
