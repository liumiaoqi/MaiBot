import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SearchDialog } from '@/app/layout/search-dialog'
import { settingsRegistry } from '@/settings-registry/settings-registry'

// 模拟 navigate
const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}))

// 模拟 i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'zh' },
  }),
}))

// 模拟 config-api
vi.mock('@/lib/config-api', () => ({
  getBotConfigSchema: vi.fn().mockRejectedValue(new Error('mock')),
  getModelConfigSchema: vi.fn().mockRejectedValue(new Error('mock')),
}))

// 模拟 plugin-api（dynamic 登记）
vi.mock('@/lib/config-api', () => ({
  getBotConfigSchema: vi.fn().mockRejectedValue(new Error('mock')),
  getModelConfigSchema: vi.fn().mockRejectedValue(new Error('mock')),
}))

// 模拟 prompt API
vi.mock('@/lib/agent-api', () => ({
  getPromptCatalog: vi.fn().mockResolvedValue([]),
}))

// 模拟 plugin API
vi.mock('@/lib/plugin-api', () => ({
  getPackList: vi.fn().mockResolvedValue([]),
}))

const RECENT_KEY = 'maibot-search-recent-routes'
const MAX_RECENT = 8

describe('SearchDialog', () => {
  beforeEach(() => {
    settingsRegistry.clear()
    localStorage.removeItem(RECENT_KEY)
    mockNavigate.mockClear()
  })

  afterEach(() => {
    settingsRegistry.clear()
    localStorage.removeItem(RECENT_KEY)
  })

  it('open=false 时不渲染', () => {
    render(<SearchDialog open={false} onOpenChange={vi.fn()} />)
    expect(screen.queryByPlaceholderText('search.placeholder')).toBeNull()
  })

  it('open=true 时渲染搜索输入框', () => {
    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByPlaceholderText('search.placeholder')).toBeTruthy()
  })

  it('空查询时显示开始搜索提示', () => {
    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('search.startSearch')).toBeTruthy()
  })

  it('注册表有条目时可搜索到结果', async () => {
    // 登记测试条目
    settingsRegistry.registerAll([
      {
        id: 'manual:page:/test',
        title: '测试页面',
        category: 'page',
        keywords: ['测试页面', 'test'],
        route: '/test',
        description: '测试描述',
        source: 'manual',
        order: 0,
      },
    ])

    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, '测试')

    await waitFor(() => {
      expect(screen.getByText('测试页面')).toBeTruthy()
    })
  })

  it('拼音搜索：输入 "rg" 可搜索到 "人格" 相关项', async () => {
    settingsRegistry.registerAll([
      {
        id: 'manual:page:/personality',
        title: '人格设置',
        category: 'page',
        keywords: ['人格设置', 'personality'],
        route: '/personality',
        description: '人格相关配置',
        source: 'manual',
        order: 0,
      },
    ])

    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, 'rg')

    await waitFor(() => {
      expect(screen.getByText('人格设置')).toBeTruthy()
    })
  })

  it('高亮：搜索结果 title 匹配区间有 <mark> 标签', async () => {
    settingsRegistry.registerAll([
      {
        id: 'manual:page:/highlight-test',
        title: '高亮测试',
        category: 'page',
        keywords: ['高亮测试'],
        route: '/highlight-test',
        description: '描述',
        source: 'manual',
        order: 0,
      },
    ])

    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, '高亮')

    await waitFor(() => {
      const mark = document.querySelector('mark')
      expect(mark).toBeTruthy()
      expect(mark?.textContent).toBe('高亮')
    })
  })

  it('无匹配结果时显示 noResults 提示', async () => {
    settingsRegistry.registerAll([
      {
        id: 'manual:page:/test',
        title: '测试页面',
        category: 'page',
        keywords: ['测试页面'],
        route: '/test',
        description: '描述',
        source: 'manual',
        order: 0,
      },
    ])

    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, 'xyz不存在的')

    await waitFor(() => {
      expect(screen.getByText('search.noResults')).toBeTruthy()
    })
  })

  it('去重：相同 path 的条目只保留一个', async () => {
    settingsRegistry.registerAll([
      {
        id: 'auto:bot:name',
        title: 'Bot名称',
        category: 'bot',
        keywords: ['名称', 'name'],
        route: '/config/bot',
        description: 'Bot名称字段',
        source: 'auto',
        order: 0,
      },
      {
        id: 'manual:page:/config/bot',
        title: 'Bot配置',
        category: 'page',
        keywords: ['Bot配置'],
        route: '/config/bot',
        description: 'Bot配置页面',
        source: 'manual',
        order: 1,
      },
    ])

    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, 'bot')

    await waitFor(() => {
      const buttons = screen.getAllByRole('button')
      // 去重后最多 1 条结果包含 /config/bot
      const configBotItems = buttons.filter(b => b.title?.includes('/config/bot'))
      expect(configBotItems.length).toBe(1)
    })
  })

  it('截断 slice(0, 80)：超过 80 条结果只显示 80 条', async () => {
    // 登记 100 个条目
    const entries = Array.from({ length: 100 }, (_, i) => ({
      id: `manual:page:/item-${i}`,
      title: `测试项${i}`,
      category: 'page',
      keywords: [`测试项${i}`, 'test'],
      route: `/item-${i}`,
      description: `描述${i}`,
      source: 'manual' as const,
      order: i,
    }))
    settingsRegistry.registerAll(entries)

    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, 'test')

    await waitFor(() => {
      const buttons = screen.getAllByRole('button').filter(b => b.title?.includes('/item-'))
      expect(buttons.length).toBe(80)
    })
  })

  it('键盘导航 ArrowDown/ArrowUp 移动选中索引', async () => {
    settingsRegistry.registerAll([
      {
        id: 'manual:page:/a',
        title: '项A',
        category: 'page',
        keywords: ['项A', 'test'],
        route: '/a',
        description: '描述A',
        source: 'manual',
        order: 0,
      },
      {
        id: 'manual:page:/b',
        title: '项B',
        category: 'page',
        keywords: ['项B', 'test'],
        route: '/b',
        description: '描述B',
        source: 'manual',
        order: 1,
      },
    ])

    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, 'test')

    await waitFor(() => {
      expect(screen.getByText('项A')).toBeTruthy()
    })

    // ArrowDown → 选中第二项
    fireEvent.keyDown(input, { key: 'ArrowDown' })
    const buttons = screen.getAllByRole('button').filter(b => b.title?.includes('/'))
    expect(buttons[1].className).toContain('bg-accent')

    // ArrowUp → 回到第一项
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(buttons[0].className).toContain('bg-accent')
  })

  it('键盘导航 Home/End 跳到首尾', async () => {
    settingsRegistry.registerAll([
      {
        id: 'manual:page:/a',
        title: '项A',
        category: 'page',
        keywords: ['项A', 'test'],
        route: '/a',
        description: '描述A',
        source: 'manual',
        order: 0,
      },
      {
        id: 'manual:page:/b',
        title: '项B',
        category: 'page',
        keywords: ['项B', 'test'],
        route: '/b',
        description: '描述B',
        source: 'manual',
        order: 1,
      },
      {
        id: 'manual:page:/c',
        title: '项C',
        category: 'page',
        keywords: ['项C', 'test'],
        route: '/c',
        description: '描述C',
        source: 'manual',
        order: 2,
      },
    ])

    render(<SearchDialog open={true} onOpenChange={vi.fn()} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, 'test')

    await waitFor(() => {
      expect(screen.getByText('项A')).toBeTruthy()
    })

    // End → 选中最后一项
    fireEvent.keyDown(input, { key: 'End' })
    const buttons = screen.getAllByRole('button').filter(b => b.title?.includes('/'))
    expect(buttons[buttons.length - 1].className).toContain('bg-accent')

    // Home → 回到第一项
    fireEvent.keyDown(input, { key: 'Home' })
    expect(buttons[0].className).toContain('bg-accent')
  })

  it('Enter 导航到选中项', async () => {
    settingsRegistry.registerAll([
      {
        id: 'manual:page:/enter-test',
        title: '回车测试',
        category: 'page',
        keywords: ['回车测试', 'test'],
        route: '/enter-test',
        description: '描述',
        source: 'manual',
        order: 0,
      },
    ])

    const onOpenChange = vi.fn()
    render(<SearchDialog open={true} onOpenChange={onOpenChange} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, 'test')

    await waitFor(() => {
      expect(screen.getByText('回车测试')).toBeTruthy()
    })

    fireEvent.keyDown(input, { key: 'Enter' })
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/enter-test' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('最近搜索 localStorage 保存 8 条上限', async () => {
    // 预填 10 条最近搜索
    const existing = Array.from({ length: 10 }, (_, i) => `/recent-${i}`)
    localStorage.setItem(RECENT_KEY, JSON.stringify(existing))

    settingsRegistry.registerAll([
      {
        id: 'manual:page:/new-page',
        title: '新页面',
        category: 'page',
        keywords: ['新页面', 'test'],
        route: '/new-page',
        description: '描述',
        source: 'manual',
        order: 0,
      },
    ])

    const onOpenChange = vi.fn()
    render(<SearchDialog open={true} onOpenChange={onOpenChange} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, 'test')

    await waitFor(() => {
      expect(screen.getByText('新页面')).toBeTruthy()
    })

    fireEvent.keyDown(input, { key: 'Enter' })

    const stored = JSON.parse(localStorage.getItem(RECENT_KEY) || '[]')
    expect(stored.length).toBeLessThanOrEqual(MAX_RECENT)
    expect(stored[0]).toBe('/new-page')
  })

  it('Esc 关闭对话框', async () => {
    const onOpenChange = vi.fn()
    render(<SearchDialog open={true} onOpenChange={onOpenChange} />)

    // 模拟 Esc 键
    const input = screen.getByPlaceholderText('search.placeholder')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('点击结果项导航', async () => {
    settingsRegistry.registerAll([
      {
        id: 'manual:page:/click-test',
        title: '点击测试',
        category: 'page',
        keywords: ['点击测试', 'test'],
        route: '/click-test',
        description: '描述',
        source: 'manual',
        order: 0,
      },
    ])

    const onOpenChange = vi.fn()
    render(<SearchDialog open={true} onOpenChange={onOpenChange} />)
    const input = screen.getByPlaceholderText('search.placeholder')
    await userEvent.type(input, 'test')

    await waitFor(() => {
      expect(screen.getByText('点击测试')).toBeTruthy()
    })

    const button = screen.getByText('点击测试').closest('button')
    fireEvent.click(button!)
    expect(mockNavigate).toHaveBeenCalledWith({ to: '/click-test' })
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})