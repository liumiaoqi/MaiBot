import type { ReactNode } from 'react'

/** PageShell——标准页面骨架（标题 + 面包屑 + 内容区） */

interface PageShellProps {
  /** 页面标题 */
  title: string
  /** 面包屑（域 > 页 > 详情） */
  breadcrumb?: string[]
  /** 内容区 */
  children: ReactNode
  /** 右侧操作区 */
  actions?: ReactNode
}

export function PageShell({ title, breadcrumb, children, actions }: PageShellProps) {
  return (
    <div className="min-h-screen bg-background" data-testid="page-shell">
      <header className="border-b border-border px-6 py-4">
        {breadcrumb && breadcrumb.length > 0 && (
          <nav className="mb-2 text-sm text-gray-500" aria-label="面包屑">
            {breadcrumb.map((item, i) => (
              <span key={i}>
                {i > 0 && <span className="mx-2">/</span>}
                {item}
              </span>
            ))}
          </nav>
        )}
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-foreground">{title}</h1>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      </header>
      <main className="p-6">{children}</main>
    </div>
  )
}