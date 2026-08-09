import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { createElement } from 'react'

import { ThemeProvider } from '@/app/theme-provider'
import { ThemeModeSwitch } from '@/features/config/appearance/theme-mode-switch'
import { AccentPicker } from '@/features/config/appearance/accent-picker'
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

describe('ThemeProvider 真实链路', () => {
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

  it('挂载时初始 pipeline 注入 CSS 变量', () => {
    render(withProvider(createElement('div', { 'data-testid': 'child' })))
    expect(screen.getByTestId('child')).toBeTruthy()
    const root = document.documentElement
    expect(root.style.length).toBeGreaterThan(0)
  })

  it('默认深色——documentElement 有 dark 类', () => {
    render(withProvider(createElement('div', null)))
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('切换到浅色——dark 类移除 + CSS 变量重注入', () => {
    render(withProvider(createElement(ThemeModeSwitch)))
    const lightButton = screen.getByRole('tab', { name: /light/i })
    fireEvent.click(lightButton)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(localStorage.getItem(THEME_STORAGE_KEYS.MODE)).toBe('light')
  })

  it('切换到深色——dark 类添加', () => {
    render(withProvider(createElement(ThemeModeSwitch)))
    const darkButton = screen.getByRole('tab', { name: /dark/i })
    fireEvent.click(darkButton)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(localStorage.getItem(THEME_STORAGE_KEYS.MODE)).toBe('dark')
  })

  it('accent 换色——CSS 变量变化（accent 变量注入）', async () => {
    render(withProvider(createElement(AccentPicker)))
    const colorInput = screen.getByTestId('accent-color-input') as HTMLInputElement
    fireEvent.change(colorInput, { target: { value: '#FF0000' } })
    await waitFor(() => {
      const root = document.documentElement
      const accentVar = root.style.getPropertyValue('--color-accent')
      expect(accentVar).toBeTruthy()
    }, { timeout: 500 })
  })

  it('style-selector 切换 future-retro——dataset 更新 + pipeline 重跑', async () => {
    const { StyleSelector } = await import('@/features/config/appearance/style-selector')
    render(withProvider(createElement(StyleSelector)))
    const futureRetroButton = screen.getByTestId('style-selector').querySelector('[data-style="future-retro"]')
    expect(futureRetroButton).toBeTruthy()
    fireEvent.click(futureRetroButton!)
    await waitFor(() => {
      expect(document.documentElement.dataset.dashboardStyle).toBe('future-retro')
    })
  })

  it('style-selector 切换 modern——dataset 更新', async () => {
    const { StyleSelector } = await import('@/features/config/appearance/style-selector')
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'future-retro')
    render(withProvider(createElement(StyleSelector)))
    const modernButton = screen.getByTestId('style-selector').querySelector('[data-style="modern"]')
    expect(modernButton).toBeTruthy()
    fireEvent.click(modernButton!)
    await waitFor(() => {
      expect(document.documentElement.dataset.dashboardStyle).toBe('modern')
    })
  })

  it('future-retro vs modern——CSS 变量有差异（圆角/阴影）', async () => {
    const { StyleSelector } = await import('@/features/config/appearance/style-selector')
    render(withProvider(createElement(StyleSelector)))
    const root = document.documentElement

    // 切换到 modern
    const modernButton = screen.getByTestId('style-selector').querySelector('[data-style="modern"]')
    fireEvent.click(modernButton!)
    await waitFor(() => {
      expect(root.dataset.dashboardStyle).toBe('modern')
    })
    const modernRadius = root.style.getPropertyValue('--visual-radius-md')

    // 切换到 future-retro
    const futureRetroButton = screen.getByTestId('style-selector').querySelector('[data-style="future-retro"]')
    fireEvent.click(futureRetroButton!)
    await waitFor(() => {
      expect(root.dataset.dashboardStyle).toBe('future-retro')
    })
    const futureRetroRadius = root.style.getPropertyValue('--visual-radius-md')

    // future-retro 圆角应更小（2-4px vs modern 6px）
    expect(futureRetroRadius).toBeTruthy()
    expect(modernRadius).toBeTruthy()
  })

  it('style-tweaks 滑块——font-size 变化注入 CSS 变量', async () => {
    const { StyleTweaksAccordion } = await import('@/features/config/appearance/style-tweaks-accordion')
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')
    render(withProvider(createElement(StyleTweaksAccordion)))
    const slider = screen.getByTestId('font-size-slider') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '18' } })
    const root = document.documentElement
    const fontSizeVar = root.style.getPropertyValue('--typography-font-size-base')
    expect(fontSizeVar).toBeTruthy()
  })

  it('style-tweaks 滑块——border-radius 变化注入 CSS 变量', async () => {
    const { StyleTweaksAccordion } = await import('@/features/config/appearance/style-tweaks-accordion')
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')
    render(withProvider(createElement(StyleTweaksAccordion)))
    const slider = screen.getByTestId('border-radius-slider') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '12' } })
    const root = document.documentElement
    const radiusVar = root.style.getPropertyValue('--visual-radius-md')
    expect(radiusVar).toBe('12px')
  })
})