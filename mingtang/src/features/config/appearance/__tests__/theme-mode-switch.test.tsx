import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ThemeModeSwitch } from '../theme-mode-switch'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'settings.appearance.light': '浅色',
        'settings.appearance.dark': '深色',
        'settings.appearance.system': '跟随系统',
      }
      return map[key] ?? key
    },
  }),
}))

// 模拟 matchMedia
const mockMatchMedia = vi.fn()
vi.stubGlobal('matchMedia', mockMatchMedia)

function setupMatchMedia(dark: boolean) {
  mockMatchMedia.mockReturnValue({
    matches: dark,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })
}

describe('R2-1-1：ThemeModeSwitch 主题模式切换', () => {
  beforeEach(() => {
    localStorage.clear()
    mockMatchMedia.mockClear()
    setupMatchMedia(false)
    document.documentElement.classList.remove('dark')
  })

  it('渲染 3 个 tab 按钮（浅色/深色/跟随系统）', () => {
    render(<ThemeModeSwitch />)
    expect(screen.getByText('浅色')).toBeInTheDocument()
    expect(screen.getByText('深色')).toBeInTheDocument()
    expect(screen.getByText('跟随系统')).toBeInTheDocument()
  })

  it('无存储时默认选中深色（R2 深色默认）', () => {
    render(<ThemeModeSwitch />)
    const darkTab = screen.getByText('深色').closest('button')!
    expect(darkTab).toHaveAttribute('aria-selected', 'true')
  })

  it('无存储时 document 添加 dark 类', () => {
    render(<ThemeModeSwitch />)
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('点击浅色 → localStorage 存 light + 移除 dark 类', () => {
    render(<ThemeModeSwitch />)
    fireEvent.click(screen.getByText('浅色'))
    expect(localStorage.getItem(THEME_STORAGE_KEYS.MODE)).toBe('light')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('点击深色 → localStorage 存 dark + 添加 dark 类', () => {
    render(<ThemeModeSwitch />)
    // 先切到浅色
    fireEvent.click(screen.getByText('浅色'))
    // 再切回深色
    fireEvent.click(screen.getByText('深色'))
    expect(localStorage.getItem(THEME_STORAGE_KEYS.MODE)).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('点击跟随系统 → localStorage 存 system + 跟随系统偏好', () => {
    setupMatchMedia(true)
    render(<ThemeModeSwitch />)
    fireEvent.click(screen.getByText('跟随系统'))
    expect(localStorage.getItem(THEME_STORAGE_KEYS.MODE)).toBe('system')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
  })

  it('跟随系统 + 系统浅色 → 移除 dark 类', () => {
    setupMatchMedia(false)
    render(<ThemeModeSwitch />)
    fireEvent.click(screen.getByText('跟随系统'))
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('从 localStorage 恢复已存模式', () => {
    localStorage.setItem(THEME_STORAGE_KEYS.MODE, 'light')
    render(<ThemeModeSwitch />)
    const lightTab = screen.getByText('浅色').closest('button')!
    expect(lightTab).toHaveAttribute('aria-selected', 'true')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })

  it('非法存储值回退到深色默认', () => {
    localStorage.setItem(THEME_STORAGE_KEYS.MODE, 'bogus')
    render(<ThemeModeSwitch />)
    const darkTab = screen.getByText('深色').closest('button')!
    expect(darkTab).toHaveAttribute('aria-selected', 'true')
  })

  it('tab 按钮有 role=tab 和 data-mode 属性', () => {
    render(<ThemeModeSwitch />)
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(3)
    expect(tabs[0]).toHaveAttribute('data-mode', 'light')
    expect(tabs[1]).toHaveAttribute('data-mode', 'dark')
    expect(tabs[2]).toHaveAttribute('data-mode', 'system')
  })
})