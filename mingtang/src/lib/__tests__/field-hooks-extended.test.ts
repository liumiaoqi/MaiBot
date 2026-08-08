import { describe, it, expect, beforeEach } from 'vitest'
import { fieldHooks, FieldHookRegistry } from '../field-hooks'

describe('R2-2-1：field-hooks 地基扩展（registerAll + getByType）', () => {
  beforeEach(() => {
    fieldHooks.clear()
  })

  it('已有 API 行为不变——register/get/has', () => {
    const component = () => null
    fieldHooks.register('test.field', component, 'replace')
    expect(fieldHooks.has('test.field')).toBe(true)
    const entry = fieldHooks.get('test.field')
    expect(entry).toBeDefined()
    expect(entry!.type).toBe('replace')
    expect(entry!.component).toBe(component)
  })

  it('已有 API 行为不变——unregister/clear/getAllPaths', () => {
    fieldHooks.register('a', () => null)
    fieldHooks.register('b', () => null)
    expect(fieldHooks.getAllPaths()).toHaveLength(2)
    fieldHooks.unregister('a')
    expect(fieldHooks.has('a')).toBe(false)
    expect(fieldHooks.getAllPaths()).toHaveLength(1)
    fieldHooks.clear()
    expect(fieldHooks.getAllPaths()).toHaveLength(0)
  })

  it('registerAll 批量注册 → 所有条目注册到注册表', () => {
    fieldHooks.registerAll([
      { fieldPath: 'field1', component: () => null, type: 'replace' },
      { fieldPath: 'field2', component: () => null, type: 'wrapper' },
      { fieldPath: 'field3', component: () => null, type: 'hidden' },
    ])
    expect(fieldHooks.has('field1')).toBe(true)
    expect(fieldHooks.has('field2')).toBe(true)
    expect(fieldHooks.has('field3')).toBe(true)
    expect(fieldHooks.getAllPaths()).toHaveLength(3)
  })

  it('getByType("replace") → 返回所有 type=replace 条目', () => {
    fieldHooks.registerAll([
      { fieldPath: 'r1', component: () => null, type: 'replace' },
      { fieldPath: 'r2', component: () => null, type: 'replace' },
      { fieldPath: 'w1', component: () => null, type: 'wrapper' },
      { fieldPath: 'h1', component: () => null, type: 'hidden' },
    ])
    const replaceEntries = fieldHooks.getByType('replace')
    expect(replaceEntries).toHaveLength(2)
  })

  it('getByType("wrapper") → 返回所有 type=wrapper 条目', () => {
    fieldHooks.registerAll([
      { fieldPath: 'r1', component: () => null, type: 'replace' },
      { fieldPath: 'w1', component: () => null, type: 'wrapper' },
      { fieldPath: 'w2', component: () => null, type: 'wrapper' },
    ])
    const wrapperEntries = fieldHooks.getByType('wrapper')
    expect(wrapperEntries).toHaveLength(2)
  })

  it('getByType("hidden") → 返回所有 type=hidden 条目', () => {
    fieldHooks.registerAll([
      { fieldPath: 'h1', component: () => null, type: 'hidden' },
      { fieldPath: 'h2', component: () => null, type: 'hidden' },
      { fieldPath: 'r1', component: () => null, type: 'replace' },
    ])
    const hiddenEntries = fieldHooks.getByType('hidden')
    expect(hiddenEntries).toHaveLength(2)
  })

  it('getByType 无匹配时返回空数组', () => {
    fieldHooks.register('r1', () => null, 'replace')
    expect(fieldHooks.getByType('hidden')).toHaveLength(0)
  })

  it('registerAll 空数组不报错', () => {
    fieldHooks.registerAll([])
    expect(fieldHooks.getAllPaths()).toHaveLength(0)
  })

  it('独立实例不共享状态', () => {
    const registry1 = new FieldHookRegistry()
    const registry2 = new FieldHookRegistry()
    registry1.register('a', () => null)
    expect(registry1.has('a')).toBe(true)
    expect(registry2.has('a')).toBe(false)
  })
})