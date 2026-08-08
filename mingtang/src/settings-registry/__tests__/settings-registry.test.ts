import { describe, it, expect, beforeEach } from 'vitest'
import { SettingsRegistry, settingsRegistry, type SettingsRegistryEntry } from '../settings-registry'

function makeEntry(overrides: Partial<SettingsRegistryEntry> = {}): SettingsRegistryEntry {
  return {
    id: 'test:1',
    title: '测试条目',
    category: 'bot',
    keywords: ['测试'],
    route: '/config/bot',
    source: 'manual',
    ...overrides,
  }
}

describe('R1-3-1：设置注册表核心', () => {
  let registry: SettingsRegistry

  beforeEach(() => {
    registry = new SettingsRegistry()
  })

  it('注册单个条目 → getAll() 包含该条目', () => {
    const entry = makeEntry()
    registry.register(entry)
    expect(registry.getAll()).toHaveLength(1)
    expect(registry.getAll()[0]).toBe(entry)
  })

  it('重复 id 注册 → 覆盖旧条目（不报错、不追加）', () => {
    registry.register(makeEntry({ id: 'dup', title: '旧' }))
    registry.register(makeEntry({ id: 'dup', title: '新' }))
    expect(registry.size()).toBe(1)
    expect(registry.get('dup')?.title).toBe('新')
  })

  it('registerAll 批量注册', () => {
    registry.registerAll([
      makeEntry({ id: 'a' }),
      makeEntry({ id: 'b' }),
      makeEntry({ id: 'c' }),
    ])
    expect(registry.size()).toBe(3)
  })

  it('unregister(id) → 条目移除', () => {
    registry.register(makeEntry({ id: 'remove-me' }))
    registry.unregister('remove-me')
    expect(registry.size()).toBe(0)
  })

  it('unregister 不存在 id → 静默返回', () => {
    expect(() => registry.unregister('nonexistent')).not.toThrow()
    expect(registry.size()).toBe(0)
  })

  it('unregisterBySource("auto") → 仅移除 auto 条目，manual/dynamic 保留', () => {
    registry.registerAll([
      makeEntry({ id: 'auto:1', source: 'auto' }),
      makeEntry({ id: 'manual:1', source: 'manual' }),
      makeEntry({ id: 'dynamic:1', source: 'dynamic' }),
    ])
    registry.unregisterBySource('auto')
    expect(registry.size()).toBe(2)
    expect(registry.get('auto:1')).toBeUndefined()
    expect(registry.get('manual:1')).toBeDefined()
    expect(registry.get('dynamic:1')).toBeDefined()
  })

  it('unregisterByPrefix("dynamic:prompt:") → 仅移除匹配前缀条目', () => {
    registry.registerAll([
      makeEntry({ id: 'dynamic:prompt:chat' }),
      makeEntry({ id: 'dynamic:prompt:system' }),
      makeEntry({ id: 'dynamic:pack:default' }),
      makeEntry({ id: 'manual:page:/config/bot' }),
    ])
    registry.unregisterByPrefix('dynamic:prompt:')
    expect(registry.size()).toBe(2)
    expect(registry.get('dynamic:prompt:chat')).toBeUndefined()
    expect(registry.get('dynamic:prompt:system')).toBeUndefined()
    expect(registry.get('dynamic:pack:default')).toBeDefined()
    expect(registry.get('manual:page:/config/bot')).toBeDefined()
  })

  it('getByCategory("bot") → 仅返回 category="bot" 条目', () => {
    registry.registerAll([
      makeEntry({ id: 'bot:1', category: 'bot' }),
      makeEntry({ id: 'model:1', category: 'model' }),
      makeEntry({ id: 'bot:2', category: 'bot' }),
    ])
    const botEntries = registry.getByCategory('bot')
    expect(botEntries).toHaveLength(2)
    expect(botEntries.every((e) => e.category === 'bot')).toBe(true)
  })

  it('clear() → 清空', () => {
    registry.registerAll([makeEntry({ id: 'a' }), makeEntry({ id: 'b' })])
    registry.clear()
    expect(registry.size()).toBe(0)
    expect(registry.getAll()).toHaveLength(0)
  })

  it('size() → 返回条目数', () => {
    expect(registry.size()).toBe(0)
    registry.register(makeEntry())
    expect(registry.size()).toBe(1)
    registry.register(makeEntry({ id: 'test:2' }))
    expect(registry.size()).toBe(2)
  })

  it('getAll() 按 order 排序', () => {
    registry.registerAll([
      makeEntry({ id: 'c', order: 3 }),
      makeEntry({ id: 'a', order: 1 }),
      makeEntry({ id: 'b', order: 2 }),
    ])
    const all = registry.getAll()
    expect(all[0].id).toBe('a')
    expect(all[1].id).toBe('b')
    expect(all[2].id).toBe('c')
  })

  it('全局单例 settingsRegistry 可用', () => {
    expect(settingsRegistry).toBeInstanceOf(SettingsRegistry)
    expect(settingsRegistry.size()).toBeGreaterThanOrEqual(0)
  })
})