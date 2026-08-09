import { useState, useEffect } from 'react'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'
import { PanelLeftClose, PanelLeftOpen } from 'lucide-react'

import { cn } from '@/lib/utils'
import { menuSections } from './menu-sections'

const COLLAPSE_KEY = 'maibot-sidebar-collapsed'

import { Home, Bot, Smile, Heart, Users, Activity, Monitor, Settings, Type, Sparkles, BookOpen, Package, Plug, Server, Palette, MessageSquare, Brain, Languages, Cpu, CircleDot } from 'lucide-react'

/** 菜单图标名 → lucide 组件映射（menu-sections 的 icon 名） */
const ICON_MAP: Record<string, typeof Home> = {
  home: Home,
  agent: Bot,
  'bot-config': Settings,
  'chat-management': MessageSquare,
  deepseek: Brain,
  emoji: Smile,
  emotion: Heart,
  expression: Sparkles,
  jargon: Languages,
  knowledge: BookOpen,
  mcp: Plug,
  model: Cpu,
  monitor: Activity,
  palette: Palette,
  'plugin-config': Server,
  'plugin-market': Package,
  prompt: Type,
  relationship: Users,
  subagent: CircleDot,
  system: Monitor,
  behavior: Brain,
}

function MenuIcon({ name, className }: { name: string; className?: string }) {
  const Icon = ICON_MAP[name] ?? CircleDot
  return <Icon className={cn('h-5 w-5 shrink-0', className)} data-icon={name} aria-hidden="true" />
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const pathname = useRouterState({ select: (s) => s.location.pathname })
  const [collapsed, setCollapsed] = useState(false)

  // 从 localStorage 恢复收起状态
  useEffect(() => {
    const stored = localStorage.getItem(COLLAPSE_KEY)
    if (stored === 'true') setCollapsed(true)
  }, [])

  const toggleCollapsed = () => {
    const next = !collapsed
    setCollapsed(next)
    localStorage.setItem(COLLAPSE_KEY, String(next))
  }

  return (
    <aside
      data-dashboard-sidebar="true"
      data-collapsed={collapsed}
      className={cn(
        'flex h-full flex-col border-r border-border bg-card transition-all duration-200',
        collapsed ? 'w-16' : 'w-[var(--layout-sidebar-width,240px)]'
      )}
    >
      {/* Logo 区域 + 收起按钮 */}
      <div className="flex h-14 items-center border-b border-border px-4">
        {!collapsed && <span className="text-lg font-bold text-foreground">MaiBot</span>}
        <button
          onClick={toggleCollapsed}
          className={cn(
            'hidden lg:block rounded-md p-1.5 text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors',
            collapsed ? 'mx-auto' : 'ml-auto'
          )}
          aria-label={collapsed ? '展开侧边栏' : '收起侧边栏'}
          data-testid="sidebar-collapse-toggle"
        >
          {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </button>
      </div>

      {/* 导航区 */}
      <nav className="flex-1 overflow-y-auto p-2" aria-label={t('a11y.sidebarNav')}>
        <ul className="flex flex-col gap-4">
          {menuSections.map((section) => (
            <li key={section.title}>
              {/* 分区标题（收起时隐藏） */}
              {!collapsed && (
                <h3
                  className={cn(
                    'mb-2 px-3 text-sm font-semibold tracking-wider text-muted-foreground/60 uppercase',
                    section.title === 'sidebar.groups.overview' && 'sr-only'
                  )}
                >
                  {t(section.title)}
                </h3>
              )}

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
                          'flex w-full items-center rounded-md text-left text-sm transition-colors',
                          collapsed ? 'justify-center px-0 py-2' : 'gap-3 px-3 py-2',
                          isActive
                            ? 'bg-primary text-primary-foreground font-medium'
                            : 'text-foreground hover:bg-accent/50'
                        )}
                        data-testid={`sidebar-item-${item.path}`}
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
