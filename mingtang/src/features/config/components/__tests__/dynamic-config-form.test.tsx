import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DynamicConfigForm } from '../dynamic-config-form'
import type { ConfigSchema } from '@/types/config-schema'

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}))

const simpleSchema: ConfigSchema = {
  className: 'TestConfig',
  classDoc: '测试配置',
  fields: [
    { name: 'name', type: 'string', label: '名称', description: '名称描述', required: true },
    { name: 'count', type: 'integer', label: '数量', description: '数量描述', required: false, default: 0 },
    { name: 'enabled', type: 'boolean', label: '启用', description: '启用描述', required: false, default: true },
  ],
}

describe('R2-2-3：DynamicConfigForm schema 驱动表单引擎', () => {
  it('消费 ConfigSchema → 遍历 fields 渲染', () => {
    render(
      <DynamicConfigForm
        schema={simpleSchema}
        values={{ name: 'test', count: 1, enabled: true }}
      />
    )
    expect(screen.getByText('名称')).toBeInTheDocument()
    expect(screen.getByText('数量')).toBeInTheDocument()
    expect(screen.getByText('启用')).toBeInTheDocument()
  })

  it('无 fieldHook 字段 → 默认渲染（Input/Select/Switch）', () => {
    render(
      <DynamicConfigForm
        schema={simpleSchema}
        values={{ name: 'test', count: 1, enabled: true }}
      />
    )
    expect(screen.getByTestId('field-name')).toBeInTheDocument()
    expect(screen.getByTestId('field-count')).toBeInTheDocument()
    expect(screen.getByTestId('field-enabled')).toBeInTheDocument()
  })

  it('type: "hidden" 字段 → 跳过字段渲染', () => {
    const schema: ConfigSchema = {
      className: 'TestConfig',
      classDoc: '测试',
      fields: [
        { name: 'visible', type: 'string', label: '可见', description: '', required: true },
        { name: 'hidden', type: 'string', label: '隐藏', description: '', required: false },
      ],
    }
    render(
      <DynamicConfigForm
        schema={schema}
        values={{ visible: 'a', hidden: 'b' }}
        hiddenFields={['hidden']}
      />
    )
    expect(screen.getByTestId('field-visible')).toBeInTheDocument()
    expect(screen.queryByTestId('field-hidden')).not.toBeInTheDocument()
  })

  it('空 schema → 不渲染任何字段', () => {
    const emptySchema: ConfigSchema = {
      className: 'Empty',
      classDoc: '',
      fields: [],
    }
    const { container } = render(
      <DynamicConfigForm schema={emptySchema} values={{}} />
    )
    expect(container.querySelectorAll('[data-testid^="field-"]')).toHaveLength(0)
  })
})