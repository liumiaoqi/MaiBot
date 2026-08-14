/**
 * 插件首页卡片内容渲染（R4 债清理 P1——从 home-card-manager.tsx 机械拆分）
 *
 * 职责：Markdown 渲染（HomeMarkdown）+ 5 种内容块（markdown/stat/key_value/list/actions）
 * + 插件卡视图（PluginHomeCardView）+ URL 消毒（sanitizeUrl）。
 */
import type { ReactNode } from 'react'
import { ExternalLink } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import type { PluginHomeCard, PluginHomeCardContent } from '@/lib/plugin-api'

function sanitizeUrl(url: unknown): string {
  const value = String(url || '').trim()
  if (!value || value.startsWith('//')) return ''
  const lower = value.toLowerCase()
  if (value.startsWith('/') || lower.startsWith('http://') || lower.startsWith('https://') || lower.startsWith('mailto:')) {
    return value
  }
  return ''
}

function HomeMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      urlTransform={(url) => sanitizeUrl(url)}
      components={{
        a({ children, href, ...props }) {
          const safeHref = sanitizeUrl(href)
          if (!safeHref) return <span>{children}</span>
          return (
            <a className="text-primary hover:underline" href={safeHref} target="_blank" rel="noopener noreferrer" {...props}>
              {children}
            </a>
          )
        },
        p({ children }) {
          return <p className="my-1.5 leading-relaxed">{children}</p>
        },
        ul({ children }) {
          return <ul className="my-2 list-inside list-disc space-y-1">{children}</ul>
        },
        ol({ children }) {
          return <ol className="my-2 list-inside list-decimal space-y-1">{children}</ol>
        },
        code({ children }) {
          return <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">{children}</code>
        },
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

function getBlockText(block: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = block[key]
    if (typeof value === 'string' && value.trim()) {
      return value
    }
  }
  return ''
}

function renderContentBlock(block: Record<string, unknown>, index: number): ReactNode {
  const type = String(block.type || 'text')
  if (type === 'markdown') {
    return <HomeMarkdown key={index} content={getBlockText(block, ['content', 'text', 'value'])} />
  }
  if (type === 'stat') {
    return (
      <div key={index} className="rounded-md border bg-muted/20 px-3 py-2">
        <div className="text-xs text-muted-foreground">{getBlockText(block, ['label', 'title'])}</div>
        <div className="mt-1 text-xl font-bold">{getBlockText(block, ['value', 'content'])}</div>
        {getBlockText(block, ['detail', 'description']) && (
          <div className="mt-1 text-xs text-muted-foreground">{getBlockText(block, ['detail', 'description'])}</div>
        )}
      </div>
    )
  }
  if (type === 'key_value') {
    const entries = block.entries && typeof block.entries === 'object' && !Array.isArray(block.entries)
      ? Object.entries(block.entries as Record<string, unknown>)
      : []
    return (
      <div key={index} className="space-y-1.5">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-center justify-between gap-3 text-sm">
            <span className="text-muted-foreground">{key}</span>
            <span className="min-w-0 truncate font-medium">{String(value || '')}</span>
          </div>
        ))}
      </div>
    )
  }
  if (type === 'list' && Array.isArray(block.items)) {
    return (
      <ul key={index} className="list-inside list-disc space-y-1 text-sm">
        {block.items.map((item, itemIndex) => (
          <li key={itemIndex}>{String(item || '')}</li>
        ))}
      </ul>
    )
  }
  if (type === 'actions' && Array.isArray(block.actions)) {
    return (
      <div key={index} className="flex flex-wrap gap-2">
        {block.actions.map((item, itemIndex) => {
          if (!item || typeof item !== 'object') return null
          const action = item as Record<string, unknown>
          const href = sanitizeUrl(action.url || action.href)
          if (!href) return null
          return (
            <Button key={itemIndex} variant="outline" size="sm" asChild>
              <a href={href} target={href.startsWith('/') ? undefined : '_blank'} rel={href.startsWith('/') ? undefined : 'noopener noreferrer'}>
                {getBlockText(action, ['label', 'title']) || href}
              </a>
            </Button>
          )
        })}
      </div>
    )
  }
  return <p key={index} className="text-sm leading-relaxed">{getBlockText(block, ['content', 'text', 'value'])}</p>
}

export function PluginHomeCardView({ card }: { card: PluginHomeCard }) {
  const href = sanitizeUrl(card.link_url)
  const content = renderPluginContent(card.content)

  return (
    <Card className="h-full">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <CardTitle className="truncate text-sm font-medium">{card.title}</CardTitle>
            {card.description && <CardDescription className="line-clamp-2">{card.description}</CardDescription>}
          </div>
          <Badge variant="outline" className="shrink-0 text-[10px]">插件</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {content}
        {href && (
          <Button variant="outline" size="sm" asChild className="w-full justify-start gap-2">
            <a href={href} target={href.startsWith('/') ? undefined : '_blank'} rel={href.startsWith('/') ? undefined : 'noopener noreferrer'}>
              {card.link_label || '打开'}
              {!href.startsWith('/') && <ExternalLink className="h-3.5 w-3.5" />}
            </a>
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

function renderPluginContent(content: PluginHomeCardContent): ReactNode {
  if (typeof content === 'string') {
    return content.trim() ? <HomeMarkdown content={content} /> : <p className="text-sm text-muted-foreground">暂无内容</p>
  }
  if (Array.isArray(content)) {
    return <div className="space-y-3">{content.map(renderContentBlock)}</div>
  }
  if (content && typeof content === 'object') {
    return renderContentBlock(content, 0)
  }
  return <p className="text-sm text-muted-foreground">暂无内容</p>
}
