import { describe, it, expect } from 'vitest'
import { searchMatch, getSearchScore } from '../pinyin-search'

describe('R1-3-4：拼音搜索 searchMatch + getSearchScore', () => {
  it('精确匹配 → score 100', () => {
    expect(searchMatch('nickname', ['nickname'])).toEqual({ matched: true, score: 100 })
  })

  it('前缀匹配 → score 90', () => {
    expect(searchMatch('nick', ['nickname'])).toEqual({ matched: true, score: 90 })
  })

  it('子串匹配 → score 70', () => {
    // '格设' 是 '人格设置' 的子串但非前缀
    expect(searchMatch('格设', ['人格设置'])).toEqual({ matched: true, score: 70 })
  })

  it('拼音全拼 → score 50', () => {
    expect(searchMatch('shezhi', ['设置'])).toEqual({ matched: true, score: 50 })
  })

  it('拼音首字母 → score 40', () => {
    expect(searchMatch('rg', ['人格'])).toEqual({ matched: true, score: 40 })
  })

  it('不匹配 → score 0', () => {
    expect(searchMatch('xyz', ['人格'])).toEqual({ matched: false, score: 0 })
  })

  it('空查询 → 不匹配', () => {
    expect(searchMatch('', ['人格'])).toEqual({ matched: false, score: 0 })
  })

  it('空 keywords → 不匹配', () => {
    expect(searchMatch('test', [])).toEqual({ matched: false, score: 0 })
  })

  it('大小写归一化', () => {
    expect(searchMatch('NICKNAME', ['nickname'])).toEqual({ matched: true, score: 100 })
    expect(searchMatch('nickname', ['NICKNAME'])).toEqual({ matched: true, score: 100 })
  })

  it('title 加成：getSearchScore title 命中 → +20', () => {
    const result = getSearchScore('人格设置', ['其他'], '人格')
    // keywords 不匹配 0，title 前缀匹配 → matched + 20 加成
    expect(result.matched).toBe(true)
    expect(result.score).toBe(20) // 0 + 20
  })

  it('title 精确匹配 + keywords 精确匹配 → 100 + 20 = 120', () => {
    const result = getSearchScore('nickname', ['nickname'], 'nickname')
    expect(result.score).toBe(120)
  })

  it('都不匹配 → score 0', () => {
    const result = getSearchScore('title', ['kw'], 'query')
    expect(result).toEqual({ matched: false, score: 0 })
  })

  it('score 排序：精确 > 前缀 > 子串 > 拼音全拼 > 拼音首字母', () => {
    const exact = searchMatch('设置', ['设置']).score
    const prefix = searchMatch('设', ['设置']).score
    const substr = searchMatch('置', ['设置']).score
    const pinyinFull = searchMatch('shezhi', ['设置']).score
    const pinyinInit = searchMatch('sz', ['设置']).score

    expect(exact).toBeGreaterThan(prefix)
    expect(prefix).toBeGreaterThan(substr)
    expect(substr).toBeGreaterThan(pinyinFull)
    expect(pinyinFull).toBeGreaterThan(pinyinInit)
  })
})