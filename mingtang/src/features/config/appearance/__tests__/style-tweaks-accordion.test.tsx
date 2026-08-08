import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StyleTweaksAccordion } from '../style-tweaks-accordion'

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

describe('R2-1-5：StyleTweaksAccordion 样式微调手风琴（modern）', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('渲染五组 Accordion（typography/visual/layout/animation/backgrounds）', () => {
    render(<StyleTweaksAccordion />)
    expect(screen.getByTestId('accordion-group-typography')).toBeInTheDocument()
    expect(screen.getByTestId('accordion-group-visual')).toBeInTheDocument()
    expect(screen.getByTestId('accordion-group-layout')).toBeInTheDocument()
    expect(screen.getByTestId('accordion-group-animation')).toBeInTheDocument()
    expect(screen.getByTestId('accordion-group-backgrounds')).toBeInTheDocument()
  })

  it('每组有"恢复默认"按钮', () => {
    render(<StyleTweaksAccordion />)
    expect(screen.getByTestId('reset-typography')).toBeInTheDocument()
    expect(screen.getByTestId('reset-visual')).toBeInTheDocument()
    expect(screen.getByTestId('reset-layout')).toBeInTheDocument()
    expect(screen.getByTestId('reset-animation')).toBeInTheDocument()
    expect(screen.getByTestId('reset-backgrounds')).toBeInTheDocument()
  })

  it('typography：字体系列 +) + 基础字号 12-20px + 行高', () => {
    render(<StyleTweaksAccordion />)
    expect(screen.getByTestId('font-family-select')).toBeInTheDocument()
    const fontSize = screen.getByTestId('font-size-slider') as HTMLInputElement
    expect(Number(fontSize.min)).toBe(12)
    expect(Number(fontSize.max)).toBe(20)
    expect(screen.getByTestId('line-height-select')).toBeInTheDocument()
  })

  it('visual：圆角 0-24px + 阴影 + 模糊 Switch', () => {
    render(<StyleTweaksAccordion />)
    const radius = screen.getByTestId('border-radius-slider') as HTMLInputElement
    expect(Number(radius.min)).toBe(0)
    expect(Number(radius.max)).toBe(24)
    expect(screen.getByTestId('shadow-select')).toBeInTheDocument()
    expect(screen.getByTestId('blur-switch')).toBeInTheDocument()
  })

  it('layout：侧边栏宽度 8-24rem step 0.5', () => {
    render(<StyleTweaksAccordion />)
    const sidebarWidth = screen.getByTestId('sidebar-width-slider') as HTMLInputElement
    expect(Number(sidebarWidth.min)).toBe(8)
    expect(Number(sidebarWidth.max)).toBe(24)
    expect(Number(sidebarWidth.step)).toBe(0.5)
  })

  it('animation：动画速度 + 全局动画开关', () => {
    render(<StyleTweaksAccordion />)
    expect(screen.getByTestId('animation-speed-select')).toBeInTheDocument()
    expect(screen.getByTestId('animation-enabled-switch')).toBeInTheDocument()
  })

  it('backgrounds：5 层 Tabs（page/sidebar/header/card/dialog）', () => {
    render(<StyleTweaksAccordion />)
    expect(screen.getByTestId('bg-tab-page')).toBeInTheDocument()
    expect(screen.getByTestId('bg-tab-sidebar')).toBeInTheDocument()
    expect(screen.getByTestId('bg-tab-header')).toBeInTheDocument()
    expect(screen.getByTestId('bg-tab-card')).toBeInTheDocument()
    expect(screen.getByTestId('bg-tab-dialog')).toBeInTheDocument()
  })

  it('backgrounds 非 page 层有继承开关', () => {
    render(<StyleTweaksAccordion />)
    fireEvent.click(screen.getByTestId('bg-tab-sidebar'))
    expect(screen.getByTestId('bg-inherit-switch')).toBeInTheDocument()
  })

  it('全局动画开关关时 documentElement 加 no-animations class', () => {
    render(<StyleTweaksAccordion />)
    const toggle = screen.getByTestId('animation-enabled-switch') as HTMLInputElement
    fireEvent.click(toggle)
    expect(document.documentElement.classList.contains('no-animations')).toBe(true)
  })

  it('全局动画开关开时 documentElement 移除 no-animations class', () => {
    document.documentElement.classList.add('no-animations')
    render(<StyleTweaksAccordion />)
    const toggle = screen.getByTestId('animation-enabled-switch') as HTMLInputElement
    // 默认开，点一下关，再点一下开
    fireEvent.click(toggle)
    fireEvent.click(toggle)
    expect(document.documentElement.classList.contains('no-animations')).toBe(false)
  })
})