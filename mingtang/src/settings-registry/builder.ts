import type { ConfigSchema, FieldSchema, LocalizedText } from '@/types/config-schema'
import { fieldHooks } from '@/lib/field-hooks'
import type { SettingsRegistryEntry } from './settings-registry'

/** 从字段构建关键词（label / name / description / options / 分组路径） */
function buildFieldKeywords(
  field: FieldSchema,
  fieldPath: string,
  groupTrail: string[]
): LocalizedText[] {
  const keywords: LocalizedText[] = []

  // label
  if (field.label) {
    keywords.push(field.label)
  }

  // name（英文标识符）
  keywords.push(field.name)

  // description（如有）
  if (field.description) {
    keywords.push(field.description)
  }

  // options
  if (field.options) {
    for (const opt of field.options) {
      keywords.push(opt)
    }
  }

  // 分组路径
  for (const g of groupTrail) {
    keywords.push(g)
  }

  // fieldPath 去空格变体
  keywords.push(fieldPath.replace(/\s+/g, ''))

  return keywords
}

/** 递归遍历 schema 构建条目 */
function collectFields(
  schema: ConfigSchema,
  category: string,
  route: string,
  parentPath: string,
  groupTrail: string[],
  schemaRef: string
): SettingsRegistryEntry[] {
  const entries: SettingsRegistryEntry[] = []

  // 遍历 fields
  for (const field of schema.fields) {
    const fieldPath = parentPath ? `${parentPath}.${field.name}` : field.name

    // 检查 fieldHooks——hidden 跳过
    const hook = fieldHooks.get(fieldPath)
    if (hook?.type === 'hidden') {
      continue
    }

    const id = `auto:${category}:${fieldPath}`
    const keywords = buildFieldKeywords(field, fieldPath, groupTrail)

    entries.push({
      id,
      title: field.label,
      category,
      keywords,
      route,
      fieldPath,
      schemaRef,
      advanced: field.advanced,
      customEditor: hook ? hook.type : undefined,
      source: 'auto',
    })

    // 递归 properties（嵌套对象字段）
    if (field.properties) {
      const nestedTrail = [...groupTrail, typeof field.label === 'string' ? field.label : field.name]
      entries.push(
        ...collectFields(
          field.properties,
          category,
          route,
          fieldPath,
          nestedTrail,
          schemaRef
        )
      )
    }
  }

  // 遍历 nested
  if (schema.nested) {
    for (const [nestedKey, nestedSchema] of Object.entries(schema.nested)) {
      const nestedPath = parentPath ? `${parentPath}.${nestedKey}` : nestedKey
      const nestedTrail = [
        ...groupTrail,
        nestedSchema.uiLabel ?? nestedKey,
      ]
      entries.push(
        ...collectFields(
          nestedSchema,
          category,
          route,
          nestedPath,
          nestedTrail,
          schemaRef
        )
      )
    }
  }

  return entries
}

/** 从 ConfigSchema 自动构建注册表条目 */
export function buildEntriesFromSchema(
  schema: ConfigSchema,
  category: string,
  route: string
): SettingsRegistryEntry[] {
  const schemaRef = schema.className
  return collectFields(schema, category, route, '', [], schemaRef)
}