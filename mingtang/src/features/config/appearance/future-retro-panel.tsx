import { useState, useCallback, useContext } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { loadThemeConfig, saveThemePartial } from '@/lib/theme/storage'
import { applyThemePipeline } from '@/lib/theme/pipeline'
import { buildFutureRetroTexture } from '@/lib/theme/future-retro'
import { ThemeProviderContext } from '@/lib/theme-context'
import {
  DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
  type FutureRetroStyleConfig,
  type FutureRetroTextureStyle,
} from '@/lib/theme/tokens'

const TEXTURE_STYLES: FutureRetroTextureStyle[] = ['fine', 'coarse', 'dot-grid', 'ruled', 'none']

/** 从 localStorage 读取 future-retro 配置，无存储时默认 */
function readStoredConfig(): FutureRetroStyleConfig {
  const config = loadThemeConfig()
  return config.styleConfig.futureRetro
}

/** future-retro 六维参数面板组件 */
export function FutureRetroPanel() {
  const { t } = useTranslation()
  const { resolvedTheme } = useContext(ThemeProviderContext)
  const [config, setConfig] = useState<FutureRetroStyleConfig>(readStoredConfig)
  const [fontSize, setFontSize] = useState(16)
  const isDark = resolvedTheme === 'dark'

  /** 即拖即生效——更新参数并写入 localStorage + 重跑 pipeline */
  const updateConfig = useCallback((partial: Partial<FutureRetroStyleConfig>) => {
    setConfig((prev) => {
      const next = { ...prev, ...partial }
      const themeConfig = loadThemeConfig()
      const updatedConfig = {
        styleConfig: {
          ...themeConfig.styleConfig,
          futureRetro: next,
        },
      }
      saveThemePartial(updatedConfig)
      const isDark = document.documentElement.classList.contains('dark')
      applyThemePipeline(loadThemeConfig(), isDark)
      return next
    })
  }, [])

  const handleReset = () => {
    updateConfig(DEFAULT_FUTURE_RETRO_STYLE_CONFIG)
  }

  const isTextureNone = config.textureStyle === 'none'

  return (
    <div className="space-y-6" data-testid="future-retro-panel">
      {/* 右上角恢复默认 */}
      <div className="flex justify-end">
        <button
          onClick={handleReset}
          className="px-3 py-1.5 rounded-md border border-border text-sm hover:bg-muted"
          data-testid="fr-reset-default"
        >
          {t('settings.appearance.resetDefault')}
        </button>
      </div>

      {/* ① 基础字号 12-20px */}
      <div className="space-y-1">
        <label className="text-sm font-medium text-foreground">{t('settings.appearance.baseFontSize')}</label>
        <input
          type="range"
          min={12}
          max={20}
          value={fontSize}
          onChange={(e) => setFontSize(Number(e.target.value))}
          className="w-full"
          data-testid="fr-font-size"
        />
      </div>

      {/* ② 纸暖度 0-100% */}
      <div className="space-y-1">
        <label className="text-sm font-medium text-foreground">{t('settings.appearance.frPaperWarmth')}</label>
        <input
          type="range"
          min={0}
          max={100}
          value={config.paperWarmth}
          onChange={(e) => updateConfig({ paperWarmth: Number(e.target.value) })}
          className="w-full"
          data-testid="fr-paper-warmth"
        />
        <span className="text-xs text-muted-foreground">{config.paperWarmth}%</span>
      </div>

      {/* ③ 纹理风格 5 张缩略卡片 */}
      <div className="space-y-1">
        <label className="text-sm font-medium text-foreground">{t('settings.appearance.frTextureStyle')}</label>
        <div className="grid grid-cols-5 gap-2" data-testid="fr-texture-style">
          {TEXTURE_STYLES.map((style) => {
            const texture = buildFutureRetroTexture(style, 55, isDark)
            return (
              <button
                key={style}
                onClick={() => updateConfig({ textureStyle: style })}
                data-testid={`fr-texture-card-${style}`}
                className={cn(
                  'h-16 rounded-md border-2 transition-colors',
                  config.textureStyle === style
                    ? 'border-primary'
                    : 'border-border hover:border-muted-foreground/30'
                )}
                style={
                  texture !== 'none'
                    ? { backgroundImage: texture, backgroundSize: 'auto' }
                    : undefined
                }
              >
                <span className="text-xs">{style}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* ④ 纹理强度 10-100%（none 时 disabled） */}
      <div className="space-y-1">
        <label className="text-sm font-medium text-foreground">{t('settings.appearance.frTextureIntensity')}</label>
        <input
          type="range"
          min={10}
          max={100}
          value={config.textureIntensity}
          onChange={(e) => updateConfig({ textureIntensity: Number(e.target.value) })}
          disabled={isTextureNone}
          className="w-full"
          data-testid="fr-texture-intensity"
        />
        <span className="text-xs text-muted-foreground">{config.textureIntensity}%</span>
      </div>

      {/* ⑤ 面板深度 0-100% */}
      <div className="space-y-1">
        <label className="text-sm font-medium text-foreground">{t('settings.appearance.frPanelDepth')}</label>
        <input
          type="range"
          min={0}
          max={100}
          value={config.panelDepth}
          onChange={(e) => updateConfig({ panelDepth: Number(e.target.value) })}
          className="w-full"
          data-testid="fr-panel-depth"
        />
        <span className="text-xs text-muted-foreground">{config.panelDepth}%</span>
      </div>

      {/* ⑥ 描边比例 50-100% */}
      <div className="space-y-1">
        <label className="text-sm font-medium text-foreground">{t('settings.appearance.frStrokeScale')}</label>
        <input
          type="range"
          min={50}
          max={100}
          value={config.strokeScale}
          onChange={(e) => updateConfig({ strokeScale: Number(e.target.value) })}
          className="w-full"
          data-testid="fr-stroke-scale"
        />
        <span className="text-xs text-muted-foreground">{config.strokeScale}%</span>
      </div>
    </div>
  )
}