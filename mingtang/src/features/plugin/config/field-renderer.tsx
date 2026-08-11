/**
 * field-renderer —— schema 驱动的字段/分区渲染（纯展示组件，无 effect）。
 *
 * 包含：
 * - i18n 工具函数 getLocaleCandidates / resolveLocalizedText / localizeItemFields
 *   （导出供 index.tsx 的 PluginConfigEditor 复用）；
 * - FieldRenderer：按 ui_type switch 渲染 switch/number/slider/select/textarea/
 *   password/list/text 等控件；
 * - SectionRenderer：按 schema.sections 折叠卡片渲染字段网格。
 */
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/button'
import { DraftNumberInput } from '@/components/ui/draft-number-input'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Textarea } from '@/components/ui/textarea'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ListFieldEditor } from '@/components/list-field-editor'
import { MultiSelect } from '@/components/ui/multi-select'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ChevronRight, ChevronDown, Eye, EyeOff } from 'lucide-react'
import type {
  ConfigFieldSchema,
  ConfigSectionSchema,
  ItemFieldDefinition,
} from '@/lib/plugin-api'

import { getNestedRecord } from './utils'

// ---- i18n 工具函数 ----

export function getLocaleCandidates(language: string): string[] {
  const normalized = (language || 'zh').replace('-', '_')
  const base = normalized.split('_')[0]
  const candidates = [language, normalized, base]

  if (base === 'zh') candidates.push('zh_CN', 'zh-CN')
  if (base === 'en') candidates.push('en_US', 'en-US')
  if (base === 'ja') candidates.push('ja_JP', 'ja-JP')
  if (base === 'ko') candidates.push('ko_KR', 'ko-KR')

  candidates.push('zh_CN', 'zh-CN', 'zh')
  return Array.from(new Set(candidates.filter(Boolean)))
}

export function resolveLocalizedText(
  value: unknown,
  language: string,
  fallback = '',
  i18n?: Record<string, Record<string, string>>,
  key?: string
): string {
  const candidates = getLocaleCandidates(language)

  if (i18n && key) {
    for (const locale of candidates) {
      const localized = i18n[locale]?.[key]
      if (typeof localized === 'string' && localized.trim()) {
        return localized
      }
    }
  }

  if (typeof value === 'string') {
    return value || fallback
  }

  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const localizedMap = value as Record<string, unknown>
    for (const locale of candidates) {
      const localized = localizedMap[locale]
      if (typeof localized === 'string' && localized.trim()) {
        return localized
      }
    }
  }

  return fallback
}

function localizeItemFields(
  itemFields: Record<string, ItemFieldDefinition> | undefined,
  language: string
): Record<string, ItemFieldDefinition> | undefined {
  if (!itemFields) return undefined

  return Object.fromEntries(
    Object.entries(itemFields).map(([fieldName, field]) => [
      fieldName,
      {
        ...field,
        label: resolveLocalizedText(field.label, language, fieldName, field.i18n, 'label'),
        placeholder:
          resolveLocalizedText(field.placeholder, language, '', field.i18n, 'placeholder') ||
          undefined,
      },
    ])
  )
}

// ---- FieldRenderer ----

interface FieldRendererProps {
  field: ConfigFieldSchema
  value: unknown
  onChange: (value: unknown) => void
  sectionName: string
}

