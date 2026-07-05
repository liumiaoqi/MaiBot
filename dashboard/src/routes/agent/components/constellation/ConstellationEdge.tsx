import { memo } from 'react'

import { BaseEdge, getSmoothStepPath, type EdgeProps } from 'reactflow'

import type { ConstellationEdge as ConstellationEdgeData } from '../../utils/constellation'

type ConstellationEdgeProps = EdgeProps & {
  data: ConstellationEdgeData
}

function ConstellationEdgeInner({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: ConstellationEdgeProps) {
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
}

export const ConstellationEdgeComponent = memo(ConstellationEdgeInner)

ConstellationEdgeComponent.displayName = 'ConstellationEdge'
