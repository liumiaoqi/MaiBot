import { describe, expect, it } from 'vitest'

import { compareVersions } from '../compare-versions'

describe('compareVersions —— 插件域统一版本比较（R4-4a §P2-2）', () => {
  it('主版本号优先', () => {
    expect(compareVersions('2.0.0', '1.9.9')).toBe(1)
    expect(compareVersions('1.9.9', '2.0.0')).toBe(-1)
  })

  it('同主版本比较次版本号', () => {
    expect(compareVersions('1.2.0', '1.1.9')).toBe(1)
    expect(compareVersions('1.1.9', '1.2.0')).toBe(-1)
  })

  it('同主次版本比较修订号', () => {
    expect(compareVersions('1.2.3', '1.2.2')).toBe(1)
    expect(compareVersions('1.2.2', '1.2.3')).toBe(-1)
  })

  it('缺失段按 0 补齐（1.0 === 1.0.0）', () => {
    expect(compareVersions('1.0', '1.0.0')).toBe(0)
    expect(compareVersions('1.0.1', '1.0')).toBe(1)
    expect(compareVersions('1.0', '1.0.1')).toBe(-1)
  })

  it('兼容 v/V 前缀', () => {
    expect(compareVersions('v1.2.3', '1.2.3')).toBe(0)
    expect(compareVersions('V1.2.3', '1.2.3')).toBe(0)
    expect(compareVersions('v2.0.0', '1.9.9')).toBe(1)
  })

  it('容错非法段（非数字段按 0 计）', () => {
    expect(compareVersions('1.a.0', '1.0.0')).toBe(0)
    expect(compareVersions('1.b.0', '1.0.1')).toBe(-1)
  })

  it('前后空白忽略', () => {
    expect(compareVersions(' 1.0.0 ', '1.0.0')).toBe(0)
  })

  it('完全相等返回 0', () => {
    expect(compareVersions('1.2.3', '1.2.3')).toBe(0)
  })
})
