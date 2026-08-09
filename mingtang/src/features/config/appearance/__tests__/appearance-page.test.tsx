import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { createElement } from 'react'

import { ThemeProvider } from '@/app/theme-provider'
import { AppearancePage } from '../index'
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

describe('TE-1-1：AppearancePage 跨组件状态共享（dashboardStyle Context 提升）', () => {
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

  it('默认 future-retro——自定义 CSS section 不渲染（7 坑 #4）', () => {
    render(withProvider(createElement(AppearancePage)))
    expect(screen.queryByTestId('custom-css-textarea')).not.toBeInTheDocument()
  })

  it('切到 modern——自定义 CSS section 渲染', async () => {
    render(withProvider(createElement(AppearancePage)))
    expect(screen.queryByTestId('custom-css-textarea')).not.toBeInTheDocument()

    const modernButton = screen.getByTestId('style-selector').querySelector('[data-style="modern"]')
    expect(modernButton).toBeTruthy()
    fireEvent.click(modernButton!)

    await waitFor(() => {
      expect(screen.getByTestId('custom-css-textarea')).toBeInTheDocument()
    })
  })

  it('切到 future-retro 再切回 modern——自定义 CSS section 跟随显示/隐藏（复现原 bug）', async () => {
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')

    render(withProvider(createElement(AppearancePage)))

    await waitFor(() => {
      expect(screen.getByTestId('custom-css-textarea')).toBeInTheDocument()
    })

    const retroButton = screen.getByTestId('style-selector').querySelector('[data-style="future-retro"]')
    fireEvent.click(retroButton!)
    await waitFor(() => {
      expect(screen.queryByTestId('custom-css-textarea')).not.toBeInTheDocument()
    })

    const modernButton = screen.getByTestId('style-selector').querySelector('[data-style="modern"]')
    fireEvent.click(modernButton!)
    await waitFor(() => {
      expect(screen.getByTestId('custom-css-textarea')).toBeInTheDocument()
    })
  })

  it('StyleSelector 切换 style 后 AppearancePage 条件 section 跟随更新（核心修复验证）', async () => {
    render(withProvider(createElement(AppearancePage)))

    // 默认 future-retro——AccentPicker 不渲染（仅 modern）
    expect(screen.queryByTestId('accent-color-input')).not.toBeInTheDocument()

    const modernButton = screen.getByTestId('style-selector').querySelector('[data-style="modern"]')
    fireEvent.click(modernButton!)

    await waitFor(() => {
      expect(screen.getByTestId('accent-color-input')).toBeInTheDocument()
    })
  })

  it('modern 风格下 CustomCssEditor 渲染（CodeEditor + 清除按钮 + 黄色警告区）', async () => {
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')
    render(withProvider(createElement(AppearancePage)))

    await waitFor(() => {
      expect(screen.getByTestId('custom-css-textarea')).toBeInTheDocument()
    })
    expect(screen.getByTestId('custom-css-clear')).toBeInTheDocument()
    expect(screen.getByTestId('custom-css-warnings')).toBeInTheDocument()
  })
})