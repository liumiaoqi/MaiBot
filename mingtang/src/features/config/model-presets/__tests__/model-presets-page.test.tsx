import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ModelPresetsPage } from '../index'

// 模拟 i18n——返回 key 本身便于断言
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

describe('R2-3-7：/model-presets 占位页', () => {
  it('渲染页面标题（PageShell）', () => {
    render(<ModelPresetsPage />)
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('modelPresets.title')
  })

  it('渲染虚线卡片"功能开发中"', () => {
    render(<ModelPresetsPage />)
    expect(screen.getByText('modelPresets.devTitle')).toBeInTheDocument()
    expect(screen.getByText('modelPresets.devDescription')).toBeInTheDocument()
  })

  it('渲染即将推出列表（5 项）', () => {
    render(<ModelPresetsPage />)
    expect(screen.getByText('modelPresets.upcomingTitle')).toBeInTheDocument()
    expect(screen.getByText('modelPresets.upcoming1')).toBeInTheDocument()
    expect(screen.getByText('modelPresets.upcoming2')).toBeInTheDocument()
    expect(screen.getByText('modelPresets.upcoming3')).toBeInTheDocument()
    expect(screen.getByText('modelPresets.upcoming4')).toBeInTheDocument()
    expect(screen.getByText('modelPresets.upcoming5')).toBeInTheDocument()
  })

  it('渲染 Package 图标', () => {
    const { container } = render(<ModelPresetsPage />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
  })

  it('虚线边框样式（border-dashed）', () => {
    const { container } = render(<ModelPresetsPage />)
    const dashedBorder = container.querySelector('.border-dashed')
    expect(dashedBorder).toBeInTheDocument()
  })

  it('无 API 调用——不引入 useQuery/useMutation', () => {
    // ModelPresetsPage 是纯占位页，不消费任何 API
    // 通过检查组件源码不包含 config-api 导入来验证
    // 此测试通过渲染不报错来间接验证——无网络请求 mock 也能正常渲染
    render(<ModelPresetsPage />)
    expect(screen.getByTestId('page-shell')).toBeInTheDocument()
  })
})