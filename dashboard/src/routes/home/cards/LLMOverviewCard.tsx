import { Link } from '@tanstack/react-router'
import { Activity, DollarSign, Zap } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

import type { StatisticsSummary } from '../types'

interface LLMOverviewCardProps {
  summary: StatisticsSummary
  formatNumber: (num: number) => { display: string; exact: string; needsExact: boolean }
  formatCurrency: (num: number) => { display: string; exact: string; needsExact: boolean }
}

export function LLMOverviewCard({ summary, formatNumber, formatCurrency }: LLMOverviewCardProps) {
  const { t } = useTranslation()

  const requests = formatNumber(summary.total_requests)
  const cost = formatCurrency(summary.total_cost)
  const tokens = formatNumber(summary.total_tokens)

  return (
    <Link to="/deepseek-monitor" className="block h-full">
      <Card className="h-full transition-colors hover:border-primary/30">
        <CardHeader className="pb-3">
          <CardTitle className="flex h-5 items-center gap-2 text-sm font-medium leading-5">
            <Zap className="h-4 w-4" />
            {t('home.llmOverview.title')}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Activity className="h-3.5 w-3.5" />
                {t('home.llmOverview.requests')}
              </span>
              <span className="text-sm font-bold text-primary">
                {requests.display}
                {requests.needsExact && <span className="ml-1 text-xs font-normal text-muted-foreground">({requests.exact})</span>}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <DollarSign className="h-3.5 w-3.5" />
                {t('home.llmOverview.cost')}
              </span>
              <span className="text-sm font-bold text-primary">
                {cost.display}
                {cost.needsExact && <span className="ml-1 text-xs font-normal text-muted-foreground">({cost.exact})</span>}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                <Zap className="h-3.5 w-3.5" />
                {t('home.llmOverview.tokens')}
              </span>
              <span className="text-sm font-bold text-primary">
                {tokens.display}
                {tokens.needsExact && <span className="ml-1 text-xs font-normal text-muted-foreground">({tokens.exact})</span>}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}