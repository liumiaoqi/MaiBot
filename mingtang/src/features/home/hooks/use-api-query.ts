/**
 * useApiQuery —— home 域 useQuery 统一包装（P2 债务清理）。
 *
 * 收编 useQuery hook 的重复样板（P1 整删 2 个孤儿 hook 后剩 3 处：useBotStatus /
 * useDashboardData / usePluginHomeCards）：
 * - loading 命名三套（isBotStatusLoading / loading / isLoading）→ 统一 loading
 * - error 只有 usePluginHomeCards 暴露 → 统一返回 error
 * - 3 处 invalidateQueries 重复 → 统一 refresh
 * - 空值归一化（data ?? null / data ?? []）由各 hook 按自身语义映射，本包装不假设默认值
 *
 * 内部 console.error：spec §5.1.3-1c 要求「卡片数值显示 `--`，控制台 console.error」——
 * 请求失败统一在 queryFn 内 console.error（各 hook 不再各自处理）。
 */
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'

export interface UseApiQueryOptions {
  staleTime?: number
  refetchInterval?: number
  refetchOnWindowFocus?: boolean
  refetchOnReconnect?: boolean
}

export function useApiQuery<TData>(
  queryKey: readonly unknown[],
  fetcher: () => Promise<TData>,
  options: UseApiQueryOptions = {},
) {
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery<TData>({
    queryKey,
    queryFn: () =>
      fetcher().catch((err: unknown) => {
        // spec §5.1.3-1c：后端 API 调用失败 → 控制台 console.error（UI 由卡片 `--` 占位兜底）
        console.error('API 请求失败:', queryKey, err)
        throw err
      }),
    ...options,
  })

  // 统一刷新：invalidateQueries 触发重取（等价原 fetchXxx(force=true) 的"跳缓存重拉"语义）
  const refresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey })
  }, [queryClient, queryKey])

  return { data, loading: isLoading, error, refresh }
}
