import { describe, it, expect, vi } from 'vitest'
import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { DynamicConfigForm, validateFieldConstraints } from '../dynamic-config-form'
import type { ConfigSchema, FieldSchema } from '@/types/config-schema'

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

/** 取字段的输入控件——`data-testid=field-<name>` 内唯一的 input */
function inputOf(name: string): HTMLInputElement {
  const control = screen.getByTestId(`field-${name}`).querySelector('input')
  if (!(control instanceof HTMLInputElement)) {
    throw new Error(`字段 ${name} 未渲染 input 控件`)
  }
  return control
}

/** 构造字段——测试里只关心约束，其余给最小合法值 */
function field(partial: Partial<FieldSchema> & Pick<FieldSchema, 'name' | 'type'>): FieldSchema {
  return { label: partial.name, description: '', required: false, ...partial }
}

function schemaOf(...fields: FieldSchema[]): ConfigSchema {
  return { className: 'ConstraintConfig', classDoc: '约束', fields }
}

describe('R?：schema 约束消费（minValue/maxValue/minLength/maxLength/pattern）', () => {
  // === 数值上下界（含边界）===
  describe('数值字段 minValue / maxValue', () => {
    const schema = schemaOf(
      field({ name: 'ratio', type: 'number', minValue: 1, maxValue: 10 }),
    )

    it('低于下界 → 越界被拦下并给出可读提示', () => {
      render(<DynamicConfigForm schema={schema} values={{ ratio: 0.5 }} />)
      expect(screen.getByTestId('field-error-ratio')).toHaveTextContent('值不能小于 1')
      expect(inputOf('ratio')).toHaveAttribute('aria-invalid', 'true')
    })

    it('高于上界 → 越界被拦下并给出可读提示', () => {
      render(<DynamicConfigForm schema={schema} values={{ ratio: 99 }} />)
      expect(screen.getByTestId('field-error-ratio')).toHaveTextContent('值不能大于 10')
    })

    it('等于下界 / 等于上界 → 含边界，不报错', () => {
      const { unmount } = render(<DynamicConfigForm schema={schema} values={{ ratio: 1 }} />)
      expect(screen.queryByTestId('field-error-ratio')).not.toBeInTheDocument()
      unmount()

      render(<DynamicConfigForm schema={schema} values={{ ratio: 10 }} />)
      expect(screen.queryByTestId('field-error-ratio')).not.toBeInTheDocument()
    })

    it('HTML 侧同时下发 min / max（浏览器兜底）', () => {
      render(<DynamicConfigForm schema={schema} values={{ ratio: 5 }} />)
      expect(inputOf('ratio')).toHaveAttribute('min', '1')
      expect(inputOf('ratio')).toHaveAttribute('max', '10')
    })

    it('字符串形态的数值同样判定（沿用旧前端 parseFloat 路径）', () => {
      render(<DynamicConfigForm schema={schema} values={{ ratio: '42' }} />)
      expect(screen.getByTestId('field-error-ratio')).toHaveTextContent('值不能大于 10')
    })

    it('未填 / 空串 / 脏值 → 不误报范围错误', () => {
      const { unmount } = render(<DynamicConfigForm schema={schema} values={{ ratio: undefined }} />)
      expect(screen.queryByTestId('field-error-ratio')).not.toBeInTheDocument()
      unmount()

      const { unmount: unmount2 } = render(<DynamicConfigForm schema={schema} values={{ ratio: '' }} />)
      expect(screen.queryByTestId('field-error-ratio')).not.toBeInTheDocument()
      unmount2()

      render(<DynamicConfigForm schema={schema} values={{ ratio: 'abc' }} />)
      expect(screen.queryByTestId('field-error-ratio')).not.toBeInTheDocument()
    })
  })

  // === 约束为 0：0 是假值，不能被 if (minValue) 吞掉 ===
  describe('约束为 0（假值陷阱）', () => {
    it('minValue: 0 → min 属性照常下发', () => {
      render(
        <DynamicConfigForm
          schema={schemaOf(field({ name: 'workers', type: 'integer', minValue: 0 }))}
          values={{ workers: 0 }}
        />
      )
      expect(inputOf('workers')).toHaveAttribute('min', '0')
    })

    it('minValue: 0 → 0 合法、-1 越界', () => {
      const schema = schemaOf(field({ name: 'workers', type: 'integer', minValue: 0 }))
      const { unmount } = render(<DynamicConfigForm schema={schema} values={{ workers: 0 }} />)
      expect(screen.queryByTestId('field-error-workers')).not.toBeInTheDocument()
      unmount()

      render(<DynamicConfigForm schema={schema} values={{ workers: -1 }} />)
      expect(screen.getByTestId('field-error-workers')).toHaveTextContent('值不能小于 0')
    })

    it('maxValue: 0 → 0 合法、1 越界', () => {
      const schema = schemaOf(field({ name: 'retry', type: 'integer', maxValue: 0 }))
      const { unmount } = render(<DynamicConfigForm schema={schema} values={{ retry: 0 }} />)
      expect(screen.queryByTestId('field-error-retry')).not.toBeInTheDocument()
      unmount()

      render(<DynamicConfigForm schema={schema} values={{ retry: 1 }} />)
      expect(screen.getByTestId('field-error-retry')).toHaveTextContent('值不能大于 0')
    })
  })

  // === 字符串长度 ===
  describe('字符串字段 minLength / maxLength', () => {
    const schema = schemaOf(
      field({ name: 'code', type: 'string', minLength: 2, maxLength: 4 }),
    )

    it('短于 minLength → 提示可读', () => {
      render(<DynamicConfigForm schema={schema} values={{ code: 'a' }} />)
      expect(screen.getByTestId('field-error-code')).toHaveTextContent('长度不能少于 2 个字符')
    })

    it('长于 maxLength → 提示可读', () => {
      render(<DynamicConfigForm schema={schema} values={{ code: 'abcde' }} />)
      expect(screen.getByTestId('field-error-code')).toHaveTextContent('长度不能超过 4 个字符')
    })

    it('等于 minLength / 等于 maxLength → 含边界，不报错', () => {
      const { unmount } = render(<DynamicConfigForm schema={schema} values={{ code: 'ab' }} />)
      expect(screen.queryByTestId('field-error-code')).not.toBeInTheDocument()
      unmount()

      render(<DynamicConfigForm schema={schema} values={{ code: 'abcd' }} />)
      expect(screen.queryByTestId('field-error-code')).not.toBeInTheDocument()
    })

    it('HTML 侧同时下发 minlength / maxlength', () => {
      render(<DynamicConfigForm schema={schema} values={{ code: 'ab' }} />)
      expect(inputOf('code')).toHaveAttribute('minlength', '2')
      expect(inputOf('code')).toHaveAttribute('maxlength', '4')
    })

    it('maxLength: 0 → 空串合法、非空越界（0 不被吞掉）', () => {
      const schema = schemaOf(field({ name: 'tag', type: 'string', maxLength: 0 }))
      const { unmount } = render(<DynamicConfigForm schema={schema} values={{ tag: '' }} />)
      expect(screen.queryByTestId('field-error-tag')).not.toBeInTheDocument()
      unmount()

      render(<DynamicConfigForm schema={schema} values={{ tag: 'x' }} />)
      expect(screen.getByTestId('field-error-tag')).toHaveTextContent('长度不能超过 0 个字符')
    })

    it('非字符串值 → 不做长度判定（留给后端）', () => {
      render(<DynamicConfigForm schema={schema} values={{ code: 123 }} />)
      expect(screen.queryByTestId('field-error-code')).not.toBeInTheDocument()
    })
  })

  // === pattern ===
  describe('字符串字段 pattern', () => {
    it('不匹配 → 提示可读并回显正则', () => {
      render(
        <DynamicConfigForm
          schema={schemaOf(field({ name: 'slug', type: 'string', pattern: '^[a-z]+$' }))}
          values={{ slug: 'ABC' }}
        />
      )
      expect(screen.getByTestId('field-error-slug')).toHaveTextContent('格式不符合要求：^[a-z]+$')
    })

    it('匹配 → 不报错，且 HTML 侧下发 pattern', () => {
      render(
        <DynamicConfigForm
          schema={schemaOf(field({ name: 'slug', type: 'string', pattern: '^[a-z]+$' }))}
          values={{ slug: 'abc' }}
        />
      )
      expect(screen.queryByTestId('field-error-slug')).not.toBeInTheDocument()
      expect(inputOf('slug')).toHaveAttribute('pattern', '^[a-z]+$')
    })

    it('按 pydantic 的 search 语义判定（`\\d+` 接受 abc123），不做整串锚定', () => {
      render(
        <DynamicConfigForm
          schema={schemaOf(field({ name: 'mixed', type: 'string', pattern: '\\d+' }))}
          values={{ mixed: 'abc123' }}
        />
      )
      expect(screen.queryByTestId('field-error-mixed')).not.toBeInTheDocument()
    })

    it('非法正则 → 不抛异常、不把用户拦死', () => {
      render(
        <DynamicConfigForm
          schema={schemaOf(field({ name: 'broken', type: 'string', pattern: '[' }))}
          values={{ broken: 'whatever' }}
        />
      )
      expect(screen.getByTestId('field-broken')).toBeInTheDocument()
      expect(screen.queryByTestId('field-error-broken')).not.toBeInTheDocument()
    })
  })

  // === 无约束字段：行为必须与接入约束前完全一致（防过度设计）===
  describe('未提供约束的字段行为不变', () => {
    const schema = schemaOf(
      field({ name: 'title', type: 'string', description: '标题描述' }),
      field({ name: 'weight', type: 'number' }),
    )

    it('不产生任何提示', () => {
      render(<DynamicConfigForm schema={schema} values={{ title: '随便什么值', weight: -99999 }} />)
      expect(screen.queryByTestId('field-error-title')).not.toBeInTheDocument()
      expect(screen.queryByTestId('field-error-weight')).not.toBeInTheDocument()
    })

    it('不下发任何约束属性——数值字段的 min/max 与字符串字段的长度/格式都不出现', () => {
      render(<DynamicConfigForm schema={schema} values={{ title: 'x', weight: 3 }} />)
      const numeric = inputOf('weight')
      expect(numeric).not.toHaveAttribute('min')
      expect(numeric).not.toHaveAttribute('max')
      expect(numeric).not.toHaveAttribute('minlength')
      expect(numeric).not.toHaveAttribute('maxlength')
      expect(numeric).not.toHaveAttribute('pattern')

      const text = inputOf('title')
      expect(text).not.toHaveAttribute('min')
      expect(text).not.toHaveAttribute('max')
      expect(text).not.toHaveAttribute('minlength')
      expect(text).not.toHaveAttribute('maxlength')
      expect(text).not.toHaveAttribute('pattern')
      expect(text).not.toHaveAttribute('aria-invalid')
    })

    it('原有 DOM 结构保持（label + input + description）', () => {
      render(<DynamicConfigForm schema={schema} values={{ title: 'x' }} />)
      expect(screen.getByText('标题描述')).toBeInTheDocument()
      expect(inputOf('title')).toHaveValue('x')
      expect(inputOf('title')).toHaveAttribute('type', 'text')
    })
  })

  // === 纯函数直测（表驱动）===
  describe('validateFieldConstraints 纯函数', () => {
    it('无约束 ⇒ 恒返回空串', () => {
      const bare = field({ name: 'n', type: 'number' })
      const bareString = field({ name: 's', type: 'string' })
      expect(validateFieldConstraints(bare, -99999)).toBe('')
      expect(validateFieldConstraints(bareString, '随便什么很长很长的值')).toBe('')
    })

    it('整数下界含边界', () => {
      const bounded = field({ name: 'n', type: 'integer', minValue: 2, maxValue: 8 })
      expect(validateFieldConstraints(bounded, 1)).toBe('值不能小于 2')
      expect(validateFieldConstraints(bounded, 2)).toBe('')
      expect(validateFieldConstraints(bounded, 8)).toBe('')
      expect(validateFieldConstraints(bounded, 9)).toBe('值不能大于 8')
    })

    it('非有限值不做范围判定（沿用旧前端 Number.isFinite 守卫）', () => {
      const bounded = field({ name: 'n', type: 'number', minValue: 1, maxValue: 10 })
      expect(validateFieldConstraints(bounded, undefined)).toBe('')
      expect(validateFieldConstraints(bounded, null)).toBe('')
      expect(validateFieldConstraints(bounded, '')).toBe('')
      expect(validateFieldConstraints(bounded, 'abc')).toBe('')
      expect(validateFieldConstraints(bounded, NaN)).toBe('')
      expect(validateFieldConstraints(bounded, Infinity)).toBe('')
    })

    it('字符串字段不消费数值约束', () => {
      const mixed = field({ name: 's', type: 'string', minValue: 5, maxValue: 10 })
      expect(validateFieldConstraints(mixed, 'a')).toBe('')
    })
  })
})

