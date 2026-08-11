/**
 * useReviewStats —— 表达方式审核统计领域 hook（页面逻辑下沉）。
 *
 * useQuery 无缓存——替代原版手写 useState + useEffect + isMountedRef。
 */
import { useQuery } from '@tanstack/react-query'

import { getReviewStats } from '@/lib/expression-api'

export function useReviewStats() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['api', 'expression', 'review-stats'],
    queryFn: () => getReviewStats(),
  })

  return {
    uncheckedCount: data?.unchecked ?? 0,
    isLoading,
    error,
  }
}