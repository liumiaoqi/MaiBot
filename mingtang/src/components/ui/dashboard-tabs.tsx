/**
 * DashboardTabs 统计 Tabs 网格布局（R4-1-2-3）
 *
 * 从 dashboard 行为等价搬移——DashboardTabBar/DashboardTabTrigger 基于 tabs + grid 布局
 * 主题适配：沿用 tabs 组件主题（ADR-5 零黑字）
 *
 * design.md §3.8.3
 */
import type { ComponentPropsWithoutRef } from 'react'

import { TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'

type DashboardTabBarVariant = 'grid' | 'scroll'

const dashboardTabBarClassName = (variant: DashboardTabBarVariant) =>
  cn(
    'h-auto gap-1 px-1 py-1.5 transition-all duration-300 ease-out',
    variant === 'grid'
      ? 'grid w-full'
      : 'flex w-max min-w-full flex-nowrap items-center justify-start sm:w-full'
  )

const dashboardTabTriggerClassName = (className?: string) =>
  cn(
    'shrink-0 px-2 py-1.5 text-sm transition-all duration-200 ease-out sm:px-3 sm:py-2 data-[state=active]:shadow-sm',
    className
  )

interface DashboardTabBarProps extends ComponentPropsWithoutRef<typeof TabsList> {
  variant?: DashboardTabBarVariant
  wrapperClassName?: string
}

function DashboardTabBar({
  className,
  children,
  variant = 'scroll',
  wrapperClassName,
  ...props
}: DashboardTabBarProps) {
  const list = (
    <TabsList
      className={cn(dashboardTabBarClassName(variant), className)}
      {...props}
    >
      {children}
    </TabsList>
  )

  if (variant === 'grid') {
    return list
  }

  return (
    <div
      data-dashboard-tab-scroll="true"
      className={cn(
        '-mx-4 overflow-x-auto px-4 pb-1 sm:mx-0 sm:overflow-x-visible sm:px-0 sm:pb-0',
        wrapperClassName
      )}
    >
      {list}
    </div>
  )
}

function DashboardTabTrigger({
  className,
  ...props
}: ComponentPropsWithoutRef<typeof TabsTrigger>) {
  return (
    <TabsTrigger
      className={dashboardTabTriggerClassName(className)}
      {...props}
    />
  )
}

export { DashboardTabBar, DashboardTabTrigger }