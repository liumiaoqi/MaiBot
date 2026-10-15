/**
 * 适配层：**嵌套对象 ⇄ 扁平条目表**（task-11 · A）。
 *
 * 为什么需要它：旧读端点回**嵌套对象**（`{bot:{chat:{max_context_size:40}}}`），
 * 新接缝按**路径**进出（`{path:'chat.max_context_size', value:40, inherited:false}`）。
 * 页面拿到的仍是嵌套结构，接缝只认路径 ⇒ 中间需要一层**双向、无损**的转换。
 *
 * **边界（刻意不越）**：本层只做**形状转换**——不校验 schema、不填默认值、不做类型纠正。
 * "这个值该不该是整数""这个键该不该有"是后端 schema 的事；前端越权校验会让
 * "后端拒绝"变成"前端猜错"，两处口径必然漂移。
 *
 * 三处对齐后端的实现细节（别"优化"掉，每条都有判据）：
 * 1. **空表 / 空数组也算叶**（`iter_leaf_paths`）——它们本身就是"值"：丢了它们，
 *    `{}` 与"键不存在"就分不开，往返即失真。
 * 2. **`null` 与"缺失"不混同**——`null` 是**存在**的叶（本仓老坑：三态用 `MISSING`
 *    区分"未提供"与 `None`），所以 `{a:null}` 与 `{}` 必须转出不同的结果。
 * 3. **文档顺序**——后端按 `dict` 保序输出，前端保持同一顺序（往返才可能逐字符一致）。
 */

import { formatConfigPath, isSecretMarker, parseConfigPath } from './config-paths'
import type {
  ConfigMutateOp,
  ConfigPathToken,
  ConfigReadEntry,
} from '@/lib/config-api'

/** 一个扁平叶：路径 + 值（`value` 允许是 `null`、空表、空数组——它们都是**存在**的值） */
export interface FlatConfigLeaf {
  path: string
  value: unknown
}

