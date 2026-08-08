import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AnimationToggle } from '../animation-toggle'

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

describe('R2-1-7：AnimationToggle 动效设置', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('no-animations')
  })

  it('渲染 Switch"启用动画"', () => {
    render(<AnimationToggle />)
    expect(screen.getByTestId('animation-toggle-switch')).toBeInTheDocument()
    expect(screen.getByText('settings.appearance.enableAnimations')).toBeInTheDocument()
  })

  it('默认开时无 no-animations class', () => {
    render(<AnimationToggle />)
    expect(document.documentElement.classList.contains('no-animations')).toBe(false)
  })

  it('关时 documentElement 加 no-animations class', () => {
    render(<AnimationToggle />)
    const toggle = screen.getByTestId('animation-toggle-switch') as HTMLInputElement
    fireEvent.click(toggle)
    expect(document.documentElement.classList.contains('no-animations')).toBe(true)
  })

  it('开时 documentElement 移除 no-animations class', () => {
    document.documentElement.classList.add('no-animations')
    render(<AnimationToggle />)
    const toggle = screen.getByTestId('animation-toggle-switch') as HTMLInputElement
    // 默认关（有 no-animations class），点一下开
    fireEvent.click(toggle)
    expect(document.documentElement.classList.contains('no-animations')).toBe(false)
  })
})