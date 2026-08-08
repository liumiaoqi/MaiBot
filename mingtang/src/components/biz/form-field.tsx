import * as React from 'react'

import { cn } from '@/lib/utils'
import { Label } from '@/components/ui/label'

/** FormField 属性 */
export interface FormFieldProps {
  /** 字段标识 */
  name: string
  /** 标签文本 */
  label: string
  /** 提示文本 */
  hint?: string
  /** 错误文本 */
  error?: string
  /** 是否必填 */
  required?: boolean
  /** 是否高级选项 */
  advanced?: boolean
  /** 子元素（输入控件） */
  children: React.ReactNode
  /** 自定义类名 */
  className?: string
}

/** 表单字段封装——与 DynamicConfigForm 衔接 */
export function FormField({
  name,
  label,
  hint,
  error,
  required,
  advanced,
  children,
  className,
}: FormFieldProps) {
  return (
    <div className={cn('flex flex-col gap-1.5', className)} data-field-name={name}>
      <div className="flex items-center gap-1">
        <Label htmlFor={name}>
          {label}
          {required && <span className="text-destructive">*</span>}
          {advanced && (
            <span className="ml-1 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
              高级
            </span>
          )}
        </Label>
      </div>
      {children}
      {error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  )
}