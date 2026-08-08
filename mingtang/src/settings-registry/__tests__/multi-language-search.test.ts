import { describe, it, expect } from 'vitest'
import { searchMatch, getSearchScore } from '@/settings-registry/pinyin-search'
import { projectToSearchItem } from '@/settings-registry/project'
import type { SettingsRegistryEntry } from '@/settings-registry/settings-registry'

/** 多语言搜索验证——zh / en / ja / ko locale 下搜索均可用 */
describe('多语言搜索支持验证（R1-3-14）', () => {
  // 模拟一个多语言注册表条目
  const entry: SettingsRegistryEntry = {
    id: 'manual:page:/test',
    title: { zh_CN: '模型配置', en: 'Model Config', ja: 'モデル設定', ko: '모델 설정' },
    category: 'config',
    keywords: [
      { zh_CN: '模型配置', en: 'Model Config', ja: 'モデル設定', ko: '모델 설정' },
      'model',
      'config',
    ],
    route: '/config/model',
    description: { zh_CN: '配置模型参数', en: 'Configure model parameters' },
    source: 'manual',
    order: 0,
  }

  it('zh locale 下搜索可用', () => {
    const item = projectToSearchItem(entry, 'zh')
    expect(item.title).toBe('模型配置')
    const result = searchMatch('模型', [item.keywords])
    expect(result.matched).toBe(true)
  })

  it('en locale 下搜索可用', () => {
    const item = projectToSearchItem(entry, 'en')
    expect(item.title).toBe('Model Config')
    const result = searchMatch('Model', [item.keywords])
    expect(result.matched).toBe(true)
  })

  it('ja locale 下搜索可用', () => {
    const item = projectToSearchItem(entry, 'ja')
    expect(item.title).toBe('モデル設定')
    const result = searchMatch('モデル', [item.keywords])
    expect(result.matched).toBe(true)
  })

  it('ko locale 下搜索可用', () => {
    const item = projectToSearchItem(entry, 'ko')
    expect(item.title).toBe('모델 설정')
    const result = searchMatch('모델', [item.keywords])
    expect(result.matched).toBe(true)
  })

  it('中英文交叉匹配：中文输入能匹配英文关键词', () => {
    const item = projectToSearchItem(entry, 'zh')
    // keywords 包含所有语言变体（跨语言匹配）
    expect(item.keywords).toContain('Model Config')
    expect(item.keywords).toContain('model')
    const result = searchMatch('Model', [item.keywords])
    expect(result.matched).toBe(true)
  })

  it('中英文交叉匹配：英文输入能匹配中文关键词', () => {
    const item = projectToSearchItem(entry, 'en')
    // en locale 下 keywords 仍包含中文变体
    expect(item.keywords).toContain('模型配置')
    const result = searchMatch('模型', [item.keywords])
    expect(result.matched).toBe(true)
  })

  it('拼音搜索在所有 locale 下可用', () => {
    const item = projectToSearchItem(entry, 'zh')
    // 输入 "mxpz"（模型配置首字母）应匹配
    const result = searchMatch('mxpz', [item.keywords])
    expect(result.matched).toBe(true)
  })

  it('getSearchScore title 命中加成', () => {
    const item = projectToSearchItem(entry, 'zh')
    const keywords = item.keywords.split(' ')
    const score = getSearchScore(item.title, keywords, '模型配置')
    // 精确匹配 title → 100 + 20 = 120
    expect(score.score).toBe(120)
    expect(score.matched).toBe(true)
  })
})