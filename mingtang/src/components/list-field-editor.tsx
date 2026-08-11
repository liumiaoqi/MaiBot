/**
 * ListFieldEditor —— 列表字段编辑占位组件。
 *
 * 维持 field-renderer 中调用方 props 契约：受控 value (unknown[]) + onChange 回调，
 * 支持可选 itemType/itemFields/minItems/maxItems/disabled/placeholder。
 * 本占位实现以换行分隔的 textarea 呈现，编辑时按行拆分回传 string[]。
 */
import type { ItemFieldDefinition } from '@/lib/plugin-api'

interface ListFieldEditorProps {
  value: unknown[]
  onChange: (value: unknown[]) => void
  itemType?: string
  itemFields?: Record<string, ItemFieldDefinition>
  minItems?: number
  maxItems?: number
  disabled?: boolean
  placeholder?: string
  className?: string
}

export function ListFieldEditor({
  value,
  onChange,
  disabled,
  placeholder,
  className,
}: ListFieldEditorProps) {
  const text = value.map((item) => String(item ?? '')).join('\n')

  return (
    <textarea
      value={text}
      onChange={(event) => onChange(event.target.value.split('\n'))}
      disabled={disabled}
      placeholder={placeholder}
      className={className}
      rows={4}
    />
  )
}