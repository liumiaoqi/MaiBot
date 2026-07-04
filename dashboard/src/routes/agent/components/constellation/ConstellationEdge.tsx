import { memo } from 'react'

import { BaseEdge, getSmoothStepPath } from 'reactflow'

import type { ConstellationEdge as ConstellationEdgeData } from '../../utils/constellation'

export const ConstellationEdgeComponent = memo(({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: {
  id: string
  sourceX: number
  sourceY: number
  targetX: number
  targetY: number
  sourcePosition: any
  targetPosition: any
  data: ConstellationEdgeData
}) {
  const [edgePath] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

  return (
    <BaseEdge
      id={id}
      path={edgePath}
      style={{
        stroke: data.color,
        strokeWidth: data.width,
        opacity: 0.6,
      }}
    />
  )
})

ConstellationEdgeComponent.displayName = 'ConstellationEdge'