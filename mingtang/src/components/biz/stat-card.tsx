import * as React from 'react'

import { cn } from '@/lib/utils'

/** StatCard 属性 */
export interface StatCardProps {
  /** 标题 */
  title: string
  /** 数值 */
  value: React.ReactNode
  /** 单位 */
  unit?: string
  /** 描述 */
  description?: string
  /** 趋势（正数=上升，负数=下降） */
  trend?: number
  /** 图标 */
  icon?: React.ReactNode
  /** 自定义类名 */
  className?: string
}

/** 状态卡片——监控 / 统计页统一 */
export function StatCard({
  title,
  value,
  unit,
  description,
  trend,
  icon,
  className,
}: StatCardProps) {
  return (
    <div
      className={cn(
        'rounded-lg border border-border bg-card p-4 shadow-sm',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-muted-foreground">{title}</span>
        {icon && <span className="text-muted-foreground">{icon}</span>}
      </div>
      <div className="mt-2 flex items-baseline gap-1">
        <span className="text-2xl font-bold text-foreground">{value}</span>
        {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
      </div>
      {(description || trend !== undefined) && (
        <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
          {trend !== undefined && (
            <span
              className={cn(
                'inline-flex items-center gap-0.5 font-medium',
                trend > 0 && 'text-green-600',
                trend < 0 && 'text-red-600'
              )}
            >
              {trend > 0 ? '↑' : trend < 0 ? '↓' : '—'}
              {Math.abs(trend)}%
            </span>
          )}
          {description && <span>{description}</span>}
        </div>
      )}
    </div>
  )
}