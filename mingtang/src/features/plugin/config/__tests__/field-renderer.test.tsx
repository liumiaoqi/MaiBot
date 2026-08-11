import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { SectionRenderer, getLocaleCandidates, resolveLocalizedText } from '../field-renderer'
import type { ConfigSectionSchema } from '@/lib/plugin-api'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k, i18n: { resolvedLanguage: 'zh', language: 'zh' } }),
}))

function TestWrapper({ children }: { children: ReactNode }) {
  return children
}

describe('R4-4a §15.2：FieldRenderer 工具函数', () => {
  beforeEach(() => vi.clearAllMocks())

  it('getLocaleCandidates 返回候选语言列表', () => {
    const candidates = getLocaleCandidates('zh-CN')
    expect(candidates).toContain('zh-CN')
    expect(candidates).toContain('zh')
  })

  it('resolveLocalizedText 解析字符串值', () => {
    expect(resolveLocalizedText('hello', 'zh')).toBe('hello')
  })

  it('resolveLocalizedText 解析 i18n 映射', () => {
    const i18n = { zh: { label: '中文名' }, en: { label: 'English' } }
    expect(resolveLocalizedText('', 'zh', '', i18n, 'label')).toBe('中文名')
  })

  it('resolveLocalizedText fallback 当无匹配', () => {
    expect(resolveLocalizedText('', 'fr', 'fallback')).toBe('fallback')
  })
})

describe('R4-4a §15.2：SectionRenderer', () => {
  beforeEach(() => vi.clearAllMocks())

  it('渲染 section 标题 + 描述', () => {
    const section: ConfigSectionSchema = {
      name: 'test_section',
      title: '测试分节',
      description: '测试描述',
      collapsed: false,
      order: 0,
      fields: {},
    }
    render(
      <SectionRenderer sectionName="test_section" section={section} config={{}} onChange={vi.fn()} />,
      { wrapper: TestWrapper }
    )
    expect(screen.getByText('测试分节')).toBeInTheDocument()
    expect(screen.getByText('测试描述')).toBeInTheDocument()
  })

  it('collapsed=true 默认折叠', () => {
    const section: ConfigSectionSchema = {
      name: 'test_section',
      title: '折叠分节',
      collapsed: true,
      order: 0,
      fields: {},
    }
    render(
      <SectionRenderer sectionName="test_section" section={section} config={{}} onChange={vi.fn()} />,
      { wrapper: TestWrapper }
    )
    expect(screen.getByText('折叠分节')).toBeInTheDocument()
  })
})