import type { ConfigSchema, FieldSchema, LocalizedText } from '@/types/config-schema'
import { fieldHooks } from '@/lib/field-hooks'

/** LocalizedText 转 string */
function localizedText(text: LocalizedText): string {
  return typeof text === 'string' ? text : String(Object.values(text)[0] ?? '')
}

/**
 * 编译后端下发的正则，非法时返回 null（不抛）。
 *
 * 判定按 **部分匹配**（`RegExp.test` 的非锚定语义）——与 pydantic v2 `pattern` 一致：
 * 实测 pydantic 2.12 `Field(pattern=r"\d+")` 接受 `abc123` / `123abc`（search 语义）。
 * 若在这里补 `^…$` 锚定，会出现"前端拒绝、后端接受"的假阳性。
 */
function compilePattern(pattern: string): RegExp | null {
  try {
    return new RegExp(pattern)
  } catch {
    return null
  }
}

/**
 * 校验单个字段的 schema 约束，违规时返回可读提示，否则返回空串。
 *
 * 行为对齐老前端 `dashboard/src/components/dynamic-form/DynamicField.tsx:38-69` 的 `validateField`
 * （同样的含边界判定、同样的"值不能小于/大于 X"措辞）——不另发明一套语义。
 *
 * 契约（后端 `src/webui/config_schema.py:389-395` 是唯一映射点）：
 * - `minValue`/`maxValue` ← pydantic `ge`/`le`，**含边界**（等于边界值合法）；
 * - `minLength`/`maxLength` ← pydantic `min_length`/`max_length`，**含边界**；
 * - `pattern` ← pydantic `pattern`，部分匹配。
 * ⚠️ 将来后端会补 `exclusiveMinValue`/`exclusiveMaxValue`（← `gt`/`lt`，**不含边界**，随 12 条约束补丁落地）：
 * 当前后端不发这两个键，故不实现；落地后在本函数补两条分支即可——不要理解成"这两个键永远不存在"。
 *
 * 约束缺失（`undefined`）⇒ 不做任何判定，字段行为与接入约束前完全一致。
 * 一律用 `!== undefined` 判定而非真值判断：`minValue: 0` / `maxLength: 0` 是合法约束。
 */
