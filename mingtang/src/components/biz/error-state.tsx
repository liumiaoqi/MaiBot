/** 错误态——三态之一 */

interface ErrorStateProps {
  error: Error | unknown
  /** 重试回调 */
  onRetry?: () => void
}

export function ErrorState({ error, onRetry }: ErrorStateProps) {
  const message = error instanceof Error ? error.message : String(error)

  return (
    <div className="flex min-h-[400px] items-center justify-center" data-testid="error-state">
      <div className="text-center">
        <h2 className="text-lg font-semibold text-red-600">加载失败</h2>
        <p className="mt-2 text-sm text-muted-foreground">{message}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="mt-4 rounded-md bg-primary px-4 py-2 text-sm text-white hover:bg-primary/90"
          >
            重试
          </button>
        )}
      </div>
    </div>
  )
}