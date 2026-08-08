import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'

interface TopbarProps {
  onMenuClick: () => void
  onSearchOpen: () => void
}

export function Topbar({ onMenuClick, onSearchOpen }: TopbarProps) {
  const { t } = useTranslation()

  return (
    <header
      data-dashboard-topbar="true"
      className="flex h-14 shrink-0 items-center justify-between border-b border-border bg-background px-4"
    >
      {/* 移动端侧边栏唤出按钮（lg 以上隐藏） */}
      <button
        onClick={onMenuClick}
        className="mr-2 rounded-md p-2 text-foreground transition-colors hover:bg-accent/50 lg:hidden"
        aria-label="打开菜单"
      >
        <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* 搜索框入口 */}
      <button
        onClick={onSearchOpen}
        className={cn(
          'flex items-center gap-2 rounded-md border border-border px-3 py-1.5',
          'text-sm text-muted-foreground transition-colors hover:bg-accent/50',
          'w-full max-w-md'
        )}
      >
        <svg
          className="h-4 w-4 shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <span>{t('search.placeholder')}</span>
        <kbd className="ml-auto rounded border border-border px-1.5 py-0.5 text-xs">⌘K</kbd>
      </button>

      {/* 右侧操作区（R2+ 扩展） */}
      <div className="flex items-center gap-2">
        {/* 主题切换、语言切换等在 R2+ 添加 */}
      </div>
    </header>
  )
}