import { useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'

/** 样式微调手风琴组件（modern——五组 typography/visual/layout/animation/backgrounds） */
export function StyleTweaksAccordion() {
  const { t } = useTranslation()
  const [animationEnabled, setAnimationEnabled] = useState(true)
  const [bgTab, setBgTab] = useState<'page' | 'sidebar' | 'header' | 'card' | 'dialog'>('page')

  const toggleAnimation = useCallback(() => {
    setAnimationEnabled((prev) => {
      const next = !prev
      document.documentElement.classList.toggle('no-animations', !next)
      return next
    })
  }, [])

  const bgTabs = ['page', 'sidebar', 'header', 'card', 'dialog'] as const

  return (
    <div className="space-y-4" data-testid="style-tweaks-accordion">
      {/* ① typography */}
      <div data-testid="accordion-group-typography" className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">{t('settings.appearance.typographyGroup')}</h3>
          <button data-testid="reset-typography" className="text-xs text-muted-foreground hover:text-foreground">
            {t('settings.appearance.resetDefault')}
          </button>
        </div>
        <div className="space-y-2">
          <select data-testid="font-family-select" className="w-full rounded-md border px-3 py-2">
            <option value="system">{t('settings.appearance.fontFamilySystem')}</option>
            <option value="sans">{t('settings.appearance.fontFamilySans')}</option>
            <option value="serif">{t('settings.appearance.fontFamilySerif')}</option>
            <option value="mono">{t('settings.appearance.fontFamilyMono')}</option>
          </select>
          <input type="range" min={12} max={20} defaultValue={16} data-testid="font-size-slider" className="w-full" />
          <select data-testid="line-height-select" className="w-full rounded-md border px-3 py-2">
            <option value="1.2">{t('settings.appearance.lineHeightCompact')}</option>
            <option value="1.5">{t('settings.appearance.lineHeightNormal')}</option>
            <option value="1.75">{t('settings.appearance.lineHeightLoose')}</option>
          </select>
        </div>
      </div>

      {/* ② visual */}
      <div data-testid="accordion-group-visual" className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">{t('settings.appearance.visualGroup')}</h3>
          <button data-testid="reset-visual" className="text-xs text-muted-foreground hover:text-foreground">
            {t('settings.appearance.resetDefault')}
          </button>
        </div>
        <div className="space-y-2">
          <input type="range" min={0} max={24} defaultValue={4} data-testid="border-radius-slider" className="w-full" />
          <select data-testid="shadow-select" className="w-full rounded-md border px-3 py-2">
            <option value="none">{t('settings.appearance.shadowNone')}</option>
            <option value="sm">{t('settings.appearance.shadowSm')}</option>
            <option value="md">{t('settings.appearance.shadowMd')}</option>
            <option value="lg">{t('settings.appearance.shadowLg')}</option>
            <option value="xl">{t('settings.appearance.shadowXl')}</option>
          </select>
          <label className="flex items-center gap-2">
            <input type="checkbox" data-testid="blur-switch" />
            <span className="text-sm">{t('settings.appearance.blurLabel')}</span>
          </label>
        </div>
      </div>

      {/* ③ layout */}
      <div data-testid="accordion-group-layout" className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">{t('settings.appearance.layoutGroup')}</h3>
          <button data-testid="reset-layout" className="text-xs text-muted-foreground hover:text-foreground">
            {t('settings.appearance.resetDefault')}
          </button>
        </div>
        <input type="range" min={8} max={24} step={0.5} defaultValue={13} data-testid="sidebar-width-slider" className="w-full" />
      </div>

      {/* ④ animation */}
      <div data-testid="accordion-group-animation" className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">{t('settings.appearance.animationGroup')}</h3>
          <button data-testid="reset-animation" className="text-xs text-muted-foreground hover:text-foreground">
            {t('settings.appearance.resetDefault')}
          </button>
        </div>
        <div className="space-y-2">
          <select data-testid="animation-speed-select" className="w-full rounded-md border px-3 py-2">
            <option value="100">{t('settings.appearance.animationFast')}</option>
            <option value="300">{t('settings.appearance.animationNormal')}</option>
            <option value="500">{t('settings.appearance.animationSlow')}</option>
            <option value="0">{t('settings.appearance.animationOff')}</option>
          </select>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={animationEnabled}
              onChange={toggleAnimation}
              data-testid="animation-enabled-switch"
            />
            <span className="text-sm">{t('settings.appearance.enableAnimations')}</span>
          </label>
        </div>
      </div>

      {/* ⑤ backgrounds */}
      <div data-testid="accordion-group-backgrounds" className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">{t('settings.appearance.backgroundGroup')}</h3>
          <button data-testid="reset-backgrounds" className="text-xs text-muted-foreground hover:text-foreground">
            {t('settings.appearance.resetDefault')}
          </button>
        </div>
        <div className="flex gap-2">
          {bgTabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setBgTab(tab)}
              data-testid={`bg-tab-${tab}`}
              className={cn(
                'px-3 py-1.5 rounded-md border text-sm',
                bgTab === tab ? 'border-primary bg-primary/5' : 'border-border'
              )}
            >
              {t(`settings.appearance.bg${tab.charAt(0).toUpperCase() + tab.slice(1)}`)}
            </button>
          ))}
        </div>
        {bgTab !== 'page' && (
          <label className="flex items-center gap-2">
            <input type="checkbox" data-testid="bg-inherit-switch" />
            <span className="text-sm">{t('settings.appearance.inheritParentBg')}</span>
          </label>
        )}
      </div>
    </div>
  )
}