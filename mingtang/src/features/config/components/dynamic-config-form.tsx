import type { ConfigSchema, FieldSchema, LocalizedText } from '@/types/config-schema'
import { fieldHooks } from '@/lib/field-hooks'

/** LocalizedText 转 string */
function localizedText(text: LocalizedText): string {
  return typeof text === 'string' ? text : String(Object.values(text)[0] ?? '')
}

interface DynamicConfigFormProps {
  /** 配置 schema */
  schema: ConfigSchema
  /** 当前配置值 */
  values: Record<string, unknown>
  /** 值变更回调 */
  onChange?: (field: string, value: unknown) => void
  /** 隐藏字段列表（手动指定跳过渲染的字段） */
  hiddenFields?: string[]
  /** 是否显示高级字段 */
  advancedVisible?: boolean
}

/** 默认字段渲染器 */
function DefaultFieldRenderer({ field, value }: { field: FieldSchema; value: unknown }) {
  if (field.type === 'boolean') {
    return (
      <label className="flex items-center gap-2" data-testid={`field-${field.name}`}>
        <input type="checkbox" defaultChecked={value as boolean} />
        <span className="text-sm">{localizedText(field.label)}</span>
      </label>
    )
  }

  if (field.type === 'select' && field.options) {
    return (
      <div data-testid={`field-${field.name}`}>
        <label className="text-sm font-medium">{localizedText(field.label)}</label>
        <select className="w-full rounded-md border px-3 py-2" defaultValue={value as string}>
          {field.options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </div>
    )
  }

  if (field.type === 'textarea') {
    return (
      <div data-testid={`field-${field.name}`}>
        <label className="text-sm font-medium">{localizedText(field.label)}</label>
        <textarea className="w-full rounded-md border px-3 py-2" defaultValue={value as string} />
      </div>
    )
  }

  return (
    <div data-testid={`field-${field.name}`}>
      <label className="text-sm font-medium">{localizedText(field.label)}</label>
      <input
        type={field.type === 'integer' || field.type === 'number' ? 'number' : 'text'}
        className="w-full rounded-md border px-3 py-2"
        defaultValue={value as string}
      />
      {field.description && (
        <p className="text-xs text-muted-foreground">{field.description}</p>
      )}
    </div>
  )
}

/** schema 驱动表单引擎——消费 ConfigSchema + fieldHooks 注册表 */
export function DynamicConfigForm({
  schema,
  values,
  onChange,
  hiddenFields = [],
  advancedVisible = false,
}: DynamicConfigFormProps) {

  const visibleFields = schema.fields.filter((field) => {
    // 手动隐藏字段
    if (hiddenFields.includes(field.name)) return false
    // fieldHooks type: 'hidden'
    const hook = fieldHooks.get(field.name)
    if (hook?.type === 'hidden') return false
    // 高级字段
    if (field.advanced && !advancedVisible) return false
    return true
  })

  return (
    <div className="space-y-4" data-testid="dynamic-config-form">
      {visibleFields.map((field) => {
        const value = values[field.name]
        const hook = fieldHooks.get(field.name)

        // type: 'replace' → 完全替换默认渲染
        if (hook?.type === 'replace') {
          const HookComponent = hook.component
          return (
            <div key={field.name}>
              <HookComponent
                fieldPath={field.name}
                value={value}
                onChange={(v) => onChange?.(field.name, v)}
                schema={field}
              />
            </div>
          )
        }

        // type: 'wrapper' → 包裹默认渲染
        if (hook?.type === 'wrapper') {
          const HookComponent = hook.component
          return (
            <div key={field.name}>
              <HookComponent fieldPath={field.name} value={value} schema={field}>
                <DefaultFieldRenderer field={field} value={value} />
              </HookComponent>
            </div>
          )
        }

        // 无注册 → 默认渲染
        return (
          <div key={field.name}>
            <DefaultFieldRenderer field={field} value={value} />
          </div>
        )
      })}
    </div>
  )
}