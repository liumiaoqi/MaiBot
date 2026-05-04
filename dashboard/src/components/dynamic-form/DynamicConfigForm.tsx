import * as React from 'react'
import * as LucideIcons from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { fieldHooks, type FieldHookRegistry } from '@/lib/field-hooks'
import type { ConfigSchema, FieldSchema } from '@/types/config-schema'

import { DynamicField } from './DynamicField'

export interface DynamicConfigFormProps {
  schema: ConfigSchema
  values: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
  basePath?: string
  hooks?: FieldHookRegistry
  /** 嵌套层级：0 = tab 内容层，1 = section 内容层，2+ = 更深嵌套 */
  level?: number
  advancedVisible?: boolean
}

function buildFieldPath(basePath: string, fieldName: string) {
  return basePath ? `${basePath}.${fieldName}` : fieldName
}

function hasTopLevelAdvancedFields(schema: ConfigSchema) {
  return schema.fields.some((field) => field.advanced && !schema.nested?.[field.name])
}

function resolveSectionTitle(schema: ConfigSchema) {
  return schema.uiLabel || schema.classDoc || schema.className
}

function resolveSectionDescription(schema: ConfigSchema, sectionTitle: string) {
  return schema.classDoc && schema.classDoc !== sectionTitle
    ? schema.classDoc
    : undefined
}

function SectionIcon({ iconName }: { iconName?: string }) {
  if (!iconName) return null
  const IconComponent = LucideIcons[iconName as keyof typeof LucideIcons] as
    | React.ComponentType<{ className?: string }>
    | undefined
  if (!IconComponent) return null
  return <IconComponent className="h-5 w-5 text-muted-foreground" />
}

function AdvancedSettingsButton({
  active,
  onClick,
}: {
  active: boolean
  onClick: () => void
}) {
  return (
    <Button
      type="button"
      variant={active ? 'default' : 'outline'}
      size="sm"
      onClick={onClick}
    >
      高级设置
    </Button>
  )
}

function DynamicConfigSection({
  basePath,
  hooks,
  level,
  nestedSchema,
  onChange,
  sectionDescription,
  sectionKey,
  sectionTitle,
  values,
}: {
  basePath: string
  hooks: FieldHookRegistry
  level: number
  nestedSchema: ConfigSchema
  onChange: (field: string, value: unknown) => void
  sectionDescription?: string
  sectionKey: string
  sectionTitle: string
  values: Record<string, unknown>
}) {
  const [advancedVisible, setAdvancedVisible] = React.useState(false)
  const hasAdvanced = hasTopLevelAdvancedFields(nestedSchema)

  return (
    <Card>
      <CardHeader className="pb-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <SectionIcon iconName={nestedSchema.uiIcon} />
              <CardTitle className="text-lg">{sectionTitle}</CardTitle>
            </div>
            {sectionDescription && (
              <CardDescription>{sectionDescription}</CardDescription>
            )}
          </div>
          {hasAdvanced && (
            <AdvancedSettingsButton
              active={advancedVisible}
              onClick={() => setAdvancedVisible((current) => !current)}
            />
          )}
        </div>
      </CardHeader>
      <CardContent>
        <DynamicConfigForm
          schema={nestedSchema}
          values={values}
          onChange={(field, value) => onChange(`${sectionKey}.${field}`, value)}
          basePath={basePath}
          hooks={hooks}
          level={level}
          advancedVisible={hasAdvanced ? advancedVisible : undefined}
        />
      </CardContent>
    </Card>
  )
}

/**
 * DynamicConfigForm - 动态配置表单组件
 *
 * 根据 ConfigSchema 渲染表单字段，支持：
 * 1. Hook 系统：通过 FieldHookRegistry 自定义字段渲染
 *    - replace 模式：完全替换默认渲染
 *    - wrapper 模式：包装默认渲染（通过 children 传递）
 * 2. 嵌套 schema：递归渲染 schema.nested 中的子配置
 * 3. 高级设置：由栏目标题右侧按钮控制显示
 */
