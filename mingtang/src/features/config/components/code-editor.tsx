import { useState, useMemo, type ChangeEvent } from 'react'
import { AlertCircle, Check } from 'lucide-react'
import { parse as parseToml } from 'smol-toml'

export type CodeEditorLanguage = 'json' | 'toml' | 'text'

export interface CodeEditorProps {
  value: string
  onChange?: (value: string) => void
  language?: CodeEditorLanguage
  readOnly?: boolean
  height?: string
  minHeight?: string
  maxHeight?: string
  placeholder?: string
  className?: string
}

/** TOML 错误模式正则翻译中文（20+ 模式） */
const TOML_ERROR_PATTERNS: Array<{ pattern: RegExp; replacement: string }> = [
  { pattern: /Expected "=" or comment/, replacement: '期望 "=" 或注释' },
  { pattern: /Unexpected token/, replacement: '意外的标记' },
  { pattern: /Invalid TOML value/, replacement: '无效的 TOML 值' },
  { pattern: /Duplicate key/, replacement: '重复的键' },
  { pattern: /Invalid key/, replacement: '无效的键名' },
  { pattern: /Invalid string/, replacement: '无效的字符串' },
  { pattern: /Invalid number/, replacement: '无效的数字' },
  { pattern: /Invalid boolean/, replacement: '无效的布尔值' },
  { pattern: /Invalid date/, replacement: '无效的日期' },
  { pattern: /Invalid array/, replacement: '无效的数组' },
  { pattern: /Invalid table/, replacement: '无效的表' },
  { pattern: /Invalid inline table/, replacement: '无效的内联表' },
  { pattern: /Unclosed string/, replacement: '未闭合的字符串' },
  { pattern: /Unclosed array/, replacement: '未闭合的数组' },
  { pattern: /Unclosed table/, replacement: '未闭合的表' },
  { pattern: /Unexpected end of input/, replacement: '输入意外结束' },
  { pattern: /Expected key/, replacement: '期望键名' },
  { pattern: /Expected value/, replacement: '期望值' },
  { pattern: /Expected newline/, replacement: '期望换行' },
  { pattern: /Expected dot/, replacement: '期望点号 "."' },
  { pattern: /Expected right bracket/, replacement: '期望右括号 "]"' },
  { pattern: /Expected right brace/, replacement: '期望右花括号 "}"' },
]

/** 翻译 TOML 错误信息为中文 */
function translateTomlError(error: string): string {
  let translated = error
  for (const { pattern, replacement } of TOML_ERROR_PATTERNS) {
    if (pattern.test(translated)) {
      translated = translated.replace(pattern, replacement)
    }
  }
  return translated
}

/** 校验代码内容 */
function validateCode(value: string, language: CodeEditorLanguage): { valid: boolean; error?: string } {
  if (!value.trim()) {
    return { valid: true }
  }
  try {
    if (language === 'json') {
      JSON.parse(value)
    } else if (language === 'toml') {
      parseToml(value)
    }
    return { valid: true }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    if (language === 'toml') {
      return { valid: false, error: translateTomlError(message) }
    }
    return { valid: false, error: message }
  }
}

/** 代码编辑器——TOML/JSON 校验 + 错误翻译中文 */
export function CodeEditor({
  value,
  onChange,
  language = 'text',
  readOnly = false,
  height = '400px',
  minHeight,
  maxHeight,
  placeholder,
  className = '',
}: CodeEditorProps) {
  const [localValue, setLocalValue] = useState(value)

  const effectiveValue = onChange ? value : localValue

  const validation = useMemo(
    () => validateCode(effectiveValue, language),
    [effectiveValue, language]
  )

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value
    if (onChange) {
      onChange(newValue)
    } else {
      setLocalValue(newValue)
    }
  }

  return (
    <div className={`flex flex-col gap-1 ${className}`} data-testid="code-editor">
      <textarea
        value={effectiveValue}
        onChange={handleChange}
        readOnly={readOnly}
        placeholder={placeholder}
        className={`font-mono text-sm rounded-md border bg-background px-3 py-2 resize-none focus:outline-none focus:ring-2 focus:ring-ring ${
          !validation.valid ? 'border-destructive' : 'border-border'
        }`}
        style={{ height, minHeight, maxHeight }}
        data-testid="code-editor-textarea"
      />
      {language !== 'text' && (
        <div className="flex items-center gap-1 text-xs h-4">
          {validation.valid ? (
            effectiveValue.trim() && (
              <span className="flex items-center gap-1 text-green-600 dark:text-green-400">
                <Check className="h-3 w-3" />
                <span>校验通过</span>
              </span>
            )
          ) : (
            <span className="flex items-center gap-1 text-destructive">
              <AlertCircle className="h-3 w-3" />
              <span className="truncate">{validation.error}</span>
            </span>
          )}
        </div>
      )}
    </div>
  )
}