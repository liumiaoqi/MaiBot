// @vitest-environment node
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { MarkdownRenderer } from '../markdown-renderer'

describe('MarkdownRenderer', () => {
  it('keeps inline code inside ordered-list text', () => {
    const content = '2. `config.toml` 中旧的 `tags = [...]` 会自动迁移到 `tag_templates`'

    const html = renderToStaticMarkup(<MarkdownRenderer content={content} />)

    expect(html).toContain('<li><code')
    expect(html).toContain('config.toml')
    expect(html).toContain('tags = [...]')
    expect(html).toContain('tag_templates')
    expect(html).not.toContain('<pre')
    expect(html).not.toMatch(/<code[^>]*\bblock\b/)
  })

  it('keeps fenced code blocks inside pre containers', () => {
    const html = renderToStaticMarkup(<MarkdownRenderer content={'```toml\ncount = 3\n```'} />)

    expect(html).toContain('<pre')
    expect(html).toContain('overflow-x-auto')
    expect(html).toContain('language-toml')
    expect(html).toContain('count = 3')
  })
})
