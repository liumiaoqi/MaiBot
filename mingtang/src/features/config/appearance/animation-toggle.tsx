import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'

/** 动效设置组件——单个 Switch"启用动画" + no-animations class 切换 */
export function AnimationToggle() {
  const { t } = useTranslation()
  const [enabled, setEnabled] = useState(() => {
    return !document.documentElement.classList.contains('no-animations')
  })

  const toggle = useCallback(() => {
    setEnabled((prev) => {
      const next = !prev
      document.documentElement.classList.toggle('no-animations', !next)
      return next
    })
  }, [])

  return (
    <div className="space-y-2" data-testid="animation-toggle">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={enabled}
          onChange={toggle}
          data-testid="animation-toggle-switch"
        />
        <span className="text-sm text-foreground">{t('settings.appearance.enableAnimations')}</span>
      </label>
      <p className="text-xs text-muted-foreground">{t('settings.appearance.enableAnimationsDesc')}</p>
    </div>
  )
}