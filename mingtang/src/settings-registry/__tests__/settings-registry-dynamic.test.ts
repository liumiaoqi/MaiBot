import { describe, it, expect, beforeEach } from 'vitest'
import { registerDynamicEntries } from '../dynamic'
import { settingsRegistry } from '../settings-registry'

describe('R1-3-7：动态登记 registerDynamicEntries', () => {
  beforeEach(() => {
    settingsRegistry.clear()
  })

  it('异步加载成功 → Prompt + Pack 条目登记到注册表', async () => {
    const result = await registerDynamicEntries(
      async () => [{ name: 'chat', description: '聊天提示词' }],
      async () => [{ id: 'pack1', name: '默认包', description: '默认配置包' }]
    )
    expect(result.errors).toHaveLength(0)
    expect(result.count).toBe(2)
    expect(settingsRegistry.get('dynamic:prompt:chat')).toBeDefined()
    expect(settingsRegistry.get('dynamic:pack:pack1')).toBeDefined()
  })

  it('所有条目 source 为 "dynamic"', async () => {
    await registerDynamicEntries(
      async () => [{ name: 'p1' }],
      async () => [{ id: 'pk1', name: 'pack1' }]
    )
    const all = settingsRegistry.getAll()
    const dynamicEntries = all.filter((e) => e.source === 'dynamic')
    expect(dynamicEntries).toHaveLength(2)
  })

  it('前缀清除：再次加载时旧 dynamic:prompt: 条目被清除后重新登记', async () => {
    await registerDynamicEntries(
      async () => [{ name: 'old', description: '旧' }],
      async () => []
    )
    expect(settingsRegistry.get('dynamic:prompt:old')).toBeDefined()

    await registerDynamicEntries(
      async () => [{ name: 'new', description: '新' }],
      async () => []
    )
    expect(settingsRegistry.get('dynamic:prompt:old')).toBeUndefined()
    expect(settingsRegistry.get('dynamic:prompt:new')).toBeDefined()
  })

  it('Prompt 加载失败 → 返回 errors，不静默吞错', async () => {
    const result = await registerDynamicEntries(
      async () => { throw new Error('网络错误') },
      async () => []
    )
    expect(result.errors).toContain('Prompt 列表加载失败')
  })

  it('Pack 加载失败 → 返回 errors，不静默吞错', async () => {
    const result = await registerDynamicEntries(
      async () => [],
      async () => { throw new Error('网络错误') }
    )
    expect(result.errors).toContain('Pack 市场加载失败')
  })

  it('Prompt 条目 category 为 "prompt"，group 为 "files"', async () => {
    await registerDynamicEntries(
      async () => [{ name: 'test' }],
      async () => []
    )
    const entry = settingsRegistry.get('dynamic:prompt:test')
    expect(entry?.category).toBe('prompt')
    expect(entry?.group).toBe('files')
  })

  it('Pack 条目 route 指向 pack-detail', async () => {
    await registerDynamicEntries(
      async () => [],
      async () => [{ id: 'p1', name: 'pack' }]
    )
    const entry = settingsRegistry.get('dynamic:pack:p1')
    expect(entry?.route).toBe('/config/pack-market/$packId')
    expect(entry?.routeParams).toEqual({ packId: 'p1' })
  })
})