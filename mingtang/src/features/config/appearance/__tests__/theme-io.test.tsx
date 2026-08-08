import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ThemeIO } from '../theme-io'

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

// 模拟 toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

describe('R2-1-8：ThemeIO 主题导入/导出/重置', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('渲染导出 + 导入 + 重置按钮', () => {
    render(<ThemeIO />)
    expect(screen.getByTestId('theme-export-btn')).toBeInTheDocument()
    expect(screen.getByTestId('theme-import-btn')).toBeInTheDocument()
    expect(screen.getByTestId('theme-reset-btn')).toBeInTheDocument()
  })

  it('重置按钮 → AlertDialog 二次确认', () => {
    render(<ThemeIO />)
    fireEvent.click(screen.getByTestId('theme-reset-btn'))
    expect(screen.getByTestId('theme-reset-dialog')).toBeInTheDocument()
    expect(screen.getByTestId('theme-reset-confirm')).toBeInTheDocument()
    expect(screen.getByTestId('theme-reset-cancel')).toBeInTheDocument()
  })

  it('重置确认 → 删 8 键', () => {
    localStorage.setItem('maibot-theme-mode', 'dark')
    localStorage.setItem('maibot-theme-preset', 'dark')
    localStorage.setItem('maibot-theme-accent', '0 0% 0%')
    localStorage.setItem('maibot-theme-style-overrides', '{}')
    localStorage.setItem('maibot-theme-style-custom-css', '{}')
    localStorage.setItem('maibot-theme-style-background', '{}')
    localStorage.setItem('maibot-theme-dashboard-style', 'modern')
    localStorage.setItem('maibot-theme-style-config', '{}')
    render(<ThemeIO />)
    fireEvent.click(screen.getByTestId('theme-reset-btn'))
    fireEvent.click(screen.getByTestId('theme-reset-confirm'))
    expect(localStorage.getItem('maibot-theme-mode')).toBeNull()
    expect(localStorage.getItem('maibot-theme-preset')).toBeNull()
    expect(localStorage.getItem('maibot-theme-accent')).toBeNull()
    expect(localStorage.getItem('maibot-theme-style-overrides')).toBeNull()
    expect(localStorage.getItem('maibot-theme-style-custom-css')).toBeNull()
    expect(localStorage.getItem('maibot-theme-style-background')).toBeNull()
    expect(localStorage.getItem('maibot-theme-dashboard-style')).toBeNull()
    expect(localStorage.getItem('maibot-theme-style-config')).toBeNull()
  })

  it('重置取消 → 不删键', () => {
    localStorage.setItem('maibot-theme-mode', 'dark')
    render(<ThemeIO />)
    fireEvent.click(screen.getByTestId('theme-reset-btn'))
    fireEvent.click(screen.getByTestId('theme-reset-cancel'))
    expect(localStorage.getItem('maibot-theme-mode')).toBe('dark')
  })
})