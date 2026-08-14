import { useCallback, useState } from 'react'

export type TopView = 'dashboard' | 'constellation' | 'global'

/**
 * useViewSwitch 顶层视图切换（dashboard/constellation/global）
 *
 * P2-C #4：历史视图恢复能力全仓零调用——连同 previousView 状态一并删除
 * （革命式清理，不留死代码）。
 */
export function useViewSwitch() {
  const [currentView, setCurrentView] = useState<TopView>('dashboard')

  const switchView = useCallback((view: TopView) => {
    setCurrentView(view)
  }, [])

  return {
    currentView,
    switchView,
  }
}
