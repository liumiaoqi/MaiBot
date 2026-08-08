import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { resetThemeToDefault, exportThemeJSON, importThemeJSON } from '@/lib/theme/storage'
import { removeCustomCSS } from '@/lib/theme/pipeline'

/** 主题导入/导出/重置组件——导出全量 JSON + 导入校验 + 重置 AlertDialog 二次确认 */
export function ThemeIO() {
  const { t } = useTranslation()
  const [resetDialogOpen, setResetDialogOpen] = useState(false)

  const handleExport = useCallback(() => {
    const json = exportThemeJSON()
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `maibot-theme-${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [])

  const handleImport = useCallback(() => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = 'application/json'
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (!file) return
      const text = await file.text()
      const result = importThemeJSON(text)
      if (result.success) {
        setTimeout(() => location.reload(), 1000)
      }
    }
    input.click()
  }, [])

  const handleResetConfirm = useCallback(() => {
    resetThemeToDefault()
    removeCustomCSS()
    setResetDialogOpen(false)
  }, [])

  return (
    <div className="space-y-3" data-testid="theme-io">
      <div className="flex gap-2">
        <button
          onClick={handleExport}
          className="px-4 py-2 rounded-md border border-border hover:bg-muted"
          data-testid="theme-export-btn"
        >
          {t('settings.appearance.exportTheme')}
        </button>
        <button
          onClick={handleImport}
          className="px-4 py-2 rounded-md border border-border hover:bg-muted"
          data-testid="theme-import-btn"
        >
          {t('settings.appearance.importTheme')}
        </button>
        <button
          onClick={() => setResetDialogOpen(true)}
          className="px-4 py-2 rounded-md border border-destructive text-destructive hover:bg-destructive/10"
          data-testid="theme-reset-btn"
        >
          {t('settings.appearance.resetTheme')}
        </button>
      </div>

      {/* 重置 AlertDialog 二次确认 */}
      {resetDialogOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          data-testid="theme-reset-dialog"
        >
          <div className="rounded-lg bg-background border p-6 max-w-md space-y-4">
            <h2 className="text-lg font-semibold">{t('settings.appearance.confirmResetTheme')}</h2>
            <p className="text-sm text-muted-foreground">{t('settings.appearance.confirmResetThemeDesc')}</p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setResetDialogOpen(false)}
                className="px-4 py-2 rounded-md border border-border hover:bg-muted"
                data-testid="theme-reset-cancel"
              >
                {t('settings.appearance.clearCss')}
              </button>
              <button
                onClick={handleResetConfirm}
                className="px-4 py-2 rounded-md bg-destructive text-destructive-foreground"
                data-testid="theme-reset-confirm"
              >
                {t('settings.appearance.confirmResetAction')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}