// ============================================================================
// task-8：受控渲染 + 真实约束字段的端到端判定
// ============================================================================

/** 受控宿主——模拟页面持有 `values` 的真实用法（编辑 → state → 回流到受控 input） */
function ControlledHarness({
  schema,
  initial = {},
}: {
  schema: ConfigSchema
  initial?: Record<string, unknown>
}) {
  const [values, setValues] = useState<Record<string, unknown>>(initial)
  return (
    <>
      <DynamicConfigForm
        schema={schema}
        values={values}
        onChange={(field, value) => setValues((prev) => ({ ...prev, [field]: value }))}
      />
      <output data-testid="draft-readout">{JSON.stringify(values)}</output>
    </>
  )
}

/** 从读数里取当前草稿（断言"编辑真的进了 state"，而不是只看 DOM 显示） */
function draft(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId('draft-readout').textContent ?? '{}') as Record<string, unknown>
}

/**
 * 以下两个字段**逐字取自后端** `GET /api/webui/config/schema/bot`（2026-10-16 容器内 dump）。
 * 用真实字段做夹具而不是编一个：`ascii_column_width` 是 32–80 的**整数**，
 * `multiple_probability` 的 `minValue` 就是 **0**（全库 44 个字段如此）——"0 不是假值"在真数据里是常态。
 */
