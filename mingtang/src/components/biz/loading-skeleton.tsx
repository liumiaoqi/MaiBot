/** 加载骨架——三态之一 */

interface LoadingSkeletonProps {
  /** 骨架行数 */
  rows?: number
  /** 自定义提示文本 */
  message?: string
}

export function LoadingSkeleton({ rows = 3, message }: LoadingSkeletonProps) {
  return (
    <div className="space-y-4 p-6" data-testid="loading-skeleton">
      {message && <p className="text-sm text-gray-500">{message}</p>}
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded bg-gray-200"
          style={{ width: `${100 - i * 10}%` }}
        />
      ))}
    </div>
  )
}