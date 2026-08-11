import type { ReactNode } from 'react'
import { useEffect } from 'react'

import { TooltipProvider } from '@/components/ui/tooltip'
import { useAuthGuard } from '@/hooks/use-auth'

interface EmbedPageShellProps {
  children: ReactNode
  shellId: string
  title: string
}

/**
 * 给外部程序嵌入使用的页面外壳：不挂载 dashboard 顶栏和侧边栏。
 * 精简背景层——纯 CSS bg-background（不搬移 background-layer 依赖链）。
 */
export function EmbedPageShell({ children, shellId, title }: EmbedPageShellProps) {
  const { checking } = useAuthGuard()

  useEffect(() => {
    document.title = title
  }, [title])

  if (checking) {
    return (
      <div className="bg-background flex h-screen items-center justify-center">
        <div className="text-muted-foreground">麦麦正在啃食服务器...</div>
      </div>
    )
  }

  return (
    <TooltipProvider delayDuration={300}>
      <div data-dashboard-shell={shellId} className="bg-background relative isolate h-screen overflow-hidden">
        <main
          id="main-content"
          data-dashboard-main="true"
          tabIndex={-1}
          className="relative z-10 h-full min-h-0 outline-none"
        >
          {children}
        </main>
      </div>
    </TooltipProvider>
  )
}