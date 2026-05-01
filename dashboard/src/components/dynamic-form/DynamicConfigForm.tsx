import * as React from 'react'
import * as LucideIcons from 'lucide-react'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import type { ConfigSchema, FieldSchema } from '@/types/config-schema'
import { fieldHooks, type FieldHookRegistry } from '@/lib/field-hooks'

import { DynamicField } from './DynamicField'

export interface DynamicConfigFormProps {
  schema: ConfigSchema
  values: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
  basePath?: string
  hooks?: FieldHookRegistry
  /** 嵌套层级：0 = tab 内容层, 1 = section 内容层, 2+ = 更深嵌套 */
  level?: number
}

/**
 * DynamicConfigForm - 动态配置表单组件
 * 
 * 根据 ConfigSchema 渲染表单字段，支持：
 * 1. Hook 系统：通过 FieldHookRegistry 自定义字段渲染
 *    - replace 模式：完全替换默认渲染
 *    - wrapper 模式：包装默认渲染（通过 children 传递）
 * 2. 嵌套 schema：递归渲染 schema.nested 中的子配置，使用 Card 容器区分层级
 * 3. 默认渲染：使用 DynamicField 组件
 */
export const DynamicConfigForm: React.FC<DynamicConfigFormProps> = ({
  schema,
  values,
  onChange,
  basePath = '',
  hooks = fieldHooks, // 默认使用全局单例
  level = 0,
}) => {
  const fieldMap = React.useMemo(
    () => new Map(schema.fields.map((field) => [field.name, field])),
    [schema.fields]
  )

  const buildFieldPath = (fieldName: string) => {
    return basePath ? `${basePath}.${fieldName}` : fieldName
  }

  /**
   * 渲染单个字段
   * 检查是否有注册的 Hook，根据 Hook 类型选择渲染方式
   */
  const renderField = (field: FieldSchema) => {
    const fieldPath = buildFieldPath(field.name)

    // 检查是否有注册的 Hook
    if (hooks.has(fieldPath)) {
      const hookEntry = hooks.get(fieldPath)
      if (!hookEntry) return null // Type guard（理论上不会发生）

      const HookComponent = hookEntry.component

      if (hookEntry.type === 'replace') {
        // replace 模式：完全替换默认渲染
        return (
          <HookComponent
            fieldPath={fieldPath}
            value={values[field.name]}
            onChange={(v) => onChange(field.name, v)}
            schema={field}
          />
        )
      } else {
        // wrapper 模式：包装默认渲染
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
    }

    // 无 Hook，使用默认渲染
    return (
      <DynamicField
        schema={field}
        value={values[field.name]}
        onChange={(v) => onChange(field.name, v)}
        fieldPath={fieldPath}
      />
    )
  }

  /** 渲染 section 图标 */
  const renderSectionIcon = (iconName?: string) => {
    if (!iconName) return null
    const IconComponent = LucideIcons[iconName as keyof typeof LucideIcons] as
      | React.ComponentType<{ className?: string }>
      | undefined
    if (!IconComponent) return null
    return <IconComponent className="h-5 w-5 text-muted-foreground" />
  }

  // 过滤出不属于 nested 的顶层字段
  const topLevelFields = schema.fields.filter(
    (field) => !schema.nested?.[field.name]
  )

  return (
    <div className="space-y-6">
      {/* 渲染顶层字段 */}
      {topLevelFields.length > 0 && (
        <div className="space-y-1">
          {topLevelFields.map((field, index) => (
            <React.Fragment key={field.name}>
              {index > 0 && field.type !== 'boolean' && topLevelFields[index - 1]?.type !== 'boolean' && (
                <Separator className="my-1" />
              )}
              <div>{renderField(field)}</div>
            </React.Fragment>
          ))}
        </div>
      )}

      {/* 渲染嵌套 schema */}
      {schema.nested &&
        Object.entries(schema.nested).map(([key, nestedSchema]) => {
          const nestedField = fieldMap.get(key)
          const nestedFieldPath = buildFieldPath(key)

          // Hook 系统处理
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

          const sectionTitle =
            nestedSchema.uiLabel || nestedSchema.classDoc || nestedSchema.className
          const sectionDescription =
            nestedSchema.classDoc && nestedSchema.classDoc !== sectionTitle
              ? nestedSchema.classDoc
              : undefined

          // 一级嵌套：使用 Card 包裹，清晰的 section 边界
          if (level === 0) {
            return (
              <Card key={key}>
                <CardHeader className="pb-4">
                  <div className="flex items-center gap-2">
                    {renderSectionIcon(nestedSchema.uiIcon)}
                    <CardTitle className="text-lg">{sectionTitle}</CardTitle>
                  </div>
                  {sectionDescription && (
                    <CardDescription>{sectionDescription}</CardDescription>
                  )}
                </CardHeader>
                <CardContent>
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
          }

          // 二级及更深嵌套：使用左侧指示条 + 轻量分组
          return (
            <div
              key={key}
              className="relative space-y-4 rounded-lg border-l-2 border-muted-foreground/20 pl-4 pt-1 pb-1"
            >
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  {renderSectionIcon(nestedSchema.uiIcon)}
                  <h4 className="text-sm font-semibold">{sectionTitle}</h4>
                </div>
                {sectionDescription && (
                  <p className="text-xs text-muted-foreground">
                    {sectionDescription}
                  </p>
                )}
              </div>

              <DynamicConfigForm
                schema={nestedSchema}
                values={(values[key] as Record<string, unknown>) || {}}
                onChange={(field, value) => onChange(`${key}.${field}`, value)}
                basePath={nestedFieldPath}
                hooks={hooks}
                level={level + 1}
              />
            </div>
          )
        })}
    </div>
  )
}
