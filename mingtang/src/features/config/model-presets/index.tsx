import { useTranslation } from 'react-i18next'
import { Package } from 'lucide-react'
import { PageShell } from '@/components/biz/page-shell'

/** 模型预设占位页（/model-presets）——原版占位延续（硬决策 #4） */
export function ModelPresetsPage() {
  const { t } = useTranslation()

  const upcomingFeatures = [
    t('modelPresets.upcoming1'),
    t('modelPresets.upcoming2'),
    t('modelPresets.upcoming3'),
    t('modelPresets.upcoming4'),
    t('modelPresets.upcoming5'),
  ]

  return (
    <PageShell title={t('modelPresets.title')} breadcrumb={[t('modelPresets.title')]}>
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="max-w-2xl w-full border border-dashed rounded-lg">
          <div className="text-center p-6 pb-4">
            <div className="flex justify-center mb-4">
              <Package className="h-16 w-16 text-muted-foreground" />
            </div>
            <h2 className="text-2xl font-semibold">{t('modelPresets.devTitle')}</h2>
            <p className="text-base text-muted-foreground mt-2">
              {t('modelPresets.devDescription')}
            </p>
          </div>
          <div className="p-6 pt-2">
            <div className="space-y-3 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">{t('modelPresets.upcomingTitle')}</p>
              <ul className="space-y-2 ml-6">
                {upcomingFeatures.map((feature, index) => (
                  <li key={index} className="flex items-start">
                    <span className="mr-2">•</span>
                    <span>{feature}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  )
}