function isPlainMapping(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

/**
 * 列出一棵树里的全部叶路径（镜像后端 `iter_leaf_paths`）。
 *
 * ⚠️ JS 对象会把"整数样"的键排在前面（引擎规范），而 Python `dict` 严格保插入序 ⇒
 * 纯数字键名的表在**键序**上可能与后端不同。MaiBot 的配置键是 snake_case，取不到这种形状；
 * 真遇到时影响的是"顺序"，不影响路径与值的正确性。
 */
export function flattenConfig(root: unknown): FlatConfigLeaf[] {
  const leaves: FlatConfigLeaf[] = []
  collectLeaves(root, [], leaves)
  return leaves
}

function collectLeaves(node: unknown, prefix: ConfigPathToken[], leaves: FlatConfigLeaf[]): void {
  if (isPlainMapping(node)) {
    const keys = Object.keys(node)
    if (keys.length === 0) {
      if (prefix.length > 0) {
        leaves.push({ path: formatConfigPath(prefix), value: node })
      }
      return
    }
    for (const key of keys) {
      collectLeaves(node[key], [...prefix, key], leaves)
    }
    return
  }

  if (Array.isArray(node)) {
    if (node.length === 0) {
      if (prefix.length > 0) {
        leaves.push({ path: formatConfigPath(prefix), value: node })
      }
      return
    }
    node.forEach((item, index) => {
      collectLeaves(item, [...prefix, index], leaves)
    })
    return
  }

  if (prefix.length > 0) {
    leaves.push({ path: formatConfigPath(prefix), value: node })
  }
}

/** 扁平叶 → 嵌套对象（依路径建容器：下一段是下标就建数组，否则建表） */
export function unflattenConfig(leaves: FlatConfigLeaf[]): Record<string, unknown> {
  const root: Record<string, unknown> = {}
  for (const leaf of leaves) {
    assignFlatLeaf(root, parseConfigPath(leaf.path), leaf.value, leaf.path)
  }
  return root
}

function assignFlatLeaf(
  root: Record<string, unknown>,
  tokens: ConfigPathToken[],
  value: unknown,
  pathText: string,
): void {
  let cursor: Record<string, unknown> | unknown[] = root

  for (let i = 0; i < tokens.length - 1; i += 1) {
    const token = tokens[i]
    const nextToken = tokens[i + 1]

    if (typeof token === 'number') {
      if (!Array.isArray(cursor)) {
        throw new Error(`扁平叶路径与容器类型不符（下标落在了表上）：${pathText}`)
      }
      // 显式标注 `unknown`：不标的话 `cursor = existing` 与 `existing = cursor[token]`
      // 构成控制流环，TS 报 7022（隐式 any）——类型检查是真判据，别留它
      const existing: unknown = cursor[token]
      if (existing === undefined) {
        // 镜像后端 `assign_path`：下标 == 当前长度 ⇒ **追加**（那是"加一条数据"）；
        // 下标 > 长度 ⇒ 报错（不做空洞填充，TOML 数组不允许空洞）。
        if (token !== cursor.length) {
          throw new Error(`扁平叶路径跳过了中间下标（不做空洞填充）：${pathText}`)
        }
        const created = typeof nextToken === 'number' ? [] : {}
        cursor.push(created)
        cursor = created
        continue
      }
      if (!isPlainMapping(existing) && !Array.isArray(existing)) {
        throw new Error(`扁平叶路径的中间层不是表/数组：${pathText}`)
      }
      cursor = existing
      continue
    }

    if (Array.isArray(cursor)) {
      throw new Error(`扁平叶路径与容器类型不符（键落在了数组上）：${pathText}`)
    }
    // 同上：显式 `unknown` 破开 `cursor = child` 与 `child = cursor[token]` 的控制流环
    let child: unknown = cursor[token]
    if (child === undefined) {
      child = typeof nextToken === 'number' ? [] : {}
      cursor[token] = child
    }
    if (!isPlainMapping(child) && !Array.isArray(child)) {
      throw new Error(`扁平叶路径的中间层不是表/数组：${pathText}`)
    }
    cursor = child
  }

  const lastToken = tokens[tokens.length - 1]
  if (typeof lastToken === 'number') {
    if (!Array.isArray(cursor)) {
      throw new Error(`扁平叶路径与容器类型不符（下标落在了表上）：${pathText}`)
    }
    if (lastToken > cursor.length) {
      throw new Error(`扁平叶路径跳过了中间下标（不做空洞填充）：${pathText}`)
    }
    if (lastToken === cursor.length) {
      cursor.push(value)
      return
    }
    cursor[lastToken] = value
    return
  }
  if (Array.isArray(cursor)) {
    throw new Error(`扁平叶路径与容器类型不符（键落在了数组上）：${pathText}`)
  }
  cursor[lastToken] = value
}

/**
 * 读条目表 → 嵌套对象。
 *
 * **秘密占位不是值**：`{$secret, path, set}` 说的是"这里有一个秘密，真值没出站"，
 * 把它塞进嵌套结构会凭空造出一个键（文件里可能根本没有这个键，`set:false` 就是这种情况）。
 * 所以这里**跳过**标记项——三态由 UI 单独渲染（见 `components/secret-state-field.tsx`）。
 */
export function entriesToNested(entries: ConfigReadEntry[]): Record<string, unknown> {
  const leaves: FlatConfigLeaf[] = []
  for (const entry of entries) {
    if (isSecretMarker(entry.value)) {
      continue
    }
    leaves.push({ path: entry.path, value: entry.value })
  }
  return unflattenConfig(leaves)
}

/**
 * 嵌套对象 → 读条目表（给"本地结构要按接缝形状送出去"的场合用）。
 *
 * ⚠️ `inherited` 一律 `false`：本地对象里没有"这个键在不在文件里"的信息，
 * 编一个 `true` 会让"值来自 schema 默认"这个判据失真。要真值就得走接缝读。
 */
export function nestedToEntries(nested: unknown, revision = 0): ConfigReadEntry[] {
  return flattenConfig(nested).map((leaf) => ({
    path: leaf.path,
    value: leaf.value,
    inherited: false,
    revision,
  }))
}

/**
 * 算出"要把 `baseline` 变成 `next`"需要的最小操作集（**只发改动的点**）。
 *
 * 这是"不再整份覆盖"的落点：没被点名的路径根本不进写路径，
 * 所以页面上没有的字段、以及**别的写者刚改过而用户没碰**的字段都不会被抹掉。
 *
 * 三处约定（各有理由，改前先读）：
 * - **`null` / `undefined` ⇒ `unset`（重置为继承）**：TOML **无法表达 `null`**
 *   （后端 `set` 遇 `null` 直接 400），而 `undefined` 根本不是 JSON 值。
 *   在这个配置世界里，"清空"唯一可表达的含义就是"把这个键从文件里删掉"。
 *   ⚠️ 只对**基线里存在**的键发 `unset`：基线本就没有 ⇒ 已经是继承态，无需操作。
 * - **数组下标差** ⇒ `remove_at`（F8：`path` 指容器、下标走 `index`），且**从大到小**删，
 *   否则删掉 `[1]` 会让 `[2]` 的下标前移，后面全错位。
 * - **形状变了（标量 ⇄ 容器 / 表 ⇄ 数组）或基线里没有整个子树** ⇒ 对该子树发**一次** `set`。
 *   这是刻意的粒度边界：形状都变了，逐叶下钻没有意义；且用户既然重造了这棵子树，
 *   其内部就没有"没展示的字段"可言。
 */
export function diffToMutateOps(baseline: unknown, next: unknown): ConfigMutateOp[] {
  const ops: ConfigMutateOp[] = []
  diffNode(baseline, next, [], ops)
  return ops
}

function diffNode(
  base: unknown,
  nxt: unknown,
  tokens: ConfigPathToken[],
  ops: ConfigMutateOp[],
): void {
  if (nxt === undefined || nxt === null) {
    if (tokens.length > 0 && hasLeafAt(base)) {
      emitUnsetOrRemoveIndex(tokens, ops)
    }
    return
  }

  if (isPlainMapping(base) && isPlainMapping(nxt)) {
    for (const key of Object.keys(nxt)) {
      diffNode(
        Object.prototype.hasOwnProperty.call(base, key) ? base[key] : undefined,
        nxt[key],
        [...tokens, key],
        ops,
      )
    }
    for (const key of Object.keys(base)) {
      if (!Object.prototype.hasOwnProperty.call(nxt, key)) {
        diffNode(base[key], undefined, [...tokens, key], ops)
      }
    }
    return
  }

  if (Array.isArray(base) && Array.isArray(nxt)) {
    const common = Math.min(base.length, nxt.length)
    for (let index = 0; index < common; index += 1) {
      diffNode(base[index], nxt[index], [...tokens, index], ops)
    }
    // 新增元素：下标 == 当前长度 ⇒ 后端 assign_path 走"追加"分支，故**升序**发
    for (let index = base.length; index < nxt.length; index += 1) {
      ops.push({ op: 'set', path: formatConfigPath([...tokens, index]), value: nxt[index] })
    }
    // 删元素：**降序**发，避免前面的删除让后面的下标前移
    for (let index = base.length - 1; index >= nxt.length; index -= 1) {
      ops.push({ op: 'remove_at', path: formatConfigPath(tokens), index })
    }
    return
  }

  if (isPlainMapping(nxt) || Array.isArray(nxt)) {
    // 形状变了（或基线里没有这棵子树）：整棵发一次 set
    ops.push({ op: 'set', path: formatConfigPath(tokens), value: nxt })
    return
  }

  if (!Object.is(base, nxt)) {
    ops.push({ op: 'set', path: formatConfigPath(tokens), value: nxt })
  }
}

/** 基线在该位置**有没有值**（`null` 也算有——它是存在的叶） */
function hasLeafAt(base: unknown): boolean {
  return base !== undefined
}

function emitUnsetOrRemoveIndex(tokens: ConfigPathToken[], ops: ConfigMutateOp[]): void {
  const lastToken = tokens[tokens.length - 1]
  if (typeof lastToken === 'number') {
    // 数组元素要用 remove_at；正常路径由数组分支产出，这里是防御分支
    ops.push({ op: 'remove_at', path: formatConfigPath(tokens.slice(0, -1)), index: lastToken })
    return
  }
  ops.push({ op: 'unset', path: formatConfigPath(tokens) })
}
