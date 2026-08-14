/**
 * PluginProgressBox —— 插件域统一的进度展示公共组件（R4 债清理 P2）。
 *
 * 收编三处手工实现：plugin-card 卡片底部进度、install-dialog 安装进度、
 * config/dialogs 的 ProgressDialog。三态语义色板（success/error——色板豁免）。
 *
 * props：
 * - progress：插件加载进度（loading/success/error 三态）
 * - actionLabel：操作动词（「安装」「卸载」「更新」「删除」）——派生 正在X / X完成 / X失败
 * - compact：卡片内紧凑尺寸（图标 h-3、文字 text-xs、进度条 h-1.5、消息截断）
 * - footer：进度框底部附加内容（如 install-dialog 的插件 ID/分支信息）
 */
import { AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'

import { Progress } from '@/components/ui/progress'
import type { PluginLoadProgress } from '@/lib/plugin-api'
import { getPluginProgressDetail } from '@/features/plugin/shared/types'

interface PluginProgressBoxProps {
  progress: PluginLoadProgress
  /** 操作动词标签：「安装」「卸载」「更新」「删除」 */
  actionLabel: string
  /** 紧凑模式（卡片内小尺寸） */
  compact?: boolean
  /** 进度框底部附加内容 */
  footer?: React.ReactNode
}

export function PluginProgressBox({
  progress,
  actionLabel,
  compact = false,
  footer,
}: PluginProgressBoxProps) {
  const isSuccess = progress.stage === 'success'
  const isError = progress.stage === 'error'
  const isLoading = progress.stage === 'loading'
  const progressDetail = getPluginProgressDetail(progress)
  const iconClassName = compact ? 'h-3 w-3' : 'h-4 w-4'
  const labelClassName = compact ? 'text-xs' : 'text-sm'
  const messageClassName = compact
    ? `text-xs ${
        isSuccess
          ? 'text-green-600 dark:text-green-400 truncate'
          : isError
            ? 'text-red-600 dark:text-red-400'
            : 'text-muted-foreground truncate'
      }`
    : `text-sm break-words ${
        isSuccess
          ? 'text-green-600 dark:text-green-400'
          : isError
            ? 'text-red-600 dark:text-red-400'
            : 'text-muted-foreground'
      }`

  return (
    // 尺寸类用静态完整类名（Tailwind v4 扫描器只识别完整字符串——避免动态拼接漏检）
    <div
      className={compact
        ? `space-y-2 rounded-lg border p-2.5 ${
            isSuccess
              ? 'border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/20'
              : isError
                ? 'border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/20'
                : 'bg-muted/50'
          }`
        : `space-y-3 rounded-lg border p-3 ${
            isSuccess
              ? 'border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950/20'
              : isError
                ? 'border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950/20'
                : 'bg-muted/50'
          }`}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          {isLoading ? (
            <Loader2 className={`${iconClassName} shrink-0 animate-spin`} />
          ) : isSuccess ? (
            <CheckCircle2 className={`${iconClassName} shrink-0 text-green-600`} />
          ) : (
            <AlertCircle className={`${iconClassName} shrink-0 text-red-600`} />
          )}
          <span
            className={`${labelClassName} font-medium ${
              isSuccess
                ? 'text-green-700 dark:text-green-300'
                : isError
                  ? 'text-red-700 dark:text-red-300'
                  : ''
            }`}
          >
            {isLoading && `正在${actionLabel}`}
            {isSuccess && `${actionLabel}完成`}
            {isError && `${actionLabel}失败`}
          </span>
        </div>
        {!isError && (
          <span
            className={`shrink-0 ${labelClassName} font-medium ${
              isSuccess ? 'text-green-700 dark:text-green-300' : ''
            }`}
          >
            {progress.progress}%
          </span>
        )}
      </div>
      {!isError && (
        <Progress
          value={progress.progress}
          className={`${compact ? 'h-1.5' : 'h-2'} ${
            isSuccess ? '[&>div]:bg-green-500' : ''
          }`}
        />
      )}
      <p className={messageClassName}>
        {isError
          ? progress.error || progress.message || `${actionLabel}失败`
          : progress.message}
      </p>
      {progressDetail && (
        <div
          className={`${compact ? 'truncate text-xs' : 'break-words text-xs'} text-muted-foreground`}
        >
          {progressDetail}
        </div>
      )}
      {footer}
    </div>
  )
}
