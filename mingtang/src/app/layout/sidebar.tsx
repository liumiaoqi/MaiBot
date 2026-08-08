import { useState } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import { menuSections } from './menu-sections'

/** 图标名称 → SVG 渲染（简化版——R1-3-11 shadcn/ui 后可增强） */
function MenuIcon({ name, className }: { name: string; className?: string }) {
  return (
    <span
      className={cn('inline-block h-5 w-5 shrink-0', className)}
      data-icon={name}
      aria-hidden="true"
    />
  )
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const [collapsed] = useState(false)

  return (
    <aside
      data-dashboard-sidebar="true"
      className="flex h-full w-[var(--layout-sidebar-width,240px)] flex-col border-r border-border bg-card"
    >
      {/* Logo 区域 */}
      <div className="flex h-14 items-center border-b border-border px-4">
        <span className="text-lg font-bold text-foreground">MaiBot</span>
      </div>

      {/* 导航区 */}
      <nav className="flex-1 overflow-y-auto p-2" aria-label={t('a11y.sidebarNav')}>
        <ul className="flex flex-col gap-4">
          {menuSections.map((section) => (
            <li key={section.title}>
              {/* 分区标题 */}
              <h3
                className={cn(
                  'mb-2 px-3 text-sm font-semibold tracking-wider text-muted-foreground/60 uppercase',
                  section.title === 'sidebar.groups.overview' && 'sr-only'
                )}
              >
                {t(section.title)}
              </h3>

              {/* 菜单项 */}
              <ul className="flex flex-col gap-1">
                {section.items.map((item) => {
                  if (!item.path) return null
                  const isActive = pathname === item.path
                  return (
                    <li key={item.path}>
                      <button
                        onClick={() => {
                          navigate({ to: item.path! })
                          onNavigate?.()
                        }}
                        title={t(item.label)}
                        className={cn(
                          'flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors',
                          isActive
                            ? 'bg-accent text-accent-foreground font-medium'
                            : 'text-foreground hover:bg-accent/50'
                        )}
                      >
                        <MenuIcon name={item.icon} />
                        {!collapsed && (
                          <span className="truncate">{t(item.label)}</span>
                        )}
                      </button>
                    </li>
                  )
                })}
              </ul>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  )
}