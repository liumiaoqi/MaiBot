import { memo } from 'react'

import { BaseEdge, getSmoothStepPath, type EdgeProps } from '@xyflow/react'

import type { ConstellationEdge as ConstellationEdgeData } from '../../utils/constellation'

function ConstellationEdgeInner({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps) {
  const edgeData = data as unknown as ConstellationEdgeData

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
        stroke: edgeData.color,
        strokeWidth: edgeData.width,
        opacity: 0.6,
      }}
    />
  )
}

export const ConstellationEdgeComponent = memo(ConstellationEdgeInner)

ConstellationEdgeComponent.displayName = 'ConstellationEdge'