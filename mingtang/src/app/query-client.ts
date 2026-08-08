/**
 * QueryClient 基座——TanStack Query 数据流统一入口
 *
 * 规范（蓝皮书 §四）：
 * - 所有 API 调用走 useQuery（不裸 fetch）
 * - queryKey 格式 ['api', 资源名, 参数] 全局唯一
 * - 写操作成功后 invalidateQueries 统一失效
 * - Query 错误 → 页面错误态（三态统一）不静默
 * - 乐观更新仅高频交互用（低频用失效刷新，简单优先）
 */
import { MutationCache, QueryClient } from '@tanstack/react-query'

declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: {
      /** 设为 true 时跳过全局错误 toast，由调用方自行处理错误 */
      suppressErrorToast?: boolean
      /** 全局错误 toast 的标题，默认「操作失败」 */
      errorTitle?: string
    }
  }
}

/** toast 占位——R1-3 组装 Layout 后替换为真实 toast */
function toast(options: { title: string; description?: string; variant?: string }) {
  console.error(`[${options.variant ?? 'default'}] ${options.title}: ${options.description ?? ''}`)
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: 1,
        refetchOnWindowFocus: false,
        staleTime: 5 * 60 * 1000,
      },
      mutations: {
        retry: false,
      },
    },
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (mutation.meta?.suppressErrorToast) {
          return
        }
        toast({
          title: mutation.meta?.errorTitle ?? '操作失败',
          description: error instanceof Error ? error.message : String(error),
          variant: 'destructive',
        })
      },
    }),
  })
}

/** 应用级单例，在 main.tsx 经 QueryClientProvider 注入 */
export const queryClient = createQueryClient()