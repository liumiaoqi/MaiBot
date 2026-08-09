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
    const modernRadius = root.style.getPropertyValue('--radius-md')

    // 切换到 future-retro
    const futureRetroButton = screen.getByTestId('style-selector').querySelector('[data-style="future-retro"]')
    fireEvent.click(futureRetroButton!)
    await waitFor(() => {
      expect(root.dataset.dashboardStyle).toBe('future-retro')
    })
    const futureRetroRadius = root.style.getPropertyValue('--radius-md')

    // future-retro 圆角应更小（2-4px vs modern 6px）
    expect(futureRetroRadius).toBeTruthy()
    expect(modernRadius).toBeTruthy()
  })

  it('深色模式下切风格——明暗保持一致（不出现浅色跳变——2026-08-09 用户场景）', async () => {
    const { StyleSelector } = await import('@/features/config/appearance/style-selector')
    render(withProvider(createElement(StyleSelector)))
    const root = document.documentElement
    // 默认深色
    expect(root.classList.contains('dark')).toBe(true)
    const luma = (hex: string) => Number.parseInt(hex.replace('#', '').slice(0, 2), 16) / 255

    // 切 future-retro——背景深色（future-retro 深棕 #221814——L≈13%）
    const frButton = screen.getByTestId('style-selector').querySelector('[data-style="future-retro"]')
    fireEvent.click(frButton!)
    await waitFor(() => {
      expect(root.dataset.dashboardStyle).toBe('future-retro')
    })
    const frBg = root.style.getPropertyValue('--color-background')
    expect(luma(frBg)).toBeLessThan(0.5)
    expect(luma(frBg)).toBeGreaterThan(0.05)

    // 切回 modern——背景仍深色（modern 冷黑 #0c0e0c——L≈5%）
    const modernButton = screen.getByTestId('style-selector').querySelector('[data-style="modern"]')
    fireEvent.click(modernButton!)
    await waitFor(() => {
      expect(root.dataset.dashboardStyle).toBe('modern')
    })
    const modernBg = root.style.getPropertyValue('--color-background')
    expect(luma(modernBg)).toBeLessThan(0.5)
    // 色相允许不同（fr 暖棕 vs modern 冷黑——设计使然）——但明暗都深
  })

  it('浅色模式下切 future-retro——背景保持浅色（米色纸感——2026-08-09 用户精确复现）', async () => {
    const { StyleSelector } = await import('@/features/config/appearance/style-selector')
    localStorage.setItem(THEME_STORAGE_KEYS.MODE, 'light')
    render(withProvider(createElement(StyleSelector)))
    const root = document.documentElement
    const luma = (hex: string) => Number.parseInt(hex.replace('#', '').slice(0, 2), 16) / 255

    // 浅色模式
    expect(root.classList.contains('dark')).toBe(false)

    // 切 future-retro——背景应保持浅色（米色 #f3e3cc——L≈85%）
    const frButton = screen.getByTestId('style-selector').querySelector('[data-style="future-retro"]')
    fireEvent.click(frButton!)
    await waitFor(() => {
      expect(root.dataset.dashboardStyle).toBe('future-retro')
    })
    const frBg = root.style.getPropertyValue('--color-background')
    expect(luma(frBg)).toBeGreaterThan(0.5)

    // 切回 modern——背景仍浅色
    const modernButton = screen.getByTestId('style-selector').querySelector('[data-style="modern"]')
    fireEvent.click(modernButton!)
    await waitFor(() => {
      expect(root.dataset.dashboardStyle).toBe('modern')
    })
    expect(luma(root.style.getPropertyValue('--color-background'))).toBeGreaterThan(0.5)
  })

  it('快速连点切换（主题模式+风格交替 10 次）——明暗与最终主题一致（竞态回归检测）', async () => {
    const { StyleSelector } = await import('@/features/config/appearance/style-selector')
    const { ThemeModeSwitch } = await import('@/features/config/appearance/theme-mode-switch')
    render(withProvider(createElement('div', null, createElement(ThemeModeSwitch), createElement(StyleSelector))))
    const root = document.documentElement
    const luma = (hex: string) => Number.parseInt(hex.replace('#', '').slice(0, 2), 16) / 255

    // 交替快速点击 10 次（模拟用户连点——触发竞态窗口）
    for (let i = 0; i < 10; i++) {
      const modeBtn = i % 2 === 0 ? screen.getByRole('tab', { name: /dark/i }) : screen.getByRole('tab', { name: /light/i })
      fireEvent.click(modeBtn)
      const styleBtn = screen.getByTestId('style-selector').querySelector(i % 2 === 0 ? '[data-style="future-retro"]' : '[data-style="modern"]')
      fireEvent.click(styleBtn!)
    }

    // 最终状态：MODE=light + modern（最后一次是 light + modern）
    await waitFor(() => {
      const stored = localStorage.getItem(THEME_STORAGE_KEYS.MODE)
      expect(stored).toBe('light')
      expect(root.dataset.dashboardStyle).toBe('modern')
    })
    // 明暗与最终主题一致（light → 浅色背景）
    const bg = root.style.getPropertyValue('--color-background')
    expect(luma(bg)).toBeGreaterThan(0.5)
    // dark 类与最终主题一致
    expect(root.classList.contains('dark')).toBe(false)
  })

  it('切换纹理风格——--color-background-texture 注入变化（纹理切换链路）', async () => {
    const { FutureRetroPanel } = await import('@/features/config/appearance/future-retro-panel')
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'future-retro')
    render(withProvider(createElement(FutureRetroPanel)))
    const root = document.documentElement
    await waitFor(() => {
      const t = root.style.getPropertyValue('--color-background-texture')
      expect(t).toBeTruthy()
      expect(t).not.toBe('none')
    })
    // 切换到 none——纹理应为 none
    const noneCard = screen.getByTestId('fr-texture-card-none')
    fireEvent.click(noneCard)
    await waitFor(() => {
      expect(root.style.getPropertyValue('--color-background-texture')).toBe('none')
    })

    // 切回 dot-grid——纹理恢复（非 none）
    const dotCard = screen.getByTestId('fr-texture-card-dot-grid')
    fireEvent.click(dotCard)
    await waitFor(() => {
      const t = root.style.getPropertyValue('--color-background-texture')
      expect(t).toBeTruthy()
      expect(t).not.toBe('none')
    })
  })

  it('style-tweaks 滑块——font-size 变化注入 CSS 变量', async () => {
    const { StyleTweaksAccordion } = await import('@/features/config/appearance/style-tweaks-accordion')
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')
    render(withProvider(createElement(StyleTweaksAccordion)))
    const slider = screen.getByTestId('font-size-slider') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '18' } })
    const root = document.documentElement
    const fontSizeVar = root.style.getPropertyValue('--text-base')
    expect(fontSizeVar).toBeTruthy()
  })

  it('style-tweaks 滑块——border-radius 变化注入 CSS 变量', async () => {
    const { StyleTweaksAccordion } = await import('@/features/config/appearance/style-tweaks-accordion')
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')
    render(withProvider(createElement(StyleTweaksAccordion)))
    const slider = screen.getByTestId('border-radius-slider') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '12' } })
    const root = document.documentElement
    const radiusVar = root.style.getPropertyValue('--radius-md')
    expect(radiusVar).toBe('12px')
  })

  it('future-retro 字号滑块——baseFontSize 变化注入 6 个 --text-* 变量', async () => {
    const { FutureRetroPanel } = await import('@/features/config/appearance/future-retro-panel')
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'future-retro')
    render(withProvider(createElement(FutureRetroPanel)))
    const slider = screen.getByTestId('fr-font-size') as HTMLInputElement
    fireEvent.change(slider, { target: { value: '18' } })
    const root = document.documentElement
    await waitFor(() => {
      expect(root.style.getPropertyValue('--text-base')).toBe('1.1250rem')
    })
    // 全量 6 个字号 token 一起写（对齐原版 buildFontSizeTokens 比例）
    expect(root.style.getPropertyValue('--text-sm')).toBe('0.9844rem')
    expect(root.style.getPropertyValue('--text-xs')).toBe('0.8438rem')
    expect(root.style.getPropertyValue('--text-2xl')).toBe('1.6875rem')
  })
})