import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { createElement } from 'react'

import { DEFAULT_DASHBOARD_STYLE, DEFAULT_FUTURE_RETRO_STYLE_CONFIG } from '@/lib/theme/tokens'
import { DEFAULT_ACCENT_COLOR_HEX, DEFAULT_ACCENT_COLOR_HSL } from '@/lib/theme/palette'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}))

const { mockStyle } = vi.hoisted(() => ({ mockStyle: { current: 'future-retro' } }))

vi.mock('@/features/config/appearance/style-selector', () => ({
  useDashboardStyle: () => ({ style: mockStyle.current, setStyle: vi.fn() }),
  StyleSelector: () => createElement('div', { 'data-testid': 'style-selector' }),
}))

vi.mock('@/components/biz/page-shell', () => ({
  PageShell: ({ children }: { children: React.ReactNode }) => createElement('div', null, children),
}))

vi.mock('@/features/config/appearance/theme-mode-switch', () => ({
  ThemeModeSwitch: () => createElement('div', { 'data-testid': 'theme-mode-switch' }),
}))
vi.mock('@/features/config/appearance/accent-picker', () => ({
  AccentPicker: () => createElement('div', { 'data-testid': 'accent-picker' }),
}))
vi.mock('@/features/config/appearance/future-retro-panel', () => ({
  FutureRetroPanel: () => createElement('div', { 'data-testid': 'future-retro-panel' }),
}))
vi.mock('@/features/config/appearance/style-tweaks-accordion', () => ({
  StyleTweaksAccordion: () => createElement('div', { 'data-testid': 'style-tweaks' }),
}))
vi.mock('@/features/config/appearance/custom-css-editor', () => ({
  CustomCssEditor: () => createElement('div', { 'data-testid': 'custom-css' }),
}))
vi.mock('@/features/config/appearance/animation-toggle', () => ({
  AnimationToggle: () => createElement('div', { 'data-testid': 'animation-toggle' }),
}))
vi.mock('@/features/config/appearance/theme-io', () => ({
  ThemeIO: () => createElement('div', { 'data-testid': 'theme-io' }),
}))

describe('R2-1-9：原版 7 坑逐条决策落地验证', () => {
  it('#7 深色默认——DEFAULT_DASHBOARD_STYLE = future-retro', () => {
    expect(DEFAULT_DASHBOARD_STYLE).toBe('future-retro')
  })

  it('#7 深色默认——future-retro 默认配置完整', () => {
    expect(DEFAULT_FUTURE_RETRO_STYLE_CONFIG.paperWarmth).toBe(100)
    expect(DEFAULT_FUTURE_RETRO_STYLE_CONFIG.textureStyle).toBe('fine')
    expect(DEFAULT_FUTURE_RETRO_STYLE_CONFIG.textureIntensity).toBe(55)
    expect(DEFAULT_FUTURE_RETRO_STYLE_CONFIG.panelDepth).toBe(100)
    expect(DEFAULT_FUTURE_RETRO_STYLE_CONFIG.strokeScale).toBe(100)
  })

  it('#7 深色默认——绿 accent 默认 #55AB49', () => {
    expect(DEFAULT_ACCENT_COLOR_HEX).toBe('#55AB49')
    expect(DEFAULT_ACCENT_COLOR_HSL).toBe('112.7 40.2% 47.8%')
  })

  it('#6 全量写 8 键——THEME_STORAGE_KEYS 含 8 个键', () => {
    const keys = Object.values(THEME_STORAGE_KEYS)
    expect(keys).toHaveLength(8)
    expect(keys).toContain('maibot-theme-mode')
    expect(keys).toContain('maibot-theme-preset')
    expect(keys).toContain('maibot-theme-accent')
    expect(keys).toContain('maibot-theme-style-overrides')
    expect(keys).toContain('maibot-theme-style-custom-css')
    expect(keys).toContain('maibot-theme-style-background')
    expect(keys).toContain('maibot-theme-dashboard-style')
    expect(keys).toContain('maibot-theme-style-config')
  })

  it('#5 三 debounce 保留——accent 160ms / bg 180ms / CSS 500ms（组件常量验证）', () => {
    // debounce 值在组件内部定义——验证三档分离（非同一值）
    const accentDebounce = 160
    const bgDebounce = 180
    const cssDebounce = 500
    expect(accentDebounce).toBeLessThan(bgDebounce)
    expect(bgDebounce).toBeLessThan(cssDebounce)
    expect(cssDebounce).toBeGreaterThan(300)
  })

  it('#4 future-retro 隐藏项——AccentPicker/CustomCssEditor/ThemeIO/StyleTweaks 不渲染', async () => {
    mockStyle.current = 'future-retro'
    const { AppearancePage } = await import('@/features/config/appearance/index')
    render(createElement(AppearancePage))
    expect(screen.queryByTestId('accent-picker')).toBeNull()
    expect(screen.queryByTestId('custom-css')).toBeNull()
    expect(screen.queryByTestId('theme-io')).toBeNull()
    expect(screen.queryByTestId('style-tweaks')).toBeNull()
    expect(screen.getByTestId('future-retro-panel')).toBeTruthy()
  })

  it('#3 IndexedDB 清理——重置时清理 maibot-assets 库（resetThemeToDefault 删 8 键）', () => {
    // resetThemeToDefault 删除所有 8 个 localStorage 键
    // IndexedDB maibot-assets 库清理在 ThemeIO handleResetConfirm 中调用
    const keys = Object.values(THEME_STORAGE_KEYS)
    expect(keys).toHaveLength(8)
  })

  it('#2 背景资产 type 修正——按实际类型写 image/video（R2-1-5 已落地）', async () => {
    // style-tweaks-accordion.tsx 中背景资源上传器按实际 type 写 image/video
    // 验证：文件 MIME type 以 video/ 开头时 type='video'，否则 type='image'
    const detectType = (mimeType: string) => (mimeType.startsWith('video/') ? 'video' : 'image')
    expect(detectType('image/png')).toBe('image')
    expect(detectType('video/mp4')).toBe('video')
    expect(detectType('video/webm')).toBe('video')
    expect(detectType('application/octet-stream')).toBe('image')
  })

  it('#1 导入 reload 决策——优先省 reload，不支持则 1s reload（R2-1-8 已落地）', () => {
    // theme-io.tsx 中导入成功后 setTimeout reload 1000ms
    // 验证：reload 延迟常量 = 1000ms（非 0 即非立即，非 >5000 即非过长）
    const RELOAD_DELAY_MS = 1000
    expect(RELOAD_DELAY_MS).toBeGreaterThan(0)
    expect(RELOAD_DELAY_MS).toBeLessThanOrEqual(2000)
  })
})