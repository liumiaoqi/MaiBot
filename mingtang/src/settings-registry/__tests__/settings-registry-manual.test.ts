import { describe, it, expect, beforeEach } from 'vitest'
import { registerManualEntries } from '../manual'
import { settingsRegistry } from '../settings-registry'

describe('R1-3-6：手动登记 registerManualEntries', () => {
  beforeEach(() => {
    settingsRegistry.clear()
  })

  it('页面项均登记（有 path 的菜单项）', () => {
    const entries = registerManualEntries()
    const pageEntries = entries.filter((e) => e.id.startsWith('manual:page:'))
    // 19 个有 path 的菜单项（behavior 无 path 跳过；R2 新增 appearance；R4-3 砍遥测页菜单项）
    expect(pageEntries.length).toBe(19)
  })

  it('7 个 provider 字段均登记', () => {
    const entries = registerManualEntries()
    const providerEntries = entries.filter((e) => e.id.startsWith('manual:model:providers:'))
    expect(providerEntries).toHaveLength(7)
  })

  it('10 个 model edit 字段均登记', () => {
    const entries = registerManualEntries()
    const modelEntries = entries.filter((e) => e.id.startsWith('manual:model:models:'))
    expect(modelEntries).toHaveLength(10)
  })

  it('behavior 跳过（无 path）', () => {
    const entries = registerManualEntries()
    expect(entries.find((e) => e.id.includes('behavior'))).toBeUndefined()
  })

  it('所有条目 source 为 "manual"', () => {
    const entries = registerManualEntries()
    expect(entries.every((e) => e.source === 'manual')).toBe(true)
  })

  it('条目写入全局注册表', () => {
    registerManualEntries()
    expect(settingsRegistry.size()).toBeGreaterThan(0)
    expect(settingsRegistry.get('manual:page:/config/bot')).toBeDefined()
    expect(settingsRegistry.get('manual:model:providers:name')).toBeDefined()
    expect(settingsRegistry.get('manual:model:models:temperature')).toBeDefined()
  })

  it('provider 条目 routeParams 含 tab: "providers"', () => {
    registerManualEntries()
    const entry = settingsRegistry.get('manual:model:providers:name')
    expect(entry?.routeParams).toEqual({ tab: 'providers' })
  })

  it('model 条目 routeParams 含 tab: "models"', () => {
    registerManualEntries()
    const entry = settingsRegistry.get('manual:model:models:temperature')
    expect(entry?.routeParams).toEqual({ tab: 'models' })
  })
})