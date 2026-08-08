import { useTranslation } from 'react-i18next'
import { PageShell } from '@/components/biz/page-shell'
import { ThemeModeSwitch } from './theme-mode-switch'
import { StyleSelector, useDashboardStyle } from './style-selector'
import { AccentPicker } from './accent-picker'
import { FutureRetroPanel } from './future-retro-panel'
import { StyleTweaksAccordion } from './style-tweaks-accordion'
import { CustomCssEditor } from './custom-css-editor'
import { AnimationToggle } from './animation-toggle'
import { ThemeIO } from './theme-io'

/** 外观设置页——主题 UI 化完整组装（R2-1-1 ~ R2-1-9） */
export function AppearancePage() {
  const { t } = useTranslation()
  const { style } = useDashboardStyle()
  const isModern = style === 'modern'
  const isFutureRetro = style === 'future-retro'

  return (
    <PageShell
      title={t('settings.appearance.themeMode')}
      breadcrumb={[t('sidebar.groups.botConfig'), t('sidebar.menu.appearance')]}
    >
      <div className="space-y-6">
        {/* 主题模式切换（两风格都显示） */}
        <section className="space-y-2">
          <h2 className="text-lg font-semibold text-foreground">
            {t('settings.appearance.themeMode')}
          </h2>
          <p className="text-sm text-muted-foreground">
            {t('settings.appearance.themeModeDesc')}
          </p>
          <ThemeModeSwitch />
        </section>

        {/* 界面风格选择（两风格都显示） */}
        <section className="space-y-2">
          <h2 className="text-lg font-semibold text-foreground">
            {t('settings.appearance.styleModern')}
          </h2>
          <StyleSelector />
        </section>

        {/* 强调色选择（仅 modern——7 坑 #4） */}
        {isModern && (
          <section className="space-y-2">
            <h2 className="text-lg font-semibold text-foreground">
              {t('settings.appearance.accentColor')}
            </h2>
            <p className="text-sm text-muted-foreground">
              {t('settings.appearance.accentHint')}
            </p>
            <AccentPicker />
          </section>
        )}

        {/* future-retro 六维参数面板（仅 future-retro） */}
        {isFutureRetro && (
          <section className="space-y-2">
            <h2 className="text-lg font-semibold text-foreground">
              {t('settings.appearance.styleFutureRetro')}
            </h2>
            <FutureRetroPanel />
          </section>
        )}

        {/* 样式微调手风琴（仅 modern——7 坑 #4） */}
        {isModern && (
          <section className="space-y-2">
            <h2 className="text-lg font-semibold text-foreground">
              {t('settings.appearance.styleTweaks')}
            </h2>
            <StyleTweaksAccordion />
          </section>
        )}

        {/* 自定义 CSS 编辑器（仅 modern——7 坑 #4） */}
        {isModern && (
          <section className="space-y-2">
            <h2 className="text-lg font-semibold text-foreground">
              {t('settings.appearance.customCss')}
            </h2>
            <CustomCssEditor />
          </section>
        )}

        {/* 动效设置（两风格都显示） */}
        <section className="space-y-2">
          <h2 className="text-lg font-semibold text-foreground">
            {t('settings.appearance.animationEffect')}
          </h2>
          <AnimationToggle />
        </section>

        {/* 主题导入/导出/重置（仅 modern——7 坑 #4） */}
        {isModern && (
          <section className="space-y-2">
            <h2 className="text-lg font-semibold text-foreground">
              {t('settings.appearance.importExportTheme')}
            </h2>
            <ThemeIO />
          </section>
        )}
      </div>
    </PageShell>
  )
}
