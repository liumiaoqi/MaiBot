import { useCallback, useEffect, useRef } from 'react'
import { useBlocker } from '@tanstack/react-router'

export interface UseUnsavedChangesGuardOptions {
  isDirty: boolean
  onSave?: () => Promise<void> | void
  onDiscard?: () => void
  message?: string
}

export function useUnsavedChangesGuard({
  isDirty,
  onSave,
  onDiscard,
  message = '存在未保存的修改，离开将丢失未保存的内容。是否继续？',
}: UseUnsavedChangesGuardOptions) {
  const stateRef = useRef({ isDirty, onSave, onDiscard, message })
  stateRef.current = { isDirty, onSave, onDiscard, message }

  // 拦截浏览器关闭/刷新
  const beforeUnloadHandler = useCallback((event: BeforeUnloadEvent) => {
    if (!stateRef.current.isDirty) return
    event.preventDefault()
  }, [])

  useEffect(() => {
    window.addEventListener('beforeunload', beforeUnloadHandler)
    return () => window.removeEventListener('beforeunload', beforeUnloadHandler)
  }, [beforeUnloadHandler])

  // 拦截 TanStack Router 路由跳转
  useBlocker({
    shouldBlockFn: () => stateRef.current.isDirty,
    withResolver: true,
    blockerFn: ({ proceed, reset }) => {
      const result = window.confirm(stateRef.current.message)
      if (result) {
        if (stateRef.current.onDiscard) {
          stateRef.current.onDiscard()
        }
        proceed()
      } else {
        reset()
      }
    },
  })

  // 编程式 API：确认离开（放弃修改）
  const confirmLeave = useCallback((): boolean => {
    if (!stateRef.current.isDirty) return true

    const result = window.confirm(stateRef.current.message)
    if (!result) return false

    if (stateRef.current.onDiscard) {
      stateRef.current.onDiscard()
    }

    return true
  }, [])

  // 编程式 API：确认离开（先保存）
  const confirmLeaveWithSave = useCallback(async (): Promise<boolean> => {
    if (!stateRef.current.isDirty) return true

    const result = window.confirm(stateRef.current.message)
    if (!result) return false

    if (stateRef.current.onSave) {
      await stateRef.current.onSave()
    }

    return true
  }, [])

  return { confirmLeave, confirmLeaveWithSave }
}
