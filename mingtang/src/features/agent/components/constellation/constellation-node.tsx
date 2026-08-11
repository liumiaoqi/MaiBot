import { memo } from 'react'

import { Handle, Position } from '@xyflow/react'

import type { ConstellationNode as ConstellationNodeData } from '../../utils/constellation'
import { EMOTION_ICONS } from '../../utils/emotion-constants'

const SIZE_MAP: Record<string, number> = {
  active: 48,
  quiet: 40,
  dormant: 32,
}

// react-spring 缺失（mingtang 无此依赖）→ CSS 呼吸动画替代（agent-emotion-pulse keyframes）
export const ConstellationNodeComponent = memo(({ data }: { data: ConstellationNodeData }) => {
  const size = SIZE_MAP[data.activityStatus] ?? 36
  const intensity = data.activityStatus === 'active' ? 30 : data.activityStatus === 'quiet' ? 15 : 0
  const scale = 1.0 + intensity / 200
  const duration = 2000 - intensity * 20

  return (
    <div className="relative flex flex-col items-center" style={{ width: size + 20 }}>
      <div
        style={{
          width: size,
          height: size,
          ...(intensity > 0
            ? {
                animation: `agent-emotion-pulse ${duration}ms ease-in-out infinite`,
                ['--agent-pulse-scale' as string]: scale,
              }
            : {}),
        }}
        className="rounded-full flex items-center justify-center text-white font-bold relative"
      >
        <div
          className="absolute inset-0 rounded-full"
          style={{ backgroundColor: data.color, opacity: 0.3 }}
        />
        <div
          className="absolute inset-1 rounded-full flex items-center justify-center"
          style={{ backgroundColor: data.color }}
        >
          <span className="text-sm">{EMOTION_ICONS[data.dominantEmotion] || data.displayName.charAt(0)}</span>
        </div>
        {data.isDefault && (
          <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-primary border-2 border-background" />
        )}
        <Handle type="source" position={Position.Top} className="!bg-transparent !border-0 !w-0 !h-0" />
        <Handle type="target" position={Position.Bottom} className="!bg-transparent !border-0 !w-0 !h-0" />
        <Handle type="source" position={Position.Left} className="!bg-transparent !border-0 !w-0 !h-0" />
        <Handle type="target" position={Position.Right} className="!bg-transparent !border-0 !w-0 !h-0" />
      </div>
      <span className="text-[10px] text-muted-foreground mt-1 truncate max-w-[80px] text-center">
        {data.displayName}
      </span>
    </div>
  )
})

ConstellationNodeComponent.displayName = 'ConstellationNode'