import { useCallback, useState } from 'react'

export type TopView = 'dashboard' | 'constellation' | 'global'

export function useViewSwitch() {
  const [currentView, setCurrentView] = useState<TopView>('dashboard')
  const [previousView, setPreviousView] = useState<TopView>('dashboard')

  const switchView = useCallback((view: TopView) => {
    setPreviousView(currentView)
    setCurrentView(view)
  }, [currentView])

  const restorePreviousView = useCallback(() => {
    setCurrentView(previousView)
  }, [previousView])

  return {
    currentView,
    switchView,
    restorePreviousView,
  }
}