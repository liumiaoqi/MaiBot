/**
 * 配置架构类型定义
 */

export type FieldType =
  | 'string'
  | 'number'
  | 'integer'
  | 'boolean'
  | 'select'
  | 'array'
  | 'object'
  | 'textarea'

export type XWidgetType =
  | 'custom'
  | 'input'
  | 'number'
  | 'password'
  | 'select'
  | 'slider'
  | 'switch'
  | 'tags'
  | 'talk-time'
  | 'textarea'
  | 'comma-list'

export type LocalizedText = string | Record<string, string>
export type DescriptionDisplayMode = 'inline' | 'icon' | 'label-hover'

export interface FieldSchema {
  name: string
  type: FieldType
  label: LocalizedText
  description: string
  required: boolean
  default?: unknown
  options?: string[]
  /**
   * 数值下界 / 上界——**含边界**（pydantic `ge`/`le` 语义，等于边界值合法）。
   * 契约来源（唯一映射点）：后端 `src/webui/config_schema.py:389-395` 把 `ge`/`le` 映射成这两个键。
   * ⚠️ 将来后端会补 `exclusiveMinValue`/`exclusiveMaxValue`（← `gt`/`lt`，**不含边界**，
   * 随 12 条约束补丁落地）——届时在此补类型并由 `validateFieldConstraints` 一并消费，
   * 本条 `minValue`/`maxValue` 的含边界语义不变。
   */
  minValue?: number
  maxValue?: number
  /**
   * 字符串长度约束——**含边界**（pydantic `min_length`/`max_length` 语义）。
   * ⚠️ 后端当前只映射 `ge`/`le`（`config_schema.py:389-395` 那一段），**这两个键今天一律不下发**：
   * `minLength` 属 1 段盘出的 12 条约束缺口（`min_length` 5 条），补丁落地后由该映射点产出；
   * `maxLength` 是按同一命名约定对称声明的前向类型（12 条里没有 `max_length`，暂无后端来源）。
   * 前端先按同名前向消费，缺失（`undefined`）时不做任何判定。
   */
  minLength?: number
  maxLength?: number
  /**
   * 正则约束（pydantic `pattern` 语义——**部分匹配**，非整串匹配）。
   * ⚠️ 同 `minLength`：属 12 条缺口里的 `pattern` 1 条，补丁落地后才会下发，今天不下发。
   */
  pattern?: string
  items?: {
    type: string
  }
  properties?: ConfigSchema
  'x-widget'?: XWidgetType
  'x-icon'?: string
  'x-layout'?: 'inline-right'
  'x-input-width'?: string
  'x-description-display'?: DescriptionDisplayMode
  'x-collapsed-by-default'?: boolean
  'x-option-labels'?: Record<string, string>
  'x-option-descriptions'?: Record<string, string>
  'x-placeholder'?: string
  'x-row'?: string
  'x-display-as-section'?: boolean
  'x-textarea-min-height'?: number
  'x-textarea-rows'?: number
  advanced?: boolean
  step?: number
}

export interface ConfigSchema {
  className: string
  classDoc: string
  fields: FieldSchema[]
  nested?: Record<string, ConfigSchema>
  uiParent?: string
  uiLabel?: string
  uiAdvanced?: boolean
  uiOrder?: number
  uiUseSubTabs?: boolean
  uiSubLabel?: string
  uiRootSubLabel?: string
}

export interface ConfigSchemaResponse {
  success: boolean
  schema: ConfigSchema
}

export interface ConfigDataResponse {
  success: boolean
  config: Record<string, unknown>
}

export interface ConfigUpdateResponse {
  success: boolean
  message: string
}
