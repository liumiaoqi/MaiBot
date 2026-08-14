/**
 * SurveyPageShell —— 问卷页面公共壳（标题 / 描述 / 内容容器）。
 *
 * P2 清理：两问卷页（maibot-feedback / webui-feedback）重复的页面壳抽取至此。
 * 错误/重试块未纳入壳——问卷配置是静态 import，运行时不可能加载失败，
 * 原「无法加载问卷配置」分支是假三态（loading/error/success）的遗留死代码，随重构一起删除。
 */
import { FileQuestion } from 'lucide-react'
import type { ReactNode } from 'react'

interface SurveyPageShellProps {
  title: string
  description: string
  children: ReactNode
}

export function SurveyPageShell({ title, description, children }: SurveyPageShellProps) {
  return (
    <div className="h-[calc(100vh-4rem)] flex flex-col p-4 sm:p-6">
      {/* 页面标题 */}
      <div className="mb-4 sm:mb-6 shrink-0">
        <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2">
          <FileQuestion className="h-8 w-8" strokeWidth={2} />
          {title}
        </h1>
        <p className="text-muted-foreground mt-1 text-sm sm:text-base">{description}</p>
      </div>

      {/* 问卷内容 */}
      <div className="flex-1 min-h-0">{children}</div>
    </div>
  )
}
