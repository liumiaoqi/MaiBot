import { lazy, Suspense } from 'react'

export type Language = 'python' | 'json' | 'toml' | 'css' | 'text'

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
}

const CodeEditorImpl = lazy(() => import('./CodeEditorImpl'))

function CodeEditorFallback({
  height,
  minHeight,
  maxHeight,
  className = '',
}: Pick<CodeEditorProps, 'height' | 'minHeight' | 'maxHeight' | 'className'>) {
  return (
    <div
      className={`bg-muted animate-pulse rounded-md border ${className}`}
      style={{ height, minHeight, maxHeight }}
    />
  )
}

export function CodeEditor(props: CodeEditorProps) {
  const { height = '400px', minHeight, maxHeight, className = '' } = props

  return (
    <Suspense
      fallback={
        <CodeEditorFallback
          height={height}
          minHeight={minHeight}
          maxHeight={maxHeight}
          className={className}
        />
      }
    >
      <CodeEditorImpl {...props} />
    </Suspense>
  )
}

export default CodeEditor
