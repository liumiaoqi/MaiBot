import { useEffect, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'

import { checkAuthStatus } from '@/lib/auth'

const AUTH_STATUS_CACHE_MS = 30_000
let cachedAuthStatus: { authenticated: boolean; checkedAt: number } | null = null
let authStatusPromise: Promise<boolean> | null = null

function readCachedAuthStatus(): boolean | undefined {
  if (!cachedAuthStatus) {
    return undefined
  }
  if (Date.now() - cachedAuthStatus.checkedAt > AUTH_STATUS_CACHE_MS) {
    cachedAuthStatus = null
    return undefined
  }
  return cachedAuthStatus.authenticated
}

async function checkAuthStatusCached(): Promise<boolean> {
  const cached = readCachedAuthStatus()
  if (typeof cached === 'boolean') {
    return cached
  }
  authStatusPromise ??= checkAuthStatus().then((authenticated) => {
    cachedAuthStatus = { authenticated, checkedAt: Date.now() }
    return authenticated
  }).finally(() => {
    authStatusPromise = null
  })
  return authStatusPromise
}

export function useAuthGuard() {
  const navigate = useNavigate()
  const [checking, setChecking] = useState(readCachedAuthStatus() !== true)

  useEffect(() => {
    let cancelled = false
    const cached = readCachedAuthStatus()
    // 缓存命中已认证时，checking 初值已是 false（lazy init），无需同步 setState
    if (cached === true) {
      return () => {
        cancelled = true
      }
    }

    const verifyAuth = async () => {
      try {
        const isAuth = await checkAuthStatusCached()
        if (!cancelled && !isAuth) {
          navigate({ to: '/auth' })
        }
      } catch {
        if (!cancelled) {
          navigate({ to: '/auth' })
        }
      } finally {
        if (!cancelled) {
          setChecking(false)
        }
      }
    }

    verifyAuth()

    return () => {
      cancelled = true
    }
  }, [navigate])

  return { checking }
}