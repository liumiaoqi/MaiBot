import { useState, useEffect, type ReactNode } from 'react'

import { cn } from '@/lib/utils'
import { matchesShortcut } from '@/lib/keyboard'
import { Sidebar } from './sidebar'
import { Topbar } from './topbar'
import { SearchDialog } from './search-dialog'

interface LayoutProps {
  children?: ReactNode
}

export function Layout({ children }: LayoutProps) {
  const [searchOpen, setSearchOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // 搜索快捷键 Cmd/Ctrl + K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (matchesShortcut(e, ['mod', 'k'])) {
        e.preventDefault()
        setSearchOpen(true)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  // 断点回弹：窗口 ≥1024px 时自动关闭移动端抽屉状态（防止 fixed/translate 状态残留导致与内容重叠）
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)')
    const handleChange = (e: MediaQueryListEvent) => {
      if (e.matches) {
        setSidebarOpen(false)
      }
    }
    mq.addEventListener('change', handleChange)
    return () => mq.removeEventListener('change', handleChange)
  }, [])

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* 移动端遮罩（侧边栏打开时——淡遮罩，内容让位模式下主要防误触） */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/30 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* 侧边栏——桌面静态 / 移动端抽屉（fixed 浮层） */}
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 -translate-x-full transition-transform duration-200 lg:static lg:translate-x-0',
          sidebarOpen && 'translate-x-0'
        )}
      >
        <Sidebar onNavigate={() => setSidebarOpen(false)} />
      </div>

      {/* 主区域——移动端抽屉打开时内容让位（ml 推开，与原版侧边栏占位行为一致） */}
      <div
        className={cn(
          'flex min-w-0 flex-1 flex-col overflow-hidden transition-[margin] duration-200',
          sidebarOpen ? 'ml-[var(--layout-sidebar-width,240px)] lg:ml-0' : 'ml-0'
        )}
      >
        {/* 顶栏 */}
        <Topbar
          onMenuClick={() => setSidebarOpen((v) => !v)}
          onSearchOpen={() => setSearchOpen(true)}
        />

        {/* 页面内容 */}
        <main
          id="main-content"
          className="flex-1 overflow-y-auto overflow-x-hidden outline-none"
          tabIndex={-1}
        >
          {children}
        </main>
      </div>

      {/* 搜索对话框 */}
      <SearchDialog open={searchOpen} onOpenChange={setSearchOpen} />
    </div>
  )
}