const REAL_ASCII_COLUMN_WIDTH: FieldSchema = {
  name: 'ascii_column_width',
  type: 'integer',
  label: { zh_CN: 'ASCII 列宽' },
  description: 'ASCII 文本列宽（范围 32-80）。',
  required: false,
  default: 48,
  minValue: 32,
  maxValue: 80,
}

const REAL_MULTIPLE_PROBABILITY: FieldSchema = {
  name: 'multiple_probability',
  type: 'number',
  label: { zh_CN: '临时风格注入概率' },
  description: '随机启用备用风格的概率；0 表示不随机切换。',
  required: false,
  default: 0,
  minValue: 0,
  maxValue: 1,
}

describe('R?：受控渲染 + 端到端约束判定（task-8）', () => {
  describe('核心判据：真填越界值 ⇒ 看到约束提示', () => {
    it('真填 999（> max 80）→ 提示出现、且值真的进了 state', () => {
      render(<ControlledHarness schema={schemaOf(REAL_ASCII_COLUMN_WIDTH)} initial={{ ascii_column_width: 48 }} />)
      expect(screen.queryByTestId('field-error-ascii_column_width')).not.toBeInTheDocument()

      fireEvent.change(inputOf('ascii_column_width'), { target: { value: '999' } })

      expect(screen.getByTestId('field-error-ascii_column_width')).toHaveTextContent('值不能大于 80')
      expect(draft().ascii_column_width).toBe(999)
      expect(inputOf('ascii_column_width')).toHaveValue(999)
    })

    it('真填 31（< min 32）→ 提示出现', () => {
      render(<ControlledHarness schema={schemaOf(REAL_ASCII_COLUMN_WIDTH)} initial={{ ascii_column_width: 48 }} />)
      fireEvent.change(inputOf('ascii_column_width'), { target: { value: '31' } })
      expect(screen.getByTestId('field-error-ascii_column_width')).toHaveTextContent('值不能小于 32')
    })

    it('真填边界值 32 / 80 → 不提示（含边界）', () => {
      render(<ControlledHarness schema={schemaOf(REAL_ASCII_COLUMN_WIDTH)} initial={{ ascii_column_width: 48 }} />)

      fireEvent.change(inputOf('ascii_column_width'), { target: { value: '32' } })
      expect(screen.queryByTestId('field-error-ascii_column_width')).not.toBeInTheDocument()

      fireEvent.change(inputOf('ascii_column_width'), { target: { value: '80' } })
      expect(screen.queryByTestId('field-error-ascii_column_width')).not.toBeInTheDocument()
      expect(draft().ascii_column_width).toBe(80)
    })

    it('真实 minValue: 0 的字段——-0.5 越界有提示，0 与 1 合法', () => {
      render(<ControlledHarness schema={schemaOf(REAL_MULTIPLE_PROBABILITY)} initial={{ multiple_probability: 0 }} />)

      expect(screen.queryByTestId('field-error-multiple_probability')).not.toBeInTheDocument()

      fireEvent.change(inputOf('multiple_probability'), { target: { value: '-0.5' } })
      expect(screen.getByTestId('field-error-multiple_probability')).toHaveTextContent('值不能小于 0')

      fireEvent.change(inputOf('multiple_probability'), { target: { value: '1' } })
      expect(screen.queryByTestId('field-error-multiple_probability')).not.toBeInTheDocument()
    })
  })

  describe('值解析契约（number/integer）', () => {
    it('integer 字段写入截断后的数字', () => {
      render(<ControlledHarness schema={schemaOf(REAL_ASCII_COLUMN_WIDTH)} />)
      fireEvent.change(inputOf('ascii_column_width'), { target: { value: '79.9' } })
      expect(draft().ascii_column_width).toBe(79)
      expect(inputOf('ascii_column_width')).toHaveValue(79)
    })

    it('number 字段保留小数', () => {
      render(<ControlledHarness schema={schemaOf(REAL_MULTIPLE_PROBABILITY)} />)
      fireEvent.change(inputOf('multiple_probability'), { target: { value: '0.25' } })
      expect(draft().multiple_probability).toBe(0.25)
    })

    it('清空 → 保留空串：不误报越界、也不静默变成 0', () => {
      render(<ControlledHarness schema={schemaOf(REAL_ASCII_COLUMN_WIDTH)} initial={{ ascii_column_width: 48 }} />)
      fireEvent.change(inputOf('ascii_column_width'), { target: { value: '' } })

      expect(draft().ascii_column_width).toBe('')
      expect(screen.queryByTestId('field-error-ascii_column_width')).not.toBeInTheDocument()
    })

    it('脏值不写 NaN（数字输入框里丢不进 NaN，且守卫把非有限数原样保留为字符串）', () => {
      render(<ControlledHarness schema={schemaOf(REAL_ASCII_COLUMN_WIDTH)} />)
      fireEvent.change(inputOf('ascii_column_width'), { target: { value: 'abc' } })

      // 契约：绝不落进 NaN（JSON.stringify(NaN) 会变 null，静默改语义）
      expect(typeof draft().ascii_column_width).toBe('string')
      expect(Number.isNaN(draft().ascii_column_width)).toBe(false)
      expect(screen.queryByTestId('field-error-ascii_column_width')).not.toBeInTheDocument()
    })
  })

  describe('其余控件分支同样受控', () => {
    it('string 字段原样写字符串', () => {
      render(<ControlledHarness schema={schemaOf(field({ name: 'nickname', type: 'string' }))} />)
      fireEvent.change(inputOf('nickname'), { target: { value: '麦麦' } })
      expect(draft().nickname).toBe('麦麦')
      expect(inputOf('nickname')).toHaveValue('麦麦')
    })

    it('select 字段：选中项进 state', () => {
      const selectField = field({ name: 'platform', type: 'select', options: ['qq', 'lark'] })
      render(<ControlledHarness schema={schemaOf(selectField)} initial={{ platform: 'qq' }} />)
      const control = screen.getByTestId('field-platform').querySelector('select')
      if (!(control instanceof HTMLSelectElement)) throw new Error('platform 未渲染 select')

      fireEvent.change(control, { target: { value: 'lark' } })
      expect(draft().platform).toBe('lark')
    })

    it('boolean 字段：勾选状态进 state', () => {
      render(<ControlledHarness schema={schemaOf(field({ name: 'enabled', type: 'boolean' }))} initial={{ enabled: false }} />)
      fireEvent.click(inputOf('enabled'))
      expect(draft().enabled).toBe(true)
    })

    it('textarea 字段：编辑进 state', () => {
      render(<ControlledHarness schema={schemaOf(field({ name: 'note', type: 'textarea' }))} />)
      const control = screen.getByTestId('field-note').querySelector('textarea')
      if (!(control instanceof HTMLTextAreaElement)) throw new Error('note 未渲染 textarea')

      fireEvent.change(control, { target: { value: '多行\n内容' } })
      expect(draft().note).toBe('多行\n内容')
    })
  })

  describe('未给 onChange ⇒ 字段明确不可编辑（不许静默吞输入）', () => {
    it('只给 values 不给 onChange：显示服务端值，且字段 disabled', () => {
      render(<DynamicConfigForm schema={schemaOf(REAL_ASCII_COLUMN_WIDTH)} values={{ ascii_column_width: 48 }} />)
      const control = inputOf('ascii_column_width')
      expect(control).toHaveValue(48)
      expect(control).toBeDisabled()
    })

    it('给了 onChange ⇒ 字段可编辑', () => {
      render(<ControlledHarness schema={schemaOf(REAL_ASCII_COLUMN_WIDTH)} initial={{ ascii_column_width: 48 }} />)
      expect(inputOf('ascii_column_width')).not.toBeDisabled()
    })
  })
})