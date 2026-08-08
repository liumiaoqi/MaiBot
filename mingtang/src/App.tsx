import { Outlet } from '@tanstack/react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import { Suspense } from 'react'
import { queryClient } from './app/query-client'
import { ErrorBoundary } from './components/biz/error-boundary'

/** 加载占位 */
function LoadingFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-sm text-gray-500">加载中…</div>
    </div>
  )
}

/** App 根组件——错误边界 > QueryClientProvider > Suspense > 路由出口 */
export function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <Suspense fallback={<LoadingFallback />}>
          <Outlet />
        </Suspense>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
