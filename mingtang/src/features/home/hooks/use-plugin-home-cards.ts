/**
 * usePluginHomeCards —— 插件首页卡片领域 hook（页面逻辑下沉）。
 *
 * useQuery 无缓存（挂载一次性拉取）——替代原版手写 useState + useEffect。
 */
import { useQuery } from '@tanstack/react-query'

import { getPluginHomeCards, type PluginHomeCard } from '@/lib/plugin-api'

export function usePluginHomeCards() {
  const { data, isLoading, error } = useQuery<PluginHomeCard[]>({
    queryKey: ['api', 'plugin', 'home-cards'],
    queryFn: () => getPluginHomeCards(),
  })

  return {
    pluginHomeCards: data ?? [],
    isLoading,
    error,
  }
}