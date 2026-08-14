/**
 * biz 组件测试（P2-B：data-table.tsx 已删除——零生产引用，通用表格不贴业务，表格手写为域内风格）
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatCard } from '@/components/biz/stat-card'
import { FormField } from '@/components/biz/form-field'

describe('StatCard', () => {
  it('渲染基本属性', () => {
    render(
      <StatCard
        title="在线用户"
        value={42}
        unit="人"
        description="较昨日"
      />
    )
    expect(screen.getByText('在线用户')).toBeTruthy()
    expect(screen.getByText('42')).toBeTruthy()
    expect(screen.getByText('人')).toBeTruthy()
    expect(screen.getByText('较昨日')).toBeTruthy()
  })

  it('渲染正趋势', () => {
    render(<StatCard title="收入" value={1000} trend={15.5} />)
    expect(screen.getByText(/↑/)).toBeTruthy()
    expect(screen.getByText(/15\.5%/)).toBeTruthy()
  })

  it('渲染负趋势', () => {
    render(<StatCard title="错误" value={5} trend={-8.3} />)
    expect(screen.getByText(/↓/)).toBeTruthy()
    expect(screen.getByText(/8\.3%/)).toBeTruthy()
  })
})

describe('FormField', () => {
  it('渲染标签和子元素', () => {
    render(
      <FormField name="username" label="用户名">
        <input type="text" />
      </FormField>
    )
    expect(screen.getByText('用户名')).toBeTruthy()
    expect(screen.getByRole('textbox')).toBeTruthy()
  })

  it('必填标记', () => {
    render(
      <FormField name="email" label="邮箱" required>
        <input type="email" />
      </FormField>
    )
    expect(screen.getByText('*')).toBeTruthy()
  })

  it('高级标记', () => {
    render(
      <FormField name="timeout" label="超时" advanced>
        <input type="number" />
      </FormField>
    )
    expect(screen.getByText('高级')).toBeTruthy()
  })

  it('错误提示', () => {
    render(
      <FormField name="pass" label="密码" error="密码至少 8 位">
        <input type="password" />
      </FormField>
    )
    expect(screen.getByText('密码至少 8 位')).toBeTruthy()
  })

  it('提示文本', () => {
    render(
      <FormField name="nick" label="昵称" hint="2-20 个字符">
        <input type="text" />
      </FormField>
    )
    expect(screen.getByText('2-20 个字符')).toBeTruthy()
  })
})