import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { SecretStateField } from '../secret-state-field'

const { languageRef } = vi.hoisted(() => ({ languageRef: { current: 'zh-CN' } }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: languageRef.current } }),
}))

describe('C · 秘密字段三态渲染：**必须可区分**', () => {
  it('三态各有不同文案与不同的 data-secret-state（不许塌成同一个空输入框）', () => {
    render(
      <>
        <SecretStateField path="p.literal" state="configured-literal" value="" />
        <SecretStateField path="p.reference" state="configured-reference" value="" />
        <SecretStateField path="p.unset" state="unset" value="" />
      </>,
    )

    expect(screen.getByTestId('secret-state-p.literal')).toHaveTextContent('已配置')
    expect(screen.getByTestId('secret-state-p.reference')).toHaveTextContent('已配置（环境变量引用）')
    expect(screen.getByTestId('secret-state-p.unset')).toHaveTextContent('未设置')

    // 属性是给测试/自动化用的硬信号：三态取值互不相同
    expect(screen.getByTestId('secret-field-p.literal')).toHaveAttribute(
      'data-secret-state',
      'configured-literal',
    )
    expect(screen.getByTestId('secret-field-p.reference')).toHaveAttribute(
      'data-secret-state',
      'configured-reference',
    )
    expect(screen.getByTestId('secret-field-p.unset')).toHaveAttribute('data-secret-state', 'unset')
  })

  it('三态的提示语也各不相同（解释"为什么看不到值"）', () => {
    render(
      <>
        <SecretStateField path="a" state="configured-literal" value="" />
        <SecretStateField path="b" state="configured-reference" value="" />
        <SecretStateField path="c" state="unset" value="" />
      </>,
    )

    const hints = ['a', 'b', 'c'].map(
      (path) => screen.getByTestId(`secret-input-${path}`).getAttribute('placeholder'),
    )
    expect(new Set(hints).size).toBe(3)
    expect(hints[0]).toContain('留空表示不修改')
    expect(hints[2]).toContain('尚未配置')
  })

  it('输入框恒为 password（前端不持有真值，这个框是"写新值"的入口）', () => {
    render(<SecretStateField path="p" state="configured-literal" value="" />)
    expect(screen.getByTestId('secret-input-p')).toHaveAttribute('type', 'password')
  })

  it('文案走 LocalizedText：语言变了文案跟着变（不是写死的中文串）', () => {
    languageRef.current = 'en-US'
    try {
      render(<SecretStateField path="p" state="configured-literal" value="" />)
      expect(screen.getByTestId('secret-state-p')).toHaveTextContent('Configured')
    } finally {
      languageRef.current = 'zh-CN'
    }
  })

  it('没有 onChange ⇒ 字段 disabled（不假装能编辑）', () => {
    render(<SecretStateField path="p" state="unset" value="" />)
    expect(screen.getByTestId('secret-input-p')).toBeDisabled()
  })

  it('输入回调带上新值', () => {
    const onChange = vi.fn()
    render(<SecretStateField path="p" state="unset" value="" onChange={onChange} />)

    fireEvent.change(screen.getByTestId('secret-input-p'), { target: { value: 'sk-NEW' } })

    expect(onChange).toHaveBeenCalledWith('sk-NEW')
  })

  it('后端拒绝的原文要**显示出来**（认领被拒不能吞）', () => {
    render(
      <SecretStateField
        path="p"
        state="unset"
        value=""
        error="秘密占位认领失败：占位指向的位置没有值（set: false）"
      />,
    )

    expect(screen.getByTestId('secret-error-p')).toHaveTextContent('秘密占位认领失败')
    expect(screen.getByTestId('secret-input-p')).toHaveAttribute('aria-invalid', 'true')
  })
})
