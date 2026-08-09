import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { sanitizeCSS } from '@/lib/theme/sanitizer'
import { loadThemeConfig, saveThemePartial } from '@/lib/theme/storage'
import { applyThemePipeline } from '@/lib/theme/pipeline'

/** 自定义 CSS 编辑器组件——CodeEditor + 清除按钮 + sanitize 警告 + 500ms debounce */
export function CustomCssEditor() {
  const { t } = useTranslation()
  const [css, setCss] = useState(() => {
    const config = loadThemeConfig()
    return config.styleCustomCSS?.modern ?? ''
  })
  const [warnings, setWarnings] = useState<string[]>([])
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  // sanitize 即时警告
  useEffect(() => {
    if (!css.trim()) {
      setWarnings([])
      return
    }
    const result = sanitizeCSS(css)
    setWarnings(result.warnings)
  }, [css])

  // 500ms debounce 持久化 + 重跑 pipeline
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      saveThemePartial({
        styleCustomCSS: { modern: css },
      })
      const isDark = document.documentElement.classList.contains('dark')
      applyThemePipeline(loadThemeConfig(), isDark)
    }, 500)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [css])

  const handleClear = () => {
    setCss('')
  }

  return (
    <div className="space-y-2" data-testid="custom-css-editor">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium">{t('settings.appearance.customCss')}</label>
        <button
          onClick={handleClear}
          className="text-xs text-muted-foreground hover:text-foreground"
          data-testid="custom-css-clear"
        >
          {t('settings.appearance.clearCss')}
        </button>
      </div>
      <textarea
        value={css}
        onChange={(e) => setCss(e.target.value)}
        className="w-full h-[250px] rounded-md border border-border p-3 font-mono text-sm"
        placeholder={t('settings.appearance.cssPlaceholder')}
        data-testid="custom-css-textarea"
      />
      {/* 黄色警告区 */}
      <div
        data-testid="custom-css-warnings"
        className="rounded-md bg-yellow-50 border border-yellow-200 p-2 text-xs text-yellow-800"
      >
        {warnings.length > 0 && (
          <>
            <p className="font-semibold">{t('settings.appearance.cssWarningTitle')}</p>
            <ul className="list-disc list-inside">
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}