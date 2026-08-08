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

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* 移动端遮罩（侧边栏打开时） */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* 侧边栏——桌面静态 / 移动端抽屉 */}
      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 -translate-x-full transition-transform duration-200 lg:static lg:translate-x-0',
          sidebarOpen && 'translate-x-0'
        )}
      >
        <Sidebar onNavigate={() => setSidebarOpen(false)} />
      </div>

      {/* 主区域 */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
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