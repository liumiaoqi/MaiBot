/**
 * useMaibotVersion 测试（§4.7.1 测试先行）
 *
 * 核心验证：
 * - GitHub 降级（fetch reject/403 → maibotStableRelease=null，不抛错）
 * - hitokoto 降级（fetch reject → fallback 文案）
 * - 不重试（grep retry 零命中）
 */
import { renderHook, waitFor, act } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'home.hitokotoFallback': '人生就像一盒巧克力，你永远不知道下一颗是什么味道。',
        'home.hitokotoFallbackFrom': '阿甘正传',
        'home.unknownSource': '未知',
      }
      return map[key] ?? key
    },
  }),
}))

import { useMaibotVersion } from '../use-maibot-version'

function createWrapper() {
  return function TestWrapper({ children }: { children: ReactNode }) {
    return createElement('div', null, children)
  }
}

const mockGitHubReleases = [
  { draft: false, prerelease: false, tag_name: 'v2.5.4', html_url: 'https://github.com/Mai-with-u/MaiBot/releases/tag/v2.5.4' },
  { draft: false, prerelease: true, tag_name: 'v2.6.0-beta', html_url: 'https://github.com/Mai-with-u/MaiBot/releases/tag/v2.6.0-beta' },
]

const mockHitokoto = { hitokoto: '测试一言', from: '测试来源', from_who: '测试作者' }

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', vi.fn())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useMaibotVersion', () => {
  it('初始状态：hitokoto=null + hitokotoLoading=true + maibotStableRelease=null', () => {
    const { result } = renderHook(() => useMaibotVersion(), { wrapper: createWrapper() })
    expect(result.current.hitokoto).toBeNull()
    expect(result.current.hitokotoLoading).toBe(true)
    expect(result.current.maibotStableRelease).toBeNull()
  })

  it('GitHub 成功 → maibotStableRelease 填充稳定版（过滤 prerelease）', async () => {
    const mockFetch = vi.mocked(fetch)
    mockFetch.mockImplementation((url: URL | RequestInfo) => {
      if (String(url).includes('github.com')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockGitHubReleases),
        } as Response)
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockHitokoto),
      } as Response)
    })

    const { result } = renderHook(() => useMaibotVersion(), { wrapper: createWrapper() })

    await waitFor(() => {
      expect(result.current.maibotStableRelease).not.toBeNull()
    })
    expect(result.current.maibotStableRelease?.version).toBe('2.5.4')
  })

  it('GitHub 降级（fetch reject → maibotStableRelease=null，不抛错）', async () => {
    const mockFetch = vi.mocked(fetch)
    mockFetch.mockImplementation((url: URL | RequestInfo) => {
      if (String(url).includes('github.com')) {
        return Promise.reject(new Error('GitHub 403'))
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockHitokoto),
      } as Response)
    })

    const { result } = renderHook(() => useMaibotVersion(), { wrapper: createWrapper() })

    // GitHub 失败 → maibotStableRelease 保持 null，不抛错
    await waitFor(() => {
      expect(result.current.hitokotoLoading).toBe(true)
    })
    expect(result.current.maibotStableRelease).toBeNull()
  })

  it('hitokoto 成功 → hitokoto 填充', async () => {
    const mockFetch = vi.mocked(fetch)
    mockFetch.mockImplementation((url: URL | RequestInfo) => {
      if (String(url).includes('github.com')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockGitHubReleases) } as Response)
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve(mockHitokoto) } as Response)
    })

    const { result } = renderHook(() => useMaibotVersion(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.fetchHitokoto()
    })

    await waitFor(() => {
      expect(result.current.hitokoto).not.toBeNull()
    })
    expect(result.current.hitokoto?.hitokoto).toBe('测试一言')
    expect(result.current.hitokotoLoading).toBe(false)
  })

  it('hitokoto 降级（fetch reject → fallback 文案）', async () => {
    const mockFetch = vi.mocked(fetch)
    mockFetch.mockImplementation((url: URL | RequestInfo) => {
      if (String(url).includes('github.com')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockGitHubReleases) } as Response)
      }
      return Promise.reject(new Error('hitokoto boom'))
    })

    const { result } = renderHook(() => useMaibotVersion(), { wrapper: createWrapper() })

    await act(async () => {
      await result.current.fetchHitokoto()
    })

    await waitFor(() => {
      expect(result.current.hitokoto).not.toBeNull()
    })
    expect(result.current.hitokoto?.hitokoto).toBe('人生就像一盒巧克力，你永远不知道下一颗是什么味道。')
    expect(result.current.hitokoto?.from).toBe('阿甘正传')
    expect(result.current.hitokotoLoading).toBe(false)
  })
})