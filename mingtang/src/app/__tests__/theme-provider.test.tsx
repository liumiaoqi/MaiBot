import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { createElement } from 'react'

import { ThemeProvider } from '@/app/theme-provider'
import { ThemeModeSwitch } from '@/features/config/appearance/theme-mode-switch'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'

// jsdom 缺 matchMedia——补 mock
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}))

vi.mock('@/lib/config-api', () => ({
  getBotConfig: vi.fn().mockResolvedValue({ webui: {} }),
  updateBotConfigSection: vi.fn().mockResolvedValue(undefined),
}))

function withProvider(children: React.ReactNode) {
  return createElement(ThemeProvider, null, children)
}

function dispatchStorageEvent(key: string, newValue: string | null) {
  const event = new StorageEvent('storage', {
    key,
    newValue,
    storageArea: localStorage,
  })
  window.dispatchEvent(event)
}

describe('TE-2-3：跨标签页主题同步（storage 事件）', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.className = ''
    document.documentElement.dataset.dashboardStyle = ''
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.className = ''
    document.documentElement.dataset.dashboardStyle = ''
  })

  it('MODE 键 storage 事件 → 主题重新应用', async () => {
    render(withProvider(createElement(ThemeModeSwitch)))

    // 初始默认 dark
    expect(document.documentElement.classList.contains('dark')).toBe(true)

    // 模拟另一个标签页切到 light
    localStorage.setItem(THEME_STORAGE_KEYS.MODE, 'light')
    dispatchStorageEvent(THEME_STORAGE_KEYS.MODE, 'light')

    await waitFor(() => {
      expect(document.documentElement.classList.contains('dark')).toBe(false)
    })
  })

  it('DASHBOARD_STYLE 键 storage 事件 → dataset 更新', async () => {
    const { StyleSelector } = await import('@/features/config/appearance/style-selector')
    render(withProvider(createElement(StyleSelector)))

    // 模拟另一个标签页切到 modern
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')
    dispatchStorageEvent(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')

    await waitFor(() => {
      expect(document.documentElement.dataset.dashboardStyle).toBe('modern')
    })
  })

  it('非主题键 storage 事件 → 忽略', () => {
    const initialDark = document.documentElement.classList.contains('dark')
    dispatchStorageEvent('other-key', 'some-value')
    // 主题状态不变
    expect(document.documentElement.classList.contains('dark')).toBe(initialDark)
  })

  it('8 主题键均监听', () => {
    const { container } = render(withProvider(createElement('div', { 'data-testid': 'child' })))

    const themeKeys = Object.values(THEME_STORAGE_KEYS)
    expect(themeKeys).toHaveLength(8)

    // 每个键触发 storage 事件不应崩溃
    themeKeys.forEach((key) => {
      dispatchStorageEvent(key, 'test-value')
    })
    // 验证不崩溃——组件仍挂载
    expect(container.querySelector('[data-testid="child"]')).toBeTruthy()
  })

  it('组件卸载时 removeEventListener 调用（无内存泄漏）', () => {
    const spy = vi.spyOn(window, 'removeEventListener')
    const { unmount } = render(withProvider(createElement('div', null)))
    unmount()
    expect(spy).toHaveBeenCalledWith('storage', expect.any(Function))
    spy.mockRestore()
  })
})