import { useState, useCallback, useContext, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { loadThemeConfig, saveThemePartial } from '@/lib/theme/storage'
import { applyThemePipeline } from '@/lib/theme/pipeline'
import { buildFutureRetroTexture, futureRetroTokenOverrides } from '@/lib/theme/future-retro'
import { ThemeProviderContext } from '@/lib/theme-context'
import {
  DEFAULT_FUTURE_RETRO_STYLE_CONFIG,
  futureRetroDarkTokens,
  futureRetroLightTokens,
  type FutureRetroStyleConfig,
  type FutureRetroTextureStyle,
} from '@/lib/theme/tokens'
import { ThemeSliderRow } from './theme-slider-row'

const TEXTURE_STYLES: FutureRetroTextureStyle[] = ['fine', 'coarse', 'dot-grid', 'ruled', 'none']

/** 纹理风格 → i18n key 显式映射（动态生成 camelCase 会漏连字符——dot-grid → Dot-grid 而非 DotGrid） */
const TEXTURE_KEYS: Record<FutureRetroTextureStyle, string> = {
  fine: 'textureFine',
  coarse: 'textureCoarse',
  'dot-grid': 'textureDotGrid',
  ruled: 'textureRuled',
  none: 'textureNone',
}

/** 从 localStorage 读取 future-retro 配置，无存储时默认 */
function readStoredConfig(): FutureRetroStyleConfig {
  const config = loadThemeConfig()
  return config.styleConfig.futureRetro
}

/** future-retro 参数面板——手风琴结构（与 modern 样式微调同构——两套主题控件统一） */
export function FutureRetroPanel() {
  const { t } = useTranslation()
  const { resolvedTheme } = useContext(ThemeProviderContext)
  const [config, setConfig] = useState<FutureRetroStyleConfig>(readStoredConfig)
  const isDark = resolvedTheme === 'dark'

  // 实时预览——直接消费 futureRetroTokenOverrides 计算结果（预览 = 页面真实效果，解决"不知道看哪里"）
  const frColors = useMemo(() => {
    const base = isDark ? futureRetroDarkTokens : futureRetroLightTokens
    const overrides = futureRetroTokenOverrides(config, isDark)
    return { ...base.color!, ...(overrides.color ?? {}) }
  }, [config, isDark])

  const baseFontSize = config.baseFontSize ?? 16

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
    <div className="space-y-4" data-testid="future-retro-panel">
      {/* 右上角恢复默认 */}
      <div className="flex justify-end">
        <button
          onClick={handleReset}
          className="px-3 py-1.5 rounded-md border border-border text-sm text-foreground hover:bg-muted"
          data-testid="fr-reset-default"
        >
          {t('settings.appearance.resetDefault')}
        </button>
      </div>

      {/* 实时预览——纸色/卡片/边框/纹理/字号全部参数实时反映（"不知道看哪里"的答案） */}
      <div className="space-y-1" data-testid="fr-preview">
        <label className="text-sm font-medium text-foreground">{t('settings.appearance.frPreview')}</label>
        <div
          className="rounded-md border border-border p-4 space-y-2"
          style={{
            backgroundColor: frColors.background,
            backgroundImage:
              frColors['background-texture'] && frColors['background-texture'] !== 'none'
                ? frColors['background-texture']
                : undefined,
            backgroundSize: '180px 180px',
          }}
        >
          {/* 卡片——面板深度看卡片背景，描边比例看卡片边框 */}
          <div
            className="rounded-sm border px-3 py-2 space-y-1"
            style={{
              backgroundColor: frColors.card,
              borderColor: frColors.border,
              color: frColors.foreground,
              fontSize: `${baseFontSize}px`,
            }}
            data-testid="fr-preview-card"
          >
            <p className="font-semibold">{t('settings.appearance.frPreviewCard')}</p>
            <p style={{ fontSize: `${(baseFontSize * 0.875).toFixed(1)}px`, color: frColors['muted-foreground'] }}>
              {t('settings.appearance.frPreviewCardSub')}
            </p>
          </div>
          {/* 页面文字——基础字号看这里 */}
          <p style={{ color: frColors.foreground, fontSize: `${(baseFontSize * 0.875).toFixed(1)}px` }} data-testid="fr-preview-page">
            {t('settings.appearance.frPreviewPage')}
          </p>
        </div>
      </div>

      {/* ① 字体排版——基准字号 */}
      <div data-testid="fr-group-typography" className="space-y-3 rounded-lg border p-4">
        <h3 className="font-semibold text-foreground">{t('settings.appearance.typographyGroup')}</h3>
        <ThemeSliderRow
          label={t('settings.appearance.baseFontSize')}
          value={baseFontSize}
          min={12}
          max={20}
          onChange={(v) => updateConfig({ baseFontSize: v })}
          hint={t('settings.appearance.baseFontSizeHint')}
          dataTestId="fr-font-size"
        />
      </div>

      {/* ② 视觉效果——面板深度 + 描边比例 */}
      <div data-testid="fr-group-visual" className="space-y-3 rounded-lg border p-4">
        <h3 className="font-semibold text-foreground">{t('settings.appearance.visualGroup')}</h3>
        <ThemeSliderRow
          label={t('settings.appearance.frPanelDepth')}
          value={config.panelDepth}
          min={0}
          max={100}
          onChange={(v) => updateConfig({ panelDepth: v })}
          hint={t('settings.appearance.frPanelDepthHint')}
          displayValue={`${config.panelDepth}%`}
          dataTestId="fr-panel-depth"
        />
        <ThemeSliderRow
          label={t('settings.appearance.frStrokeScale')}
          value={config.strokeScale}
          min={50}
          max={100}
          onChange={(v) => updateConfig({ strokeScale: v })}
          hint={t('settings.appearance.frStrokeScaleHint')}
          displayValue={`${config.strokeScale}%`}
          dataTestId="fr-stroke-scale"
        />
      </div>

      {/* ③ 背景设置——纸暖度 + 纹理风格 + 纹理强度 */}
      <div data-testid="fr-group-backgrounds" className="space-y-3 rounded-lg border p-4">
        <h3 className="font-semibold text-foreground">{t('settings.appearance.backgroundGroup')}</h3>
        <ThemeSliderRow
          label={t('settings.appearance.frPaperWarmth')}
          value={config.paperWarmth}
          min={0}
          max={100}
          onChange={(v) => updateConfig({ paperWarmth: v })}
          hint={t('settings.appearance.frPaperWarmthHint')}
          displayValue={`${config.paperWarmth}%`}
          dataTestId="fr-paper-warmth"
        />
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
                  <span className="text-xs text-foreground">{t(`settings.appearance.${TEXTURE_KEYS[style]}`)}</span>
                </button>
              )
            })}
          </div>
        </div>
        <ThemeSliderRow
          label={t('settings.appearance.frTextureIntensity')}
          value={config.textureIntensity}
          min={10}
          max={100}
          onChange={(v) => updateConfig({ textureIntensity: v })}
          hint={t('settings.appearance.frTextureIntensityHint')}
          displayValue={`${config.textureIntensity}%`}
          disabled={isTextureNone}
          dataTestId="fr-texture-intensity"
        />
      </div>
    </div>
  )
}
