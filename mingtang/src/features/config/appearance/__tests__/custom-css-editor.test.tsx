import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CustomCssEditor } from '../custom-css-editor'
import { THEME_STORAGE_KEYS } from '@/lib/theme/storage'

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

describe('R2-1-6：CustomCssEditor 自定义 CSS 编辑器', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('渲染 CodeEditor + 清除按钮 + 黄色警告区', () => {
    render(<CustomCssEditor />)
    expect(screen.getByTestId('custom-css-textarea')).toBeInTheDocument()
    expect(screen.getByTestId('custom-css-clear')).toBeInTheDocument()
    expect(screen.getByTestId('custom-css-warnings')).toBeInTheDocument()
  })

  it('编辑 CSS → 500ms debounce 后保存原文', async () => {
    render(<CustomCssEditor />)
    const textarea = screen.getByTestId('custom-css-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '.test { color: red; }' } })
    expect(localStorage.getItem(THEME_STORAGE_KEYS.STYLE_CUSTOM_CSS)).toBeNull()
    await waitFor(() => {
      expect(localStorage.getItem(THEME_STORAGE_KEYS.STYLE_CUSTOM_CSS)).not.toBeNull()
    }, { timeout: 800 })
  })

  it('sanitize 即时警告列表（不安全 CSS 警告）', () => {
    render(<CustomCssEditor />)
    const textarea = screen.getByTestId('custom-css-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '@import url("https://evil.com/style.css");' } })
    const warnings = screen.getByTestId('custom-css-warnings')
    expect(warnings.textContent).not.toBe('')
  })

  it('清除按钮 → CSS 清空', () => {
    render(<CustomCssEditor />)
    const textarea = screen.getByTestId('custom-css-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '.test { color: red; }' } })
    fireEvent.click(screen.getByTestId('custom-css-clear'))
    expect(textarea.value).toBe('')
  })

  it('安全 CSS 无警告', () => {
    render(<CustomCssEditor />)
    const textarea = screen.getByTestId('custom-css-textarea') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '.test { color: red; }' } })
    const warnings = screen.getByTestId('custom-css-warnings')
    expect(warnings.textContent).toBe('')
  })
})