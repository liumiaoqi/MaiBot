/**
 * AccentPanel 测试（R4-1-2-3 测试先行）
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { AccentPanel } from '../accent-panel'

describe('AccentPanel 面板容器', () => {
  it('渲染 children', () => {
    render(
      <AccentPanel>
        <span>面板内容</span>
      </AccentPanel>
    )

    expect(screen.getByText('面板内容')).toBeInTheDocument()
  })

  it('data-dashboard-accent-panel 标记存在', () => {
    const { container } = render(<AccentPanel>内容</AccentPanel>)
    expect(container.querySelector('[data-dashboard-accent-panel="true"]')).toBeTruthy()
  })

  it('showRetroStripes=false 时不渲染条纹', () => {
    const { container } = render(<AccentPanel showRetroStripes={false}>内容</AccentPanel>)
    expect(container.querySelector('[data-retro-stripes="false"]')).toBeTruthy()
  })
})