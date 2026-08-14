/**
 * usePluginHomeCards —— 插件首页卡片领域 hook（页面逻辑下沉）。
 *
 * useQuery 无缓存（挂载一次性拉取）——替代原版手写 useState + useEffect。
 * 统一走 useApiQuery 包装；错误降级为空数组由本 hook 归一化（data ?? []）。
 */
import { getPluginHomeCards, type PluginHomeCard } from '@/lib/plugin-api'

import { useApiQuery } from './use-api-query'

export function usePluginHomeCards() {
  const { data, loading, error } = useApiQuery<PluginHomeCard[]>(
    ['api', 'plugin', 'home-cards'],
    () => getPluginHomeCards(),
  )

  return {
    pluginHomeCards: data ?? [],
    isLoading: loading,
    error,
  }
}
