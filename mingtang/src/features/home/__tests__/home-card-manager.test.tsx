/**
 * HomeCardManager 测试（§6.1 测试先行）
 *
 * 核心验证：
 * - 4 内置 + N 插件卡片渲染
 * - sanitizeUrl（javascript:alert(1) → 不渲染链接）
 * - localStorage 持久化
 * - 编辑模式切换
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const stableT = (key: string) => key

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: stableT }),
}))

import { HomeCardManager, type HomeCardDefinition } from '../home-card-manager'
import type { PluginHomeCard } from '@/lib/plugin-api'

function makeBuiltinCard(id: string, title: string): HomeCardDefinition {
  return {
    id,
    title,
    description: `${title} 描述`,
    source: 'builtin',
    render: () => <div data-testid={`card-${id}`}>{title}</div>,
  }
}

function makePluginCard(id: string, title: string, overrides: Partial<PluginHomeCard> = {}): PluginHomeCard {
  return {
    id,
    name: title,
    plugin_id: id,
    title,
    description: `${title} 插件描述`,
    content: `# ${title}\n插件卡片内容`,
    link_url: '',
    link_label: '打开',
    icon: 'puzzle',
    width: 'medium',
    order: 0,
    enabled: true,
    ...overrides,
  }
}

beforeEach(() => {
  localStorage.clear()
})

describe('HomeCardManager', () => {
  it('渲染 4 内置卡片', () => {
    const cards = [
      makeBuiltinCard('agent-status', '智能体状态'),
      makeBuiltinCard('chat-stream', '聊天流'),
      makeBuiltinCard('llm-overview', 'LLM 概览'),
      makeBuiltinCard('system-status', '系统状态'),
    ]

    render(<HomeCardManager cards={cards} pluginCards={[]} />)

    expect(screen.getByTestId('card-agent-status')).toBeInTheDocument()
    expect(screen.getByTestId('card-chat-stream')).toBeInTheDocument()
    expect(screen.getByTestId('card-llm-overview')).toBeInTheDocument()
    expect(screen.getByTestId('card-system-status')).toBeInTheDocument()
  })

  it('渲染插件卡片', () => {
    const pluginCards = [makePluginCard('plugin-a', '插件 A'), makePluginCard('plugin-b', '插件 B')]

    render(<HomeCardManager cards={[]} pluginCards={pluginCards} />)

    // 卡片标题 + markdown h1 都包含标题文本，用 getAllByText
    expect(screen.getAllByText('插件 A').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('插件 B').length).toBeGreaterThanOrEqual(1)
  })

  it('sanitizeUrl：javascript: 链接不渲染', () => {
    const pluginCards = [makePluginCard('evil', '恶意插件', {
      content: '[点击](javascript:alert(1))',
      link_url: 'javascript:alert(1)',
    })]

    render(<HomeCardManager cards={[]} pluginCards={pluginCards} />)

    // javascript: 链接不应渲染为 <a href="javascript:...">
    const evilLink = document.querySelector('a[href="javascript:alert(1)"]')
    expect(evilLink).toBeNull()
  })

  it('sanitizeUrl：https 链接正常渲染', () => {
    const pluginCards = [makePluginCard('safe', '安全插件', {
      link_url: 'https://example.com',
      link_label: '访问',
    })]

    render(<HomeCardManager cards={[]} pluginCards={pluginCards} />)

    const safeLink = document.querySelector('a[href="https://example.com"]')
    expect(safeLink).not.toBeNull()
  })

  it('编辑模式切换', () => {
    const cards = [makeBuiltinCard('test', '测试卡片')]

    render(<HomeCardManager cards={cards} pluginCards={[]} />)

    expect(screen.queryByText('home.cards.done')).not.toBeInTheDocument()

    const editButton = screen.getByText('home.cards.edit')
    fireEvent.click(editButton)

    // 编辑模式按钮文本切换为 done
    expect(screen.getByText('home.cards.done')).toBeInTheDocument()
    expect(screen.queryByText('home.cards.edit')).not.toBeInTheDocument()
  })

  it('localStorage 持久化布局', () => {
    const cards = [makeBuiltinCard('a', '卡片 A'), makeBuiltinCard('b', '卡片 B')]

    render(<HomeCardManager cards={cards} pluginCards={[]} />)

    // 布局应持久化到 localStorage
    const stored = JSON.parse(localStorage.getItem('maibot-home-card-layout-v1') ?? '{}')
    expect(stored.order).toContain('a')
    expect(stored.order).toContain('b')
  })
})
