import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { highlightMatch } from '../../settings-registry/search-highlight'

describe('R1-3-5：搜索高亮 highlightMatch', () => {
  it('匹配高亮 → 含 <mark> 标签', () => {
    render(<div>{highlightMatch('人格设置', '人格')}</div>)
    const mark = screen.getByText('人格')
    expect(mark.tagName).toBe('MARK')
  })

  it('空查询 → 返回原 text', () => {
    render(<div>{highlightMatch('人格设置', '')}</div>)
    expect(screen.getByText('人格设置')).toBeInTheDocument()
    expect(screen.queryByRole('mark')).not.toBeInTheDocument()
  })

  it('拼音不高亮 → 返回原 text（子串不匹配）', () => {
    render(<div>{highlightMatch('人格设置', 'rg')}</div>)
    expect(screen.getByText('人格设置')).toBeInTheDocument()
    expect(document.querySelector('mark')).toBeNull()
  })

  it('大小写保留 → <mark> 内为原大小写', () => {
    render(<div>{highlightMatch('NickName', 'nick')}</div>)
    const mark = screen.getByText('Nick')
    expect(mark.tagName).toBe('MARK')
  })

  it('无匹配 → 返回原 text', () => {
    render(<div>{highlightMatch('人格设置', 'xyz')}</div>)
    expect(screen.getByText('人格设置')).toBeInTheDocument()
    expect(document.querySelector('mark')).toBeNull()
  })

  it('高亮样式含 bg-yellow-200/60', () => {
    render(<div>{highlightMatch('测试', '测')}</div>)
    const mark = document.querySelector('mark')
    expect(mark?.className).toContain('bg-yellow-200/60')
  })
})