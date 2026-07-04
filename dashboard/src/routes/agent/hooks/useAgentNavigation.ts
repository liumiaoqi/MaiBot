import { useCallback, useEffect, useMemo, useState } from 'react'

import { useRouterState } from '@tanstack/react-router'

export function useAgentNavigation(agentIds: string[]) {
  const routerState = useRouterState()
  const search = (routerState.location.search ?? {}) as Record<string, string>
  const agentParam = search['agent'] ?? null

  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(agentParam)

  const sortedIds = useMemo(() => [...agentIds].sort(), [agentIds])

  useEffect(() => {
    if (agentParam && agentIds.includes(agentParam)) {
      setSelectedAgentId(agentParam)
    }
  }, [agentParam, agentIds])

  const navigateToAgent = useCallback((agentId: string | null) => {
    setSelectedAgentId(agentId)
    const url = new URL(window.location.href)
    if (agentId) {
      url.searchParams.set('agent', agentId)
    } else {
      url.searchParams.delete('agent')
    }
    window.history.replaceState(null, '', url.toString())
  }, [])

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