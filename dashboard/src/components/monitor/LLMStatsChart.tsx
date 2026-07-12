import {
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
} from 'recharts'

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart'
import type { TimeSeriesItem } from '@/hooks/useLLMStats'

interface LLMStatsChartProps {
  timeSeriesData: TimeSeriesItem[]
}

const chartConfig = {
  requests: {
    label: '请求数',
    color: 'hsl(var(--color-chart-1))',
  },
  cost: {
    label: '费用',
    color: 'hsl(var(--color-chart-2))',
  },
  tokens: {
    label: 'Tokens',
    color: 'hsl(var(--color-chart-3))',
  },
} satisfies ChartConfig

function formatHour(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:00`
  } catch {
    return timestamp
  }
}

export function LLMStatsChart({ timeSeriesData }: LLMStatsChartProps) {
  const chartData = timeSeriesData.map((item) => ({
    ...item,
    timeLabel: formatHour(item.timestamp),
  }))

  return (
    <ChartContainer config={chartConfig} className="h-[280px] w-full">
      <LineChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-muted/30" />
        <XAxis
          dataKey="timeLabel"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          className="text-xs"
          interval="preserveStartEnd"
        />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Line
          type="monotone"
          dataKey="requests"
          stroke="var(--color-requests)"
          strokeWidth={2}
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="tokens"
          stroke="var(--color-tokens)"
          strokeWidth={2}
          dot={false}
          yAxisId={1}
        />
      </LineChart>
    </ChartContainer>
  )
}