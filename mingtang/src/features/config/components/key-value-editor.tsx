import { useState, useCallback, type ChangeEvent } from 'react'
import { AlertCircle, Check, Plus, X } from 'lucide-react'

export interface KeyValueEditorProps {
  value: Record<string, unknown>
  onChange: (value: Record<string, unknown>) => void
  className?: string
  placeholder?: string
}

/** JSON 校验 */
function validateJson(jsonStr: string): { valid: boolean; error?: string; parsed?: Record<string, unknown> } {
  if (!jsonStr.trim()) {
    return { valid: true, parsed: {} }
  }
  try {
    const parsed = JSON.parse(jsonStr)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { valid: false, error: '必须是一个 JSON 对象 {}' }
    }
    return { valid: true, parsed: parsed as Record<string, unknown> }
  } catch {
    return { valid: false, error: 'JSON 格式错误' }
  }
}

/** 键值对编辑器——环境变量/Headers（可视化编辑 + JSON 编辑双模式） */
export function KeyValueEditor({
  value,
  onChange,
  className = '',
}: KeyValueEditorProps) {
  const [mode, setMode] = useState<'list' | 'json'>('list')
  const [jsonText, setJsonText] = useState('')
  const [jsonError, setJsonError] = useState<string | null>(null)
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')

  const entries = Object.entries(value || {})

  const switchToJson = useCallback(() => {
    setJsonText(Object.keys(value).length > 0 ? JSON.stringify(value, null, 2) : '')
    setJsonError(null)
    setMode('json')
  }, [value])

  const switchToList = useCallback(() => {
    setMode('list')
  }, [])

  const handleJsonChange = useCallback((text: string) => {
    setJsonText(text)
    const validation = validateJson(text)
    if (validation.valid && validation.parsed) {
      setJsonError(null)
      onChange(validation.parsed)
    } else {
      setJsonError(validation.error ?? 'JSON 格式错误')
    }
  }, [onChange])

  const addEntry = useCallback(() => {
    if (!newKey.trim()) return
    onChange({ ...value, [newKey.trim()]: newValue })
    setNewKey('')
    setNewValue('')
  }, [newKey, newValue, value, onChange])

  const removeEntry = useCallback((key: string) => {
    const next = { ...value }
    delete next[key]
    onChange(next)
  }, [value, onChange])

  const updateEntryKey = useCallback((oldKey: string, newKey: string) => {
    if (!newKey.trim() || newKey === oldKey) return
    const next: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value)) {
      next[k === oldKey ? newKey.trim() : k] = v
    }
    onChange(next)
  }, [value, onChange])

  const updateEntryValue = useCallback((key: string, val: string) => {
    onChange({ ...value, [key]: val })
  }, [value, onChange])

  return (
    <div className={`flex flex-col ${className}`} data-testid="key-value-editor">
      <div className="flex gap-1 mb-2">
        <button
          type="button"
          onClick={switchToList}
          className={`px-3 py-1 text-xs rounded ${mode === 'list' ? 'bg-background border shadow-sm' : 'bg-muted/60'}`}
          data-testid="kv-mode-list"
        >
          可视化编辑
        </button>
        <button
          type="button"
          onClick={switchToJson}
          className={`px-3 py-1 text-xs rounded ${mode === 'json' ? 'bg-background border shadow-sm' : 'bg-muted/60'}`}
          data-testid="kv-mode-json"
        >
          JSON 编辑
        </button>
      </div>

      {mode === 'list' ? (
        <div className="space-y-2">
          {entries.map(([key, val]) => (
            <div key={key} className="flex items-center gap-2">
              <input
                type="text"
                value={key}
                onChange={(e: ChangeEvent<HTMLInputElement>) => updateEntryKey(key, e.target.value)}
                className="flex-1 font-mono text-sm rounded border border-border bg-background px-2 py-1"
              />
              <input
                type="text"
                value={String(val)}
                onChange={(e: ChangeEvent<HTMLInputElement>) => updateEntryValue(key, e.target.value)}
                className="flex-1 font-mono text-sm rounded border border-border bg-background px-2 py-1"
              />
              <button
                type="button"
                onClick={() => removeEntry(key)}
                className="p-1 text-muted-foreground hover:text-destructive"
                aria-label={`删除 ${key}`}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ))}
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={newKey}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setNewKey(e.target.value)}
              placeholder="键"
              className="flex-1 font-mono text-sm rounded border border-border bg-background px-2 py-1"
            />
            <input
              type="text"
              value={newValue}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setNewValue(e.target.value)}
              placeholder="值"
              className="flex-1 font-mono text-sm rounded border border-border bg-background px-2 py-1"
            />
            <button
              type="button"
              onClick={addEntry}
              className="p-1 text-muted-foreground hover:text-foreground"
              aria-label="添加键值对"
              data-testid="kv-add-button"
            >
              <Plus className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">编辑</span>
            {jsonError ? (
              <span className="flex items-center gap-1 text-xs text-destructive">
                <AlertCircle className="h-3 w-3" />
                <span className="truncate max-w-[200px]">{jsonError}</span>
              </span>
            ) : jsonText.trim() && (
              <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400">
                <Check className="h-3 w-3" />
                <span>有效</span>
              </span>
            )}
          </div>
          <textarea
            value={jsonText}
            onChange={(e: ChangeEvent<HTMLTextAreaElement>) => handleJsonChange(e.target.value)}
            placeholder={'{\n  "key": "value"\n}'}
            className={`font-mono text-sm rounded-md border bg-background px-3 py-2 resize-none ${
              jsonError ? 'border-destructive' : 'border-border'
            }`}
            rows={8}
            data-testid="kv-json-textarea"
          />
        </div>
      )}
    </div>
  )
}