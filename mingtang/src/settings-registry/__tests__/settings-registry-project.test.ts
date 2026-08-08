import { describe, it, expect } from 'vitest'
import { projectToSearchItem, projectToSearchItems } from '../project'
import type { SettingsRegistryEntry } from '../settings-registry'

function makeEntry(overrides: Partial<SettingsRegistryEntry> = {}): SettingsRegistryEntry {
  return {
    id: 'test:1',
    title: { zh_CN: '机器人配置', en: 'Bot Config' },
    category: 'bot',
    keywords: [
      { zh_CN: '机器人', en: 'bot' },
      { zh_CN: '配置', en: 'config' },
    ],
    route: '/config/bot',
    description: { zh_CN: '机器人基本配置', en: 'Basic bot configuration' },
    source: 'manual',
    ...overrides,
  }
}

describe('R1-3-3：语言投影 projectToSearchItem', () => {
  it('中文语言 → title 解析为 zh_CN', () => {
    const entry = makeEntry()
    const item = projectToSearchItem(entry, 'zh_CN')
    expect(item.title).toBe('机器人配置')
  })

  it('英文语言 → title 解析为 en', () => {
    const entry = makeEntry()
    const item = projectToSearchItem(entry, 'en')
    expect(item.title).toBe('Bot Config')
  })

  it('未知语言 → fallback 到G 到 zh_CN', () => {
    const entry = makeEntry()
    const item = projectToSearchItem(entry, 'fr')
    expect(item.title).toBe('机器人配置')
  })

  it('跨语言 keywords → 含所有语言变体', () => {
    const entry = makeEntry()
    const item = projectToSearchItem(entry, 'zh_CN')
    expect(item.keywords).toContain('机器人')
    expect(item.keywords).toContain('bot')
    expect(item.keywords).toContain('配置')
    expect(item.keywords).toContain('config')
  })

  it('SearchItem 接口字段完整', () => {
    const entry = makeEntry()
    const item = projectToSearchItem(entry, 'zh_CN')
    expect(item).toHaveProperty('id')
    expect(item).toHaveProperty('title')
    expect(item).toHaveProperty('description')
    expect(item).toHaveProperty('path')
    expect(item).toHaveProperty('category')
    expect(item).toHaveProperty('keywords')
  })

  it('string 类型 title 直接使用', () => {
    const entry = makeEntry({ title: '纯文本标题' })
    const item = projectToSearchItem(entry, 'zh_CN')
    expect(item.title).toBe('纯文本标题')
  })

  it('无 description → 空字符串', () => {
    const entry = makeEntry({ description: undefined })
    const item = projectToSearchItem(entry, 'zh_CN')
    expect(item.description).toBe('')
  })

  it('projectToSearchItems 批量投影', () => {
    const entries = [
      makeEntry({ id: 'a' }),
      makeEntry({ id: 'b', title: 'B' }),
    ]
    const items = projectToSearchItems(entries, 'zh_CN')
    expect(items).toHaveLength(2)
    expect(items[0].id).toBe('a')
    expect(items[1].id).toBe('b')
  })

  it('path 等于 entry.route', () => {
    const entry = makeEntry({ route: '/custom/route' })
    const item = projectToSearchItem(entry, 'zh_CN')
    expect(item.path).toBe('/custom/route')
  })
})