/** 空态——三态之一 */

interface EmptyStateProps {
  /** 提示消息 */
  message?: string
  /** 操作按钮 */
  action?: React.ReactNode
}

export function EmptyState({ message = '暂无数据', action }: EmptyStateProps) {
  return (
    <div className="flex min-h-[400px] items-center justify-center" data-testid="empty-state">
      <div className="text-center">
        <p className="text-sm text-gray-500">{message}</p>
        {action && <div className="mt-4">{action}</div>}
      </div>
    </div>
  )
}