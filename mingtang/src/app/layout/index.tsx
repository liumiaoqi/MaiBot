import { useState, useEffect, type ReactNode } from 'react'

import { matchesShortcut } from '@/lib/keyboard'
import { Sidebar } from './sidebar'
import { Topbar } from './topbar'
import { SearchDialog } from './search-dialog'

interface LayoutProps {
  children?: ReactNode
}

export function Layout({ children }: LayoutProps) {
  const [searchOpen, setSearchOpen] = useState(false)

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
      {/* 侧边栏 */}
      <div className="hidden shrink-0 lg:block">
        <Sidebar />
      </div>

      {/* 主区域 */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* 顶栏 */}
        <Topbar onSearchOpen={() => setSearchOpen(true)} />

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