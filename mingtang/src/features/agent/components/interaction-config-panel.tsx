import { useQuery } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { getInteractionConfig } from '@/lib/agent-api'

export function InteractionConfigPanel() {
  const { t } = useTranslation()

  const { data: config, isLoading } = useQuery({
    queryKey: ['agent', 'interactions', 'config'],
    queryFn: getInteractionConfig,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8 text-sm text-muted-foreground">
        {t('common.loading', '加载中...')}
      </div>
    )
  }

  if (!config) return null

  return (
    <div className="space-y-4 px-1">
      <h3 className="text-sm font-medium text-foreground/80">
        {t('agent.interaction.config.title')}
      </h3>

      <ConfigSection title={t('agent.interaction.config.basic.title')}>
        <ConfigRow label={t('agent.interaction.config.basic.enabled')}>
          <BooleanIndicator value={config.enabled} />
        </ConfigRow>
        <ConfigRow label={t('agent.interaction.config.basic.cooldownMinutes')}>
          <span className="text-sm text-foreground/70">{config.cooldown_minutes}</span>
        </ConfigRow>
        <ConfigRow label={t('agent.interaction.config.basic.maxPerHour')}>
          <span className="text-sm text-foreground/70">{config.max_interactions_per_hour}</span>
        </ConfigRow>
        <ConfigRow label={t('agent.interaction.config.basic.maxPerDay')}>
          <span className="text-sm text-foreground/70">{config.max_interactions_per_day}</span>
        </ConfigRow>
      </ConfigSection>

      <ConfigSection title={t('agent.interaction.config.echo.title')}>
        <ConfigRow label={t('agent.interaction.config.echo.enabled')}>
          <BooleanIndicator value={config.echo_enabled} />
        </ConfigRow>
        <ConfigRow label={t('agent.interaction.config.echo.maxDepth')}>
          <span className="text-sm text-foreground/70">{config.echo_max_depth}</span>
        </ConfigRow>
        <ConfigRow label={t('agent.interaction.config.echo.decayRatio')}>
          <span className="text-sm text-foreground/70">{config.echo_decay_ratio}</span>
        </ConfigRow>
      </ConfigSection>

      <ConfigSection title={t('agent.interaction.config.monologue.title')}>
        <ConfigRow label={t('agent.interaction.config.monologue.enabled')}>
          <BooleanIndicator value={config.monologue_enabled} />
        </ConfigRow>
        <ConfigRow label={t('agent.interaction.config.monologue.minInterval')}>
          <span className="text-sm text-foreground/70">{config.monologue_min_interval_minutes}</span>
        </ConfigRow>
        <ConfigRow label={t('agent.interaction.config.monologue.idleThreshold')}>
          <span className="text-sm text-foreground/70">{config.monologue_idle_threshold_minutes}</span>
        </ConfigRow>
        <ConfigRow label={t('agent.interaction.config.monologue.emotionThreshold')}>
          <span className="text-sm text-foreground/70">{config.monologue_emotion_intensity_threshold}</span>
        </ConfigRow>
      </ConfigSection>
    </div>
  )
}

function ConfigSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium text-muted-foreground/80 uppercase tracking-wider">{title}</h4>
      <div className="space-y-1.5 rounded-lg bg-muted/10 border border-border/60 px-3 py-2">
        {children}
      </div>
    </div>
  )
}

function ConfigRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between py-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}

function BooleanIndicator({ value }: { value: boolean }) {
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full ${
        value
          ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
          : 'bg-muted text-muted-foreground'
      }`}
    >
      {value ? 'ON' : 'OFF'}
    </span>
  )
}