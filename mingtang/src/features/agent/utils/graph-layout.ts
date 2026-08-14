/**
 * 径向/星型图布局（ReactFlow 节点位置计算）
 *
 * 从 agent-constellation / internal-relationship-graph 两处逐行相似的
 * 径向布局函数抽取（P2-C #8）——统一按角度均匀分布：
 * - centerFirst=false（默认）：所有节点绕圆均匀分布（agent-constellation）
 * - centerFirst=true：数组首位节点居中，其余节点绕圆分布（internal-relationship-graph 的 self 节点）
 */
import type { Edge, Node } from '@xyflow/react'

export interface RadialLayoutOptions {
  /** 环绕半径 */
  radius: number
  /** 首位节点居中（星型布局）；默认 false——所有节点均匀绕圆 */
  centerFirst?: boolean
}

/** 第 index 个节点（共 count 个）的分布角度——起点为正上方（-π/2），顺时针 */
function angleFor(index: number, count: number): number {
  return (2 * Math.PI * index) / Math.max(count, 1) - Math.PI / 2
}

export function layoutRadial<N extends Node, E extends Edge>(
  nodes: N[],
  edges: E[],
  { radius, centerFirst = false }: RadialLayoutOptions
): { nodes: N[]; edges: E[] } {
  if (nodes.length === 0) {
    return { nodes: [], edges }
  }

  let layouted: N[]
  if (centerFirst) {
    const [centerNode, ...others] = nodes
    layouted = [
      { ...centerNode, position: { x: 0, y: 0 } },
      ...others.map((node, i) => ({
        ...node,
        position: {
          x: radius * Math.cos(angleFor(i, others.length)),
          y: radius * Math.sin(angleFor(i, others.length)),
        },
      })),
    ]
  } else {
    layouted = nodes.map((node, i) => ({
      ...node,
      position: {
        x: radius * Math.cos(angleFor(i, nodes.length)),
        y: radius * Math.sin(angleFor(i, nodes.length)),
      },
    }))
  }

  return { nodes: layouted, edges }
}
