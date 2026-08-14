/**
 * TimeRangeSelector 测试（P2-C #7——补直接测试）
 *
 * 核心验证：
 * - 渲染 5 个时间范围选项（1h/6h/24h/7d/30d）
 * - 当前选中值对应按钮为高亮 variant（default）
 * - 点击其他选项触发 onChange（带对应小时数）
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { TimeRangeSelector } from '../time-range-selector'

const LABELS = ['1h', '6h', '24h', '7d', '30d']

describe('TimeRangeSelector', () => {
  it('渲染 5 个时间范围按钮', () => {
    render(<TimeRangeSelector value={24} onChange={() => {}} />)

    for (const label of LABELS) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument()
    }
  })

  it('当前选中值对应按钮为 default variant（高亮），其余为 outline', () => {
    render(<TimeRangeSelector value={24} onChange={() => {}} />)

    const selected = screen.getByRole('button', { name: '24h' })
    const other = screen.getByRole('button', { name: '6h' })
    expect(selected.className).toContain('bg-accent-9')
    expect(other.className).not.toContain('bg-accent-9')
  })

  it('点击其他选项触发 onChange（传入对应小时数）', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<TimeRangeSelector value={24} onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: '7d' }))
    expect(onChange).toHaveBeenCalledWith(168)

    await user.click(screen.getByRole('button', { name: '30d' }))
    expect(onChange).toHaveBeenCalledWith(720)

    // 点击当前选中项同样触发（切换语义不变）
    await user.click(screen.getByRole('button', { name: '24h' }))
    expect(onChange).toHaveBeenCalledWith(24)
  })
})
