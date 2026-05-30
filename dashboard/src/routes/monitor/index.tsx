/**
 * MaiSaka 聊天流监控页面入口
 *
 * 通过 WebSocket 实时渲染 MaiSaka 推理过程。
 */
import { MaisakaMonitor } from './maisaka-monitor'

export function PlannerMonitorPage() {
  return (
    <div className="min-w-0 max-w-full space-y-4 overflow-x-hidden p-4 sm:space-y-6 sm:p-6">
      {/* 主体 */}
      <MaisakaMonitor />
    </div>
  )
}