export const DynamicConfigForm: React.FC<DynamicConfigFormProps> = ({
  schema,
  values,
  onChange,
  basePath = '',
  hooks = fieldHooks,
  level = 0,
  advancedVisible,
}) => {
  const [localAdvancedVisible, setLocalAdvancedVisible] = React.useState(false)
  const resolvedAdvancedVisible = advancedVisible ?? localAdvancedVisible

  const fieldMap = React.useMemo(
    () => new Map(schema.fields.map((field) => [field.name, field])),
    [schema.fields],
  )

  const renderField = (field: FieldSchema) => {
    const fieldPath = buildFieldPath(basePath, field.name)

    if (hooks.has(fieldPath)) {
      const hookEntry = hooks.get(fieldPath)
      if (!hookEntry) return null

      const HookComponent = hookEntry.component

      if (hookEntry.type === 'replace') {
        return (
          <HookComponent
            fieldPath={fieldPath}
            value={values[field.name]}
            onChange={(v) => onChange(field.name, v)}
            schema={field}
          />
        )
      }

      return (
        <HookComponent
          fieldPath={fieldPath}
          value={values[field.name]}
          onChange={(v) => onChange(field.name, v)}
          schema={field}
        >
          <DynamicField
            schema={field}
            value={values[field.name]}
            onChange={(v) => onChange(field.name, v)}
            fieldPath={fieldPath}
          />
        </HookComponent>
      )
    }

    return (
      <DynamicField
        schema={field}
        value={values[field.name]}
        onChange={(v) => onChange(field.name, v)}
        fieldPath={fieldPath}
      />
    )
  }

  const topLevelFields = schema.fields.filter(
    (field) => !schema.nested?.[field.name],
  )
  const normalFields = topLevelFields.filter((field) => !field.advanced)
  const advancedFields = topLevelFields.filter((field) => field.advanced)
  const visibleFields = resolvedAdvancedVisible
    ? [...normalFields, ...advancedFields]
    : normalFields

  const groupFieldsByRow = (fields: FieldSchema[]) => {
    const rows: FieldSchema[][] = []
    let currentRow: FieldSchema[] = []
    let currentRowKey: string | undefined

    for (const field of fields) {
      const rowKey = field['x-row']
      if (rowKey && rowKey === currentRowKey) {
        currentRow.push(field)
        continue
      }

      if (currentRow.length > 0) {
        rows.push(currentRow)
      }

      currentRow = [field]
      currentRowKey = rowKey
    }

    if (currentRow.length > 0) {
      rows.push(currentRow)
    }

    return rows
  }

  const renderFieldList = (fields: FieldSchema[]) => (
    <>
      {groupFieldsByRow(fields).map((row, index) => (
        <React.Fragment key={row.map((field) => field.name).join('|')}>
          {index > 0 && <Separator className="my-2 bg-border/50" />}
          {row.length > 1 ? (
            <div
              className="grid gap-4 py-1 md:grid-cols-[repeat(var(--field-row-count),minmax(0,1fr))]"
              style={{ '--field-row-count': row.length } as React.CSSProperties}
            >
              {row.map((field) => (
                <div key={field.name}>{renderField(field)}</div>
              ))}
            </div>
          ) : (
            <div className="py-1">{renderField(row[0])}</div>
          )}
        </React.Fragment>
      ))}
    </>
  )

  return (
    <div className="space-y-6">
      {topLevelFields.length > 0 && (
        <div>
          {advancedVisible === undefined && advancedFields.length > 0 && (
            <div className="flex justify-end pb-2">
              <AdvancedSettingsButton
                active={localAdvancedVisible}
                onClick={() => setLocalAdvancedVisible((current) => !current)}
              />
            </div>
          )}
          {renderFieldList(visibleFields)}
        </div>
      )}

      {schema.nested &&
        Object.entries(schema.nested)
          .map(([key, nestedSchema]) => {
          const nestedField = fieldMap.get(key)
          const nestedFieldPath = buildFieldPath(basePath, key)

          if (hooks.has(nestedFieldPath)) {
            const hookEntry = hooks.get(nestedFieldPath)
            if (!hookEntry) return null

            const HookComponent = hookEntry.component
            if (hookEntry.type === 'replace') {
              return (
                <div key={key}>
                  <HookComponent
                    fieldPath={nestedFieldPath}
                    value={values[key]}
                    onChange={(v) => onChange(key, v)}
                    schema={nestedField ?? nestedSchema}
                    nestedSchema={nestedSchema}
                  />
                </div>
              )
            }

            return (
              <div key={key}>
                <HookComponent
                  fieldPath={nestedFieldPath}
                  value={values[key]}
                  onChange={(v) => onChange(key, v)}
                  schema={nestedField ?? nestedSchema}
                  nestedSchema={nestedSchema}
                >
                  <DynamicConfigForm
                    schema={nestedSchema}
                    values={(values[key] as Record<string, unknown>) || {}}
                    onChange={(field, value) => onChange(`${key}.${field}`, value)}
                    basePath={nestedFieldPath}
                    hooks={hooks}
                    level={level + 1}
                  />
                </HookComponent>
              </div>
            )
          }

          const sectionTitle = resolveSectionTitle(nestedSchema)
          const sectionDescription = resolveSectionDescription(nestedSchema, sectionTitle)

          if (level === 0) {
            return (
              <DynamicConfigSection
                key={key}
                nestedSchema={nestedSchema}
                values={(values[key] as Record<string, unknown>) || {}}
                onChange={onChange}
                basePath={nestedFieldPath}
                hooks={hooks}
                level={level + 1}
                sectionKey={key}
                sectionTitle={sectionTitle}
                sectionDescription={sectionDescription}
              />
            )
          }

          return (
            <Card key={key} className="border-border/70 bg-muted/20 shadow-none">
              <CardHeader className="px-4 py-3">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <SectionIcon iconName={nestedSchema.uiIcon} />
                      <CardTitle className="text-sm">{sectionTitle}</CardTitle>
                    </div>
                    {sectionDescription && (
                      <CardDescription className="text-xs">
                        {sectionDescription}
                      </CardDescription>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="px-4 pb-4 pt-0">
                <DynamicConfigForm
                  schema={nestedSchema}
                  values={(values[key] as Record<string, unknown>) || {}}
                  onChange={(field, value) => onChange(`${key}.${field}`, value)}
                  basePath={nestedFieldPath}
                  hooks={hooks}
                  level={level + 1}
                />
              </CardContent>
            </Card>
          )
        })}
    </div>
  )
}
