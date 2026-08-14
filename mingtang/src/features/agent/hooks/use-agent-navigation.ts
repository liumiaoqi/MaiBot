import { useCallback, useEffect, useMemo, useState } from 'react'

import { useNavigate, useRouterState } from '@tanstack/react-router'

export function useAgentNavigation(agentIds: string[]) {
  const navigate = useNavigate()
  const routerState = useRouterState()
  const search = (routerState.location.search ?? {}) as Record<string, string>
  const agentParam = search['agent'] ?? null

  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(agentParam)

  const sortedIds = useMemo(() => [...agentIds].sort(), [agentIds])

  const [prevAgentParam, setPrevAgentParam] = useState<string | null>(agentParam)
  if (agentParam !== prevAgentParam) {
    setPrevAgentParam(agentParam)
    if (agentParam && agentIds.includes(agentParam)) {
      setSelectedAgentId(agentParam)
    }
  }

  const navigateToAgent = useCallback((agentId: string | null) => {
    setSelectedAgentId(agentId)
    // P2-C #6：search 参数经 TanStack Router 官方 API 同步（替代 URL 直接改写旁路）——
    // agent=undefined 时 router 从 URL 移除该参数；replace: true 保留原旁路的不进历史栈语义。
    // 路由未声明 validateSearch，typed search 无法表达动态参数——沿用仓库既有 as never 先例（plugin/detail）。
    navigate({
      to: '/agents',
      search: { agent: agentId ?? undefined },
      replace: true,
    } as never)
  }, [navigate])

  const navigateToNext = useCallback(() => {
    if (!selectedAgentId) {
      if (sortedIds.length > 0) navigateToAgent(sortedIds[0])
      return
    }
    const idx = sortedIds.indexOf(selectedAgentId)
    if (idx < sortedIds.length - 1) {
      navigateToAgent(sortedIds[idx + 1])
    }
  }, [selectedAgentId, sortedIds, navigateToAgent])

  const navigateToPrev = useCallback(() => {
    if (!selectedAgentId) return
    const idx = sortedIds.indexOf(selectedAgentId)
    if (idx > 0) {
      navigateToAgent(sortedIds[idx - 1])
    }
  }, [selectedAgentId, sortedIds, navigateToAgent])

  const exitInnerWorld = useCallback(() => {
    navigateToAgent(null)
  }, [navigateToAgent])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        navigateToNext()
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        navigateToPrev()
      } else if (e.key === 'Escape') {
        exitInnerWorld()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [navigateToNext, navigateToPrev, exitInnerWorld])

  return {
    selectedAgentId,
    setSelectedAgentId: navigateToAgent,
    navigateToAgent,
    navigateToNext,
    navigateToPrev,
    isInnerWorldOpen: selectedAgentId !== null,
    exitInnerWorld,
  }
}