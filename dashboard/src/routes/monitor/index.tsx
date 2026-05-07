/**
 * MaiSaka 聊天流监控页面入口
 *
 * 通过 WebSocket 实时渲染 MaiSaka 推理过程。
 */
import { Activity } from 'lucide-react'

import { MaisakaMonitor } from './maisaka-monitor'

export function PlannerMonitorPage() {
  return (
    <div className="space-y-4 sm:space-y-6 p-4 sm:p-6">
      {/* 页面标题 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2">
            <Activity className="h-6 w-6 sm:h-7 sm:w-7" />
            麦麦观察
          </h1>
        </div>
      </div>

      {/* 主体 */}
      <MaisakaMonitor />
    </div>
  )
}
