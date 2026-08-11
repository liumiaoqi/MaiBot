/**
 * MarkdownRenderer —— Markdown 渲染占位组件。
 *
 * mingtang 未引入完整 Markdown 渲染管线，这里以纯文本方式呈现内容，
 * 保持调用方 props 契约（content + 可选 className）不变。
 */
interface MarkdownRendererProps {
  content: string
  className?: string
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return <div className={className}>{content}</div>
}