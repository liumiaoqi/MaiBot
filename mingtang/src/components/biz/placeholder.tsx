/** 占位组件——R1 阶段路由登记用，R2-R4 组装实际业务页面 */

interface PlaceholderProps {
  /** 页面名称 */
  pageName: string
  /** 功能域 */
  domain: string
}

export function Placeholder({ pageName, domain }: PlaceholderProps) {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h1 className="text-2xl font-bold text-foreground">{pageName}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {domain} · 占位页（R2-R4 组装）
        </p>
      </div>
    </div>
  )
}