/**
 * schema-field —— 按 ModeFieldSchema 渲染单个表单字段（HA config flow 的通用渲染器）。
 *
 * 覆盖 text / number / datetime / select / checkbox 五类：
 * - label/description/placeholder/options 全部来自 schema 声明；
 * - 动态 min/max（依赖 settings 的并发上限等）由调用方通过 props 覆盖；
 * - checkbox 带说明文案时与旧版一致展示在下方。
 */
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'

import type { ImportFieldValue, ModeFieldSchema } from '../../import-mode-schemas'

export interface SchemaFieldProps {
  field: ModeFieldSchema
  value: ImportFieldValue
  onChange: (value: ImportFieldValue) => void
  /** 覆盖 schema 的 min/max（动态值，如依赖 settings 的分块上限、maibot 时间/ID 交叉约束——datetime 用字符串） */
  min?: number | string
  max?: number | string
  /** 覆盖 schema 的 placeholder */
  placeholder?: string
  /** 覆盖 schema 的 description（如高级参数里带「默认 X」动态前缀的说明） */
  description?: string
  /** 原生 id（用于 Label htmlFor 无障碍关联） */
  id?: string
  required?: boolean
}

export function SchemaField({
  field,
  value,
  onChange,
  min,
  max,
  placeholder,
  description,
  id,
  required,
}: SchemaFieldProps) {
  if (field.type === 'checkbox') {
    return (
      <div className="flex items-center gap-2 text-sm">
        <Checkbox checked={Boolean(value)} onCheckedChange={(checked) => onChange(Boolean(checked))} />
        <span className="font-medium leading-tight">{field.label}</span>
        {field.description ? (
          <span className="pl-1 text-[11px] leading-snug text-muted-foreground">{field.description}</span>
        ) : null}
      </div>
    )
  }

  if (field.type === 'select') {
    return (
      <div className="space-y-1">
        <Label htmlFor={id}>{field.label}</Label>
        <Select value={String(value)} onValueChange={(next) => onChange(next)}>
          <SelectTrigger aria-label={`${field.key}-input`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(field.options ?? []).map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {(description ?? field.description) ? (
          <div className="text-[11px] leading-snug text-muted-foreground">{description ?? field.description}</div>
        ) : null}
      </div>
    )
  }

  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{field.label}</Label>
      {field.multiline ? (
        <Textarea
          id={id}
          value={String(value ?? '')}
          onChange={(event) => onChange(event.target.value)}
          rows={8}
        />
      ) : (
        <Input
          id={id}
          type={field.type === 'number' ? 'number' : field.type === 'datetime' ? 'datetime-local' : 'text'}
          min={min ?? field.min}
          max={max ?? field.max}
          step={field.type === 'number' || field.type === 'datetime' ? 1 : undefined}
          required={required}
          value={String(value ?? '')}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder ?? field.placeholder}
        />
      )}
      {(description ?? field.description) ? (
        <div className="text-[11px] leading-snug text-muted-foreground">{description ?? field.description}</div>
      ) : null}
    </div>
  )
}
