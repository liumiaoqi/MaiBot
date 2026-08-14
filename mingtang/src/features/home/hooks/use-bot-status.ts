/**
 * useBotStatus —— 机器人运行状态领域 hook（页面逻辑下沉）。
 *
 * useQuery 化（30s staleTime + refetchInterval + refetchOnWindowFocus + refetchOnReconnect）
 * ——替代原版手写 let 模块级缓存 + setInterval 轮询 + addEventListener visibilitychange/focus。
 * 统一走 useApiQuery 包装（loading/error/refresh 样板 + 失败 console.error 满足 spec §5.1.3）。
 *
 * force 契约简化说明（P2）：design §2.2.2.2 承诺 fetchBotStatus(force?: boolean)——
 * invalidateQueries 对 active 查询总是重新拉取（即 force=true 语义），且当前无消费者传 force，
 * 故保持无参形式（fetchBotStatus = refresh），对外返回值结构不变。
 */
import { backendApi } from '@/lib/http'

import { useApiQuery } from './use-api-query'
import type { BotStatus } from '../types'

const QUERY_KEY = ['api', 'system', 'status'] as const

export function useBotStatus() {
  const { data, loading, refresh } = useApiQuery<BotStatus>(
    QUERY_KEY,
    () => backendApi.get<BotStatus>('/api/webui/system/status'),
    {
      staleTime: 30_000,
      refetchInterval: 30_000,
      refetchOnWindowFocus: true,
      refetchOnReconnect: true,
    },
  )

  return {
    botStatus: data ?? null,
    isBotStatusLoading: loading,
    fetchBotStatus: refresh,
  }
}
