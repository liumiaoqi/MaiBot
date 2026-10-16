/**
 * 本批接入的配置域（(a)-⑤）——**只接纯标量域**，其余 100 个域不动。
 *
 * 选这 6 个域的依据（2026-10-16 容器内实测 `ConfigSchemaGenerator`）：
 *
 * | 域 | 标量字段 | 有约束 | 其中**非高级** | 异形字段 |
 * |---|---|---|---|---|
 * | `agent_autonomy` | 46 | 29 | 3 | 0 |
 * | `chat` | 20 | 10 | 10 | 2（object） |
 * | `a_memorix.integration` | 22 | 14 | 1 | 0 |
 * | `agent_interaction` | 12 | 9 | 4 | 0 |
 * | `visual` | 7 | 6 | 5 | 1（object） |
 * | `bot` | 3 | 0 | 0 | 3（array，task-8 时曾按文本框兜底渲染，本批改为显式跳过） |
 *
 * ⚠️ **为什么必须跳过 `array` / `object` / `x-widget: custom`**：
 * `features/config/hooks/index.ts` 的 8 个注册函数**全是空壳** ⇒ 这些字段没有真编辑器，
 * 会落到文本框兜底，编辑后 state 里是**字符串而不是数组** ⇒ 一旦接落盘就写回**类型不符的值**。
 * 所以这里**显式剔除**并把被剔除的名字回报给界面（`prepareDomainForm` 的 `skipped`），
 * **不静默兜底**——静默兜底正是"写坏数据"那条路的入口。
 */

import type { ConfigSchema, FieldSchema, LocalizedText } from '@/types/config-schema'
import { parseConfigPath } from '../seam/config-paths'

/** 接入顺序 = 界面上的排列顺序（约束多、字段多的靠前） */
export const WIRED_DOMAIN_PATHS = [
  'agent_autonomy',
  'chat',
  'a_memorix.integration',
  'agent_interaction',
  'visual',
  'bot',
] as const

/** 字段被跳过的原因（三选一，写进界面的提示里） */
export type SkippedFieldReason = 'array' | 'object' | 'custom-widget'

export interface SkippedField {
  name: string
  reason: SkippedFieldReason
}

export interface PreparedDomainForm {
  /** 只含可渲染字段的 schema（原对象不改；`fields` 是新数组） */
  schema: ConfigSchema
  /** 被显式跳过的异形字段（界面要如实报出来） */
  skipped: SkippedField[]
}

export interface WiredDomainInfo {
  path: string
  label: LocalizedText
  /** 会渲染的字段数（已剔除异形） */
  renderableCount: number
  skippedCount: number
  /** 后端 schema 的 `uiOrder`（排序用；缺失记 `null`，排在最后） */
  uiOrder: number | null
}

/**
 * 域路径 → 键 token。
 *
 * 复用 2 段接缝的**唯一路径解析入口**（`seam/config-paths.ts`，镜像后端 `parse_path`），
 * 不再写一套 `split('.')`：域路径与配置路径同源，两套解析迟早会漂。
 * 域路径**只允许键名**——出现下标说明用错了地方（域不是数组元素），直接报错而不是猜。
 */
function domainKeyTokens(path: string): string[] {
  const tokens = parseConfigPath(path)
  if (tokens.some((token) => typeof token !== 'string')) {
    throw new Error(`域路径不能含数组下标：${path}`)
  }
  return tokens.filter((token): token is string => typeof token === 'string')
}

/** 按域路径取该域的 schema 节点（走 `nested`） */
export function resolveDomainSchema(
  root: ConfigSchema,
  domainPath: string,
): ConfigSchema | undefined {
  let node: ConfigSchema | undefined = root
  for (const token of domainKeyTokens(domainPath)) {
    node = node?.nested?.[token]
    if (!node) {
      return undefined
    }
  }
  return node
}

/** 按域路径取该域的**当前值字典**（`a_memorix.integration` ⇒ `config.a_memorix.integration`） */
export function readDomainValues(config: unknown, domainPath: string): Record<string, unknown> {
  let cursor: unknown = config
  for (const token of domainKeyTokens(domainPath)) {
    if (cursor === null || typeof cursor !== 'object' || Array.isArray(cursor)) {
      return {}
    }
    cursor = (cursor as Record<string, unknown>)[token]
  }
  if (cursor === null || typeof cursor !== 'object' || Array.isArray(cursor)) {
    return {}
  }
  return cursor as Record<string, unknown>
}

