import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AccentPicker } from '../accent-picker'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'
import { DEFAULT_ACCENT_COLOR_HEX } from '@/lib/theme/palette'

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => {
      const map: Record<string, string> = {
        'settings.appearance.accentColor': '主题色',
        'settings.appearance.accentHint': '点击色环选择或输入 HEX 值',
        'settings.appearance.resetDefault': '重置默认',
        'settings.appearance.colorPreview': '实时色板预览',
      }
      return map[key] ?? key
    },
  }),
}))

// 模拟 pipeline
const { mockApplyThemePipeline } = vi.hoisted(() => ({
  mockApplyThemePipeline: vi.fn(),
}))
vi.mock('@/lib/theme/pipeline', () => ({
  applyThemePipeline: mockApplyThemePipeline,
}))

describe('R2-1-3：AccentPicker 强调色选择', () => {
  beforeEach(() => {
    localStorage.clear()
    mockApplyThemePipeline.mockClear()
  })

  it('渲染 color input + hex 文本输入 + 恢复默认按钮 + 8 格色板预览', () => {
    render(<AccentPicker />)
    expect(screen.getByTestId('accent-color-input')).toBeInTheDocument()
    expect(screen.getByTestId('accent-hex-input')).toBeInTheDocument()
    expect(screen.getByText('重置默认')).toBeInTheDocument()
    const swatches = screen.getAllByTestId(/accent-swatch-\d/)
    expect(swatches).toHaveLength(8)
  })

  it('无存储时默认 #55AB49（绿 accent）', () => {
    render(<AccentPicker />)
    const hexInput = screen.getByTestId('accent-hex-input') as HTMLInputElement
    expect(hexInput.value).toBe(DEFAULT_ACCENT_COLOR_HEX)
  })

  it('hex 输入 → 160ms debounce 后 localStorage 保存', async () => {
    render(<AccentPicker />)
    const hexInput = screen.getByTestId('accent-hex-input') as HTMLInputElement
    fireEvent.change(hexInput, { target: { value: '#FF5733' } })
    // debounce 前不保存
    expect(localStorage.getItem(THEME_STORAGE_KEYS.ACCENT)).toBeNull()
    // debounce 后保存
    await waitFor(() => {
      expect(localStorage.getItem(THEME_STORAGE_KEYS.ACCENT)).not.toBeNull()
    }, { timeout: 300 })
  })

  it('hex 输入 → 160ms debounce 后 applyThemePipeline 调用', async () => {
    render(<AccentPicker />)
    const hexInput = screen.getByTestId('accent-hex-input') as HTMLInputElement
    fireEvent.change(hexInput, { target: { value: '#FF5733' } })
    await waitFor(() => {
      expect(mockApplyThemePipeline).toHaveBeenCalled()
    }, { timeout: 300 })
  })

  it('恢复默认按钮 → accent 回到 #55AB49', () => {
    localStorage.setItem(THEME_STORAGE_KEYS.ACCENT, '0 84.2% 60.2%')
    render(<AccentPicker />)
    fireEvent.click(screen.getByText('重置默认'))
    const hexInput = screen.getByTestId('accent-hex-input') as HTMLInputElement
    expect(hexInput.value).toBe(DEFAULT_ACCENT_COLOR_HEX)
  })

  it('hex 输入 maxLength 7', () => {
    render(<AccentPicker />)
    const hexInput = screen.getByTestId('accent-hex-input') as HTMLInputElement
    expect(hexInput.maxLength).toBe(7)
  })

  it('color input 变化 → hex 同步更新', () => {
    render(<AccentPicker />)
    const colorInput = screen.getByTestId('accent-color-input') as HTMLInputElement
    fireEvent.change(colorInput, { target: { value: '#ff0000' } })
    const hexInput = screen.getByTestId('accent-hex-input') as HTMLInputElement
    expect(hexInput.value).toBe('#FF0000')
  })

  it('从 localStorage 恢复已存 accent', () => {
    localStorage.setItem(THEME_STORAGE_KEYS.ACCENT, '0 84.2% 60.2%')
    render(<AccentPicker />)
    const hexInput = screen.getByTestId('accent-hex-input') as HTMLInputElement
    // HSL 0 84.2% 60.2% 对应约 #F33
    expect(hexInput.value).not.toBe(DEFAULT_ACCENT_COLOR_HEX)
  })

  it('8 格色板预览不可点选', () => {
    render(<AccentPicker />)
    const swatches = screen.getAllByTestId(/accent-swatch-\d/)
    swatches.forEach((s) => {
      expect(s).not.toBeInstanceOf(HTMLButtonElement)
    })
  })
})