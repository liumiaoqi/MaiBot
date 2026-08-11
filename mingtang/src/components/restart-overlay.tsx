/**
 * RestartOverlay 占位 stub（待后续批次从 dashboard 搬移）
 *
 * dashboard 原版：src/components/restart-overlay.tsx（412 行）
 * mingtang 当前未搬移完整实现——本 stub 仅保证引用不断裂
 * 后续搬移时替换为实际实现（RestartProvider + useRestart + 重启进度遮罩）
 */

interface RestartOverlayProps {
  /** 是否可见（仅独立模式使用） */
  visible?: boolean
  /** 重启完成回调 */
  onComplete?: () => void
  /** 重启失败回调 */
  onFailed?: () => void
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function RestartOverlay(_props: RestartOverlayProps = {}): null {
  // TODO: 后续批次从 dashboard/src/components/restart-overlay.tsx 搬移完整实现
  return null
}