export function validateFieldConstraints(field: FieldSchema, value: unknown): string {
  if (field.type === 'number' || field.type === 'integer') {
    const numericValue = typeof value === 'number' ? value : parseFloat(String(value))
    // 非有限数（未填 / 空串 / 脏值）不做范围判定——留给 required 与后端，避免前端误报
    if (Number.isFinite(numericValue)) {
      if (field.minValue !== undefined && numericValue < field.minValue) {
        return `值不能小于 ${field.minValue}`
      }
      if (field.maxValue !== undefined && numericValue > field.maxValue) {
        return `值不能大于 ${field.maxValue}`
      }
    }
    return ''
  }

  if (field.type === 'string' && typeof value === 'string') {
    if (field.minLength !== undefined && value.length < field.minLength) {
      return `长度不能少于 ${field.minLength} 个字符`
    }
    if (field.maxLength !== undefined && value.length > field.maxLength) {
      return `长度不能超过 ${field.maxLength} 个字符`
    }
    if (field.pattern !== undefined) {
      const regex = compilePattern(field.pattern)
      // 正则编译失败是后端 schema 的问题，不在前端把用户拦死
      if (regex && !regex.test(value)) {
        return `格式不符合要求：${field.pattern}`
      }
    }
  }

  return ''
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

/** 值 → 受控输入框的显示文本（`null`/`undefined` 回落到 schema 默认值） */
function toInputText(value: unknown, fallback: unknown): string {
  if (value === null || value === undefined) {
    return fallback === null || fallback === undefined ? '' : String(fallback)
  }
  return String(value)
}

/**
 * 输入框原始字符串 → 写进 `values` 的值（**本任务定的解析契约，改它要同步测试**）。
 *
 * - `number` / `integer`：能解析成有限数就写**数字**（`integer` 走 `Math.trunc`，
 *   对齐 dashboard `DynamicField.tsx:342` 的整数分支）；解析不出有限数时**原样保留字符串**：
 *   ① 空串 = "未填写"——`validateFieldConstraints` 对非有限数跳过范围判定，故不会误报越界；
 *      且**不猜成 0** 写回后端（静默把用户的清空改成 0，比报错更隐蔽）；
 *   ② 脏值不写 `NaN`——`JSON.stringify(NaN)` 会变成 `null`，那是静默改语义。
 * - 其余类型原样字符串。`array`/`object` 目前没有编辑器（走文本框兜底），
 *   故数组字段编辑后拿到的是字符串——写回需要列表解析语义，本任务不做。
 */
function parseFieldInputValue(field: FieldSchema, raw: string): unknown {
  if (field.type !== 'number' && field.type !== 'integer') {
    return raw
  }
  if (raw.trim() === '') {
    return raw
  }
  const parsed = Number(raw)
  if (!Number.isFinite(parsed)) {
    return raw
  }
  return field.type === 'integer' ? Math.trunc(parsed) : parsed
}

/**
 * 默认字段渲染器——**受控**：显示值来自 `value`，编辑经 `onChange` 回到表单持有者。
 *
 * ⚠️ 没给 `onChange` 时字段**明确 disabled**：受控组件若无持有者，用户敲的字会被下一帧冲掉，
 * 表现成"输入框坏了"——`AGENTS.md §七` 把这种静默失效列为头号缺陷类，故让它当场可见，而不是默默吞掉。
 */
function DefaultFieldRenderer({
  field,
  value,
  error,
  onChange,
}: {
  field: FieldSchema
  value: unknown
  /** 约束校验提示（见 validateFieldConstraints）——仅用于无障碍标记，提示文本由表单统一渲染 */
  error?: string
  onChange?: (value: unknown) => void
}) {
  const isNumeric = field.type === 'integer' || field.type === 'number'
  const textValue = toInputText(value, field.default)
  const readOnly = !onChange

  if (field.type === 'boolean') {
    return (
      <label className="flex items-center gap-2" data-testid={`field-${field.name}`}>
        <input
          type="checkbox"
          checked={Boolean(value)}
          disabled={readOnly}
          onChange={(e) => onChange?.(e.target.checked)}
        />
        <span className="text-sm">{localizedText(field.label)}</span>
      </label>
    )
  }

  if (field.type === 'select' && field.options) {
    return (
      <div data-testid={`field-${field.name}`}>
        <label className="text-sm font-medium">{localizedText(field.label)}</label>
        <select
          className="w-full rounded-md border px-3 py-2"
          value={textValue}
          disabled={readOnly}
          onChange={(e) => onChange?.(e.target.value)}
        >
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
        <textarea
          className="w-full rounded-md border px-3 py-2"
          value={textValue}
          disabled={readOnly}
          onChange={(e) => onChange?.(e.target.value)}
        />
      </div>
    )
  }

  return (
    <div data-testid={`field-${field.name}`}>
      <label className="text-sm font-medium">{localizedText(field.label)}</label>
      <input
        type={isNumeric ? 'number' : 'text'}
        className="w-full rounded-md border px-3 py-2"
        value={textValue}
        disabled={readOnly}
        onChange={(e) => onChange?.(parseFieldInputValue(field, e.target.value))}
        // 数值上下界（含边界）——浏览器侧兜底；提交前判定见 validateFieldConstraints
        min={isNumeric ? field.minValue : undefined}
        max={isNumeric ? field.maxValue : undefined}
        // 字符串长度 / 格式约束——12 条约束补丁落地前后端不下发，届时自动生效
        minLength={isNumeric ? undefined : field.minLength}
        maxLength={isNumeric ? undefined : field.maxLength}
        pattern={isNumeric ? undefined : field.pattern}
        aria-invalid={error ? true : undefined}
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
        // 提交前校验：表单持有的 values 逐字段过 schema 约束，越界值在界面上显形（可读提示，不静默拦）
        const error = validateFieldConstraints(field, value)

        // ⚠️ 这里必须透传"表单有没有 onChange"，不能每帧现造一个箭头函数——
        // 现造的箭头恒为 truthy，默认渲染器就无从判断自己有没有持有者，字段会静默变成只吞不认。
        const commitField = onChange
          ? (nextValue: unknown) => onChange(field.name, nextValue)
          : undefined

        // type: 'replace' → 完全替换默认渲染；'wrapper' → 包裹默认渲染；无注册 → 默认渲染
        const renderField = () => {
          if (hook?.type === 'replace') {
            const HookComponent = hook.component
            return (
              <HookComponent
                fieldPath={field.name}
                value={value}
                onChange={commitField}
                schema={field}
              />
            )
          }

          if (hook?.type === 'wrapper') {
            const HookComponent = hook.component
            return (
              <HookComponent fieldPath={field.name} value={value} schema={field}>
                <DefaultFieldRenderer
                  field={field}
                  value={value}
                  error={error}
                  onChange={commitField}
                />
              </HookComponent>
            )
          }

          return (
            <DefaultFieldRenderer
              field={field}
              value={value}
              error={error}
              onChange={commitField}
            />
          )
        }

        return (
          <div key={field.name}>
            {renderField()}
            {error && (
              <p
                className="text-xs text-destructive"
                data-testid={`field-error-${field.name}`}
              >
                {error}
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}