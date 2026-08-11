/**
 * CodeEditor —— 只读代码展示的轻量 stub。
 *
 * dashboard 的 CodeEditor 基于 CodeMirror（CodeEditorImpl，lazy load），
 * mingtang 暂不引入 CodeMirror 依赖；TuningTab 仅用其 readOnly TOML 展示，
 * 这里用 `<pre>` 满足接口契约，保持 tab 组件零改动。
 *
 * 若后续需要编辑能力（plugin-config 源码模式），再引入 CodeMirror 并替换实现。
 */
import { cn } from '@/lib/utils'

export type Language = 'python' | 'json' | 'toml' | 'css' | 'text'

export interface CodeEditorRangeClassName {
  fromLine: number
  fromCh: number
  toLine: number
  toCh: number
  className: string
}

export interface CodeEditorProps {
  value: string
  onChange?: (value: string) => void
  language?: Language
  readOnly?: boolean
  height?: string
  minHeight?: string
  maxHeight?: string
  placeholder?: string
  theme?: 'light' | 'dark'
  className?: string
  lineClassNames?: Record<number, string>
  rangeClassNames?: CodeEditorRangeClassName[]
}

export function CodeEditor({
  value,
  height = '400px',
  minHeight,
  maxHeight,
  className,
  readOnly,
  placeholder,
}: CodeEditorProps) {
  return (
    <pre
      data-mingtang-code-editor="true"
      className={cn(
        'overflow-auto rounded-md border bg-muted/20 p-3 text-xs break-words whitespace-pre-wrap',
        className,
      )}
      style={{ height, minHeight, maxHeight }}
      aria-readonly={readOnly}
    >
      {value || placeholder || ''}
    </pre>
  )
}

export default CodeEditor