import { Download, Wifi, WifiOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { TimeRangeSelector } from '@/components/monitor/TimeRangeSelector'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useLLMStats } from '@/hooks/useLLMStats'

import { ChatStreamMonitor } from './monitor/chat-stream-monitor'
import { SystemResourceMonitor } from './monitor/system-resource-monitor'

export function SystemMonitorPage() {
  const { t } = useTranslation()
  const {
    agentStats,
    modelStats,
    summary,
    isConnected,
    hours,
    setHours,
    exportCSV,
  } = useLLMStats()

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{t('monitor.title')}</h1>
        <div className="flex items-center gap-3">
          {isConnected ? (
            <span className="flex items-center gap-1 text-xs text-green-600">
              <Wifi className="h-3.5 w-3.5" />
              {t('monitor.live')}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs text-muted-foreground">
              <WifiOff className="h-3.5 w-3.5" />
              {t('monitor.polling')}
            </span>
          )}
        </div>
      </div>

      <Tabs defaultValue="system">
        <TabsList>
          <TabsTrigger value="system">{t('monitor.tabs.system')}</TabsTrigger>
          <TabsTrigger value="llm">{t('monitor.tabs.llm')}</TabsTrigger>
          <TabsTrigger value="chat">{t('monitor.tabs.chat')}</TabsTrigger>
        </TabsList>

        <TabsContent value="system" className="mt-4">
          <SystemResourceMonitor />
        </TabsContent>

        <TabsContent value="llm" className="mt-4 space-y-4">
          <div className="flex items-center justify-between">
            <TimeRangeSelector value={hours} onChange={setHours} />
            <Button variant="outline" size="sm" onClick={exportCSV}>
              <Download className="mr-1.5 h-3.5 w-3.5" />
              {t('monitor.llm.exportCSV')}
            </Button>
          </div>

          {summary && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    {t('monitor.llm.totalRequests')}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{summary.total_requests.toLocaleString()}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    {t('monitor.llm.totalCost')}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">¥{summary.total_cost.toFixed(2)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    {t('monitor.llm.totalTokens')}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{summary.total_tokens.toLocaleString()}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-xs font-medium text-muted-foreground">
                    {t('monitor.llm.avgResponse')}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-2xl font-bold">{summary.avg_response_time.toFixed(2)}s</div>
                </CardContent>
              </Card>
            </div>
          )}

          {modelStats.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium">{t('monitor.llm.modelStats')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th className="pb-2 pr-3 font-medium">{t('monitor.llm.model')}</th>
                        <th className="pb-2 pr-3 font-medium text-right">{t('monitor.llm.requests')}</th>
                        <th className="pb-2 pr-3 font-medium text-right">{t('monitor.llm.cost')}</th>
                        <th className="pb-2 pr-3 font-medium text-right">{t('monitor.llm.tokens')}</th>
                        <th className="pb-2 font-medium text-right">{t('monitor.llm.avgTime')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {modelStats.map((m) => (
                        <tr key={m.model_name} className="border-b last:border-0">
                          <td className="py-2 pr-3 max-w-[200px] truncate">{m.model_name}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{m.request_count}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">¥{m.total_cost.toFixed(4)}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{m.total_tokens.toLocaleString()}</td>
                          <td className="py-2 text-right tabular-nums">{m.avg_response_time.toFixed(2)}s</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {agentStats.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium">{t('monitor.llm.agentStats')}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th className="pb-2 pr-3 font-medium">{t('monitor.llm.agent')}</th>
                        <th className="pb-2 pr-3 font-medium text-right">{t('monitor.llm.requests')}</th>
                        <th className="pb-2 pr-3 font-medium text-right">{t('monitor.llm.inputTokens')}</th>
                        <th className="pb-2 pr-3 font-medium text-right">{t('monitor.llm.outputTokens')}</th>
                        <th className="pb-2 pr-3 font-medium text-right">{t('monitor.llm.cost')}</th>
                        <th className="pb-2 font-medium text-right">{t('monitor.llm.avgTime')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {agentStats.map((a) => (
                        <tr key={a.agent_id} className="border-b last:border-0">
                          <td className="py-2 pr-3 max-w-[150px] truncate">{a.agent_id}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{a.request_count}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{a.total_input_tokens.toLocaleString()}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">{a.total_output_tokens.toLocaleString()}</td>
                          <td className="py-2 pr-3 text-right tabular-nums">¥{a.total_cost.toFixed(4)}</td>
                          <td className="py-2 text-right tabular-nums">{a.avg_response_time.toFixed(2)}s</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="chat" className="mt-4">
          <ChatStreamMonitor />
        </TabsContent>
      </Tabs>
    </div>
  )
}