function FieldRenderer({ field, value, onChange }: FieldRendererProps) {
  const [showPassword, setShowPassword] = useState(false)
  const { i18n } = useTranslation()
  const language = i18n.resolvedLanguage || i18n.language || 'zh'
  const label = resolveLocalizedText(field.label, language, field.name, field.i18n, 'label')
  const hint = resolveLocalizedText(field.hint, language, '', field.i18n, 'hint')
  const placeholder = resolveLocalizedText(
    field.placeholder,
    language,
    '',
    field.i18n,
    'placeholder'
  )
  const localizedItemFields = localizeItemFields(field.item_fields, language)

  // 根据 ui_type 渲染不同的控件
  switch (field.ui_type) {
    case 'switch':
      return (
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <Label>{label}</Label>
            {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
          </div>
          <Switch
            checked={Boolean(value ?? field.default)}
            onCheckedChange={onChange}
            disabled={field.disabled}
          />
        </div>
      )

    case 'number':
      return (
        <div className="space-y-2">
          <Label>{label}</Label>
          <DraftNumberInput
            value={value}
            defaultValue={field.default}
            onValueChange={onChange}
            min={field.min}
            max={field.max}
            step={field.step ?? 1}
            placeholder={placeholder}
            disabled={field.disabled}
          />
          {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
        </div>
      )

    case 'slider':
      return (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>{label}</Label>
            <span className="text-muted-foreground text-sm">
              {(value as number) ?? field.default}
            </span>
          </div>
          <Slider
            value={[(value as number) ?? (field.default as number)]}
            onValueChange={(v) => onChange(v[0])}
            min={field.min ?? 0}
            max={field.max ?? 100}
            step={field.step ?? 1}
            disabled={field.disabled}
          />
          {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
        </div>
      )

    case 'select':
      if (field.multiple) {
        const selectedValues = Array.isArray(value)
          ? value.map(v => String(v))
          : Array.isArray(field.default)
            ? field.default.map(v => String(v))
            : []

        return (
          <div className="space-y-2">
            <Label>{label}</Label>
            <MultiSelect
              options={(field.choices ?? []).map((choice) => ({
                label: String(choice),
                value: String(choice),
              }))}
              selected={selectedValues}
              onChange={onChange}
              placeholder={placeholder || '请选择'}
              disabled={field.disabled}
            />
            {hint && (
              <p className="text-xs text-muted-foreground">{hint}</p>
            )}
          </div>
        )
      }

      return (
        <div className="space-y-2">
          <Label>{label}</Label>
          <Select
            value={String(value ?? field.default)}
            onValueChange={onChange}
            disabled={field.disabled}
          >
            <SelectTrigger>
              <SelectValue placeholder={placeholder || '请选择'} />
            </SelectTrigger>
            <SelectContent>
              {field.choices?.map((choice) => (
                <SelectItem key={String(choice)} value={String(choice)}>
                  {String(choice)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
        </div>
      )

    case 'textarea':
      return (
        <div className="space-y-2">
          <Label>{label}</Label>
          <Textarea
            value={(value as string) ?? field.default}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            rows={field.rows ?? 3}
            disabled={field.disabled}
          />
          {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
        </div>
      )

    case 'password':
      return (
        <div className="space-y-2">
          <Label>{label}</Label>
          <div className="relative">
            <Input
              type={showPassword ? 'text' : 'password'}
              value={(value as string) ?? ''}
              onChange={(e) => onChange(e.target.value)}
              placeholder={placeholder}
              disabled={field.disabled}
              className="pr-10"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute top-0 right-0 h-full px-3"
              onClick={() => setShowPassword(!showPassword)}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
          </div>
          {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
        </div>
      )

    case 'list':
      return (
        <div className="space-y-2">
          <Label>{label}</Label>
          <ListFieldEditor
            value={Array.isArray(value) ? value : Array.isArray(field.default) ? field.default : []}
            onChange={(newValue: unknown[]) => onChange(newValue)}
            itemType={field.item_type ?? 'string'}
            itemFields={localizedItemFields}
            minItems={field.min_items}
            maxItems={field.max_items}
            disabled={field.disabled}
            placeholder={placeholder}
          />
          {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
        </div>
      )

    case 'text':
    default:
      return (
        <div className="space-y-2">
          <Label>{label}</Label>
          <Input
            type="text"
            value={(value as string) ?? field.default ?? ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            maxLength={field.max_length}
            disabled={field.disabled}
          />
          {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
        </div>
      )
  }
}

// ---- SectionRenderer ----

interface SectionRendererProps {
  sectionName: string
  section: ConfigSectionSchema
  config: Record<string, unknown>
  onChange: (sectionName: string, fieldName: string, value: unknown) => void
}

function getFieldGridClassName(field: ConfigFieldSchema): string {
  if (field.ui_type === 'textarea' || field.ui_type === 'list' || field.ui_type === 'slider') {
    return 'lg:col-span-2'
  }

  return 'min-w-0'
}

export function SectionRenderer({ sectionName, section, config, onChange }: SectionRendererProps) {
  const [isOpen, setIsOpen] = useState(!section.collapsed)
  const { i18n } = useTranslation()
  const language = i18n.resolvedLanguage || i18n.language || 'zh'
  const resolvedSectionName = section.name || sectionName
  const sectionConfig = getNestedRecord(config, resolvedSectionName)
  const title = resolveLocalizedText(section.title, language, sectionName, section.i18n, 'title')
  const description = resolveLocalizedText(
    section.description,
    language,
    '',
    section.i18n,
    'description'
  )

  // 按 order 排序字段
  const sortedFields = Object.entries(section.fields)
    .filter(([, field]) => !field.hidden)
    .sort(([, a], [, b]) => (a.order ?? 0) - (b.order ?? 0))

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <Card>
        <CollapsibleTrigger asChild>
          <CardHeader className="hover:bg-muted/50 cursor-pointer gap-0.5 px-4! py-2! transition-colors sm:px-4! sm:py-2!">
            <div className="flex items-center">
              <div className="flex min-w-0 items-center gap-2">
                {isOpen ? (
                  <ChevronDown className="text-muted-foreground h-4 w-4" />
                ) : (
                  <ChevronRight className="text-muted-foreground h-4 w-4" />
                )}
                <CardTitle className="min-w-0 truncate text-base">{title}</CardTitle>
              </div>
            </div>
            {description && <CardDescription className="ml-6 text-xs leading-tight">{description}</CardDescription>}
          </CardHeader>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <CardContent className="grid grid-cols-1 gap-4 pt-0 lg:grid-cols-2">
            {sortedFields.map(([fieldName, field]) => (
              <div key={fieldName} className={getFieldGridClassName(field)}>
                <FieldRenderer
                  field={field}
                  value={sectionConfig?.[fieldName]}
                  onChange={(value) => onChange(resolvedSectionName, fieldName, value)}
                  sectionName={resolvedSectionName}
                />
              </div>
            ))}
          </CardContent>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}