/** 字段能不能用**现有**渲染器安全处理（只有标量能；异形字段见文件头说明） */
function skipReasonOf(field: FieldSchema): SkippedFieldReason | undefined {
  if (field.type === 'array') {
    return 'array'
  }
  if (field.type === 'object') {
    return 'object'
  }
  if (field['x-widget'] === 'custom') {
    return 'custom-widget'
  }
  return undefined
}

/**
 * 把一个域的 schema 收敛成"能安全渲染的那部分"。
 *
 * **不做业务校验、不改字段定义**：只按类型/控件剔掉前端今天处理不了的字段，并如实登记，
 * 让界面能把"哪些字段没渲染、为什么"说清楚（静默少渲染 = 用户以为"这域就这些字段"）。
 */
export function prepareDomainForm(domainSchema: ConfigSchema): PreparedDomainForm {
  const fields: FieldSchema[] = []
  const skipped: SkippedField[] = []

  for (const field of domainSchema.fields) {
    const reason = skipReasonOf(field)
    if (reason) {
      skipped.push({ name: field.name, reason })
      continue
    }
    fields.push(field)
  }

  return { schema: { ...domainSchema, fields }, skipped }
}

/**
 * 域节点的显示名。
 *
 * ⚠️ 实测事实：后端 `ConfigSchema.uiLabel` 是**纯字符串**（`'基础'` / `'聊天'` / `'记忆'`），
 * 与 `FieldSchema.label` 的 `LocalizedText`（`{zh_CN:…}` 字典）**不是一种东西**
 * ⇒ 域级名字**今天根本没有多语言**，这里原样透传（字符串本身就是合法的 `LocalizedText`），
 * 不编一个 `{zh_CN: …}` 出来假装有翻译。
 *
 * 后端 schema 只有 **32/92** 个域节点带 `uiLabel`（`a_memorix.integration` 就没有，
 * 它的父节点 `a_memorix` 有「记忆」）⇒ 按"自身 → 最近有名字的祖先 + 叶子键名 → 原始路径"
 * 三级回落，**不硬编码中文**（硬编码会与后端 label 漂移，而 label 是后端派生的）。
 */
export function resolveDomainLabel(root: ConfigSchema, domainPath: string): LocalizedText {
  const schema = resolveDomainSchema(root, domainPath)
  if (schema?.uiLabel) {
    return schema.uiLabel
  }

  const tokens = domainKeyTokens(domainPath)
  const leaf = tokens[tokens.length - 1]
  for (let depth = tokens.length - 1; depth > 0; depth -= 1) {
    const ancestor = resolveDomainSchema(root, tokens.slice(0, depth).join('.'))
    if (ancestor?.uiLabel) {
      return `${ancestor.uiLabel} · ${leaf}`
    }
  }
  return domainPath
}

/**
 * 本批接入且**该 schema 里确实存在**的域（不存在的不列出，免得点进去是空的）。
 *
 * 排序用后端 schema 的 `uiOrder`（`bot` 10 → `chat` 20 → `agent_interaction` 51 → `agent_autonomy` 52
 * → `visual` 60；`a_memorix.integration` 没有 `uiOrder` ⇒ 排最后）。
 * **不按我写死的顺序排**：顺序是后端给的元数据，前端重排一次就多一处漂移点。
 */
export function listWiredDomains(root: ConfigSchema): WiredDomainInfo[] {
  const domains: WiredDomainInfo[] = []

  for (const path of WIRED_DOMAIN_PATHS) {
    const domainSchema = resolveDomainSchema(root, path)
    if (!domainSchema) {
      continue
    }
    const { schema, skipped } = prepareDomainForm(domainSchema)
    domains.push({
      path,
      label: resolveDomainLabel(root, path),
      renderableCount: schema.fields.length,
      skippedCount: skipped.length,
      uiOrder: typeof domainSchema.uiOrder === 'number' ? domainSchema.uiOrder : null,
    })
  }

  // 同 `uiOrder` 或都缺失时保持 `WIRED_DOMAIN_PATHS` 的接入顺序
  //（ES2019+ 的 sort 是稳定排序，返回 0 即保持插入序）
  return domains.sort((left, right) => {
    if (left.uiOrder === right.uiOrder) {
      return 0
    }
    if (left.uiOrder === null) {
      return 1
    }
    if (right.uiOrder === null) {
      return -1
    }
    return left.uiOrder - right.uiOrder
  })
}

/** schema 里全部域节点数（用来如实报出"其余 N 个域未接入"） */
export function countAllDomains(root: ConfigSchema): number {
  let count = 0
  const walk = (node: ConfigSchema): void => {
    for (const child of Object.values(node.nested ?? {})) {
      count += 1
      walk(child)
    }
  }
  walk(root)
  return count
}
