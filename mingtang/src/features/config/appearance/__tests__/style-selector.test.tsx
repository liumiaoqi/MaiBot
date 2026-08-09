import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { createElement } from 'react'
import { StyleSelector } from '../style-selector'
import { ThemeProvider } from '@/app/theme-provider'
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

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'settings.appearance.styleModern': '现代',
        'settings.appearance.styleModernDesc': '保留卡片圆角背景和自定义能力',
        'settings.appearance.styleFutureRetro': '未来复古',
        'settings.appearance.styleFutureRetroDesc': '纸面颗粒、硬朗描边和切角面板',
      }
      return map[key] ?? key
    },
  }),
}))

// 模拟 config-api
const { mockUpdateBotConfigSection, mockGetBotConfig } = vi.hoisted(() => ({
  mockUpdateBotConfigSection: vi.fn(),
  mockGetBotConfig: vi.fn(),
}))
vi.mock('@/lib/config-api', () => ({
  updateBotConfigSection: mockUpdateBotConfigSection,
  getBotConfig: mockGetBotConfig,
}))

function withProvider(children: React.ReactNode) {
  return createElement(ThemeProvider, null, children)
}

describe('R2-1-2：StyleSelector 界面风格选择 + 双通道同步', () => {
  beforeEach(() => {
    localStorage.clear()
    mockUpdateBotConfigSection.mockClear()
    mockGetBotConfig.mockClear()
    mockUpdateBotConfigSection.mockResolvedValue({ success: true })
    mockGetBotConfig.mockResolvedValue({})
    delete document.documentElement.dataset.dashboardStyle
  })

  it('渲染 2 张卡片按钮（现代 / 未来复古）', () => {
    render(withProvider(createElement(StyleSelector)))
    expect(screen.getByText('现代')).toBeInTheDocument()
    expect(screen.getByText('未来复古')).toBeInTheDocument()
  })

  it('无存储时默认 future-retro（7 坑 #7）', () => {
    render(withProvider(createElement(StyleSelector)))
    const retroCard = screen.getByText('未来复古').closest('button')!
    expect(retroCard).toHaveAttribute('aria-selected', 'true')
  })

  it('无存储时 dataset.dashboardStyle = future-retro', () => {
    render(withProvider(createElement(StyleSelector)))
    expect(document.documentElement.dataset.dashboardStyle).toBe('future-retro')
  })

  it('选 modern → localStorage + 后端调用 + dataset', async () => {
    render(withProvider(createElement(StyleSelector)))
    fireEvent.click(screen.getByText('现代'))
    expect(localStorage.getItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE)).toBe('modern')
    expect(document.documentElement.dataset.dashboardStyle).toBe('modern')
    await waitFor(() => {
      expect(mockUpdateBotConfigSection).toHaveBeenCalledWith('webui', { webui_style: 'modern' })
    })
  })

  it('选 future-retro → localStorage + 后端调用 + dataset', async () => {
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')
    render(withProvider(createElement(StyleSelector)))
    fireEvent.click(screen.getByText('未来复古'))
    expect(localStorage.getItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE)).toBe('future-retro')
    expect(document.documentElement.dataset.dashboardStyle).toBe('future-retro')
    await waitFor(() => {
      expect(mockUpdateBotConfigSection).toHaveBeenCalledWith('webui', { webui_style: 'future-retro' })
    })
  })

  it('互斥选择（选一个另一个取消）', () => {
    render(withProvider(createElement(StyleSelector)))
    const modernCard = screen.getByText('现代').closest('button')!
    const retroCard = screen.getByText('未来复古').closest('button')!

    fireEvent.click(modernCard)
    expect(modernCard).toHaveAttribute('aria-selected', 'true')
    expect(retroCard).toHaveAttribute('aria-selected', 'false')

    fireEvent.click(retroCard)
    expect(retroCard).toHaveAttribute('aria-selected', 'true')
    expect(modernCard).toHaveAttribute('aria-selected', 'false')
  })

  it('从 localStorage 恢复已存风格', () => {
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'modern')
    render(withProvider(createElement(StyleSelector)))
    const modernCard = screen.getByText('现代').closest('button')!
    expect(modernCard).toHaveAttribute('aria-selected', 'true')
    expect(document.documentElement.dataset.dashboardStyle).toBe('modern')
  })

  it('非法存储值回退到 future-retro 默认', () => {
    localStorage.setItem(THEME_STORAGE_KEYS.DASHBOARD_STYLE, 'bogus')
    render(withProvider(createElement(StyleSelector)))
    const retroCard = screen.getByText('未来复古').closest('button')!
    expect(retroCard).toHaveAttribute('aria-selected', 'true')
  })

  it('卡片有 role=tab 和 data-style 属性', () => {
    render(withProvider(createElement(StyleSelector)))
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(2)
    expect(tabs[0]).toHaveAttribute('data-style', 'modern')
    expect(tabs[1]).toHaveAttribute('data-style', 'future-retro')
  })

  it('后端同步失败时 console.error 但不崩溃', async () => {
    mockUpdateBotConfigSection.mockRejectedValueOnce(new Error('网络错误'))
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(withProvider(createElement(StyleSelector)))
    fireEvent.click(screen.getByText('现代'))
    await waitFor(() => {
      expect(mockUpdateBotConfigSection).toHaveBeenCalled()
    })
    expect(spy).toHaveBeenCalled()
    spy.mockRestore()
  })
})
