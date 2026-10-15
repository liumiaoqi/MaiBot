/**
 * 秘密字段的三态渲染（task-11 · C）。
 *
 * **不许把三态渲染成同一个空输入框**——那正是 2 段修掉的那个洞的同族：
 * 三态塌成一个"空" ⇒ 用户以为"没配置"，于是把已有的密钥又填一遍（或反过来：以为配好了）。
 *
 * 三态各给了**三重**可区分信号（用户看得懂、测试断得准、色盲/高对比下也不丢信息）：
 * 1. 文案不同（`已配置` / `已配置（环境变量引用）` / `未设置`）；
 * 2. 样式不同（实底 / 虚线边 / 警示底）；
 * 3. `data-secret-state` 属性不同。
 *
 * 输入框恒为 `type="password"`：**前端不持有真值**（真值在服务端，接口只回三态标记），
 * 这个框是"写新值"的入口，不是"回显现值"的地方。
 */

import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import { resolveLocalizedText } from '@/lib/config-label'
import { SECRET_STATE_HINTS, SECRET_STATE_LABELS, type SecretState } from '../seam/secret-state'

/** 三态各自的样式（只用 token 类名——`scripts/check-no-hardcoded-color.sh` 禁硬编码颜色） */
const STATE_CLASSES: Record<SecretState, string> = {
  'configured-literal': 'bg-primary/10 text-primary',
  'configured-reference': 'border border-dashed border-primary/40 bg-muted text-muted-foreground',
  unset: 'bg-destructive/10 text-destructive',
}

export interface SecretStateFieldProps {
  /** 字段路径（做 testid 用；也是"这个秘密在配置里的位置"） */
  path: string
  /** 当前三态（来自接缝读的秘密标记） */
  state: SecretState
  /** 用户输入的新值；空串 = 不修改 */
  value: string
  /** 输入回调；不传 ⇒ 字段只读（与 `DynamicConfigForm` 同款：没有持有者就不假装能编辑） */
  onChange?: (value: string) => void
  /** 该字段相关的错误文案（例如后端**认领被拒**的原文） */
  error?: string
}

export function SecretStateField({
  path,
  state,
  value,
  onChange,
  error,
}: SecretStateFieldProps) {
  const { i18n } = useTranslation()
  const label = resolveLocalizedText(SECRET_STATE_LABELS[state], i18n.language)
  const hint = resolveLocalizedText(SECRET_STATE_HINTS[state], i18n.language)
  const readOnly = !onChange

  return (
    <div className="min-w-0 space-y-1" data-testid={`secret-field-${path}`} data-secret-state={state}>
      <span
        className={cn(
          'inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium',
          STATE_CLASSES[state],
        )}
        data-testid={`secret-state-${path}`}
      >
        {label}
      </span>
      <input
        type="password"
        className="w-full min-w-32 rounded-md border px-2 py-1 text-sm"
        value={value}
        disabled={readOnly}
        placeholder={hint}
        aria-label={`${label}：${path}`}
        aria-invalid={error ? true : undefined}
        data-testid={`secret-input-${path}`}
        onChange={(event) => onChange?.(event.target.value)}
      />
      {error && (
        <p className="text-xs text-destructive" data-testid={`secret-error-${path}`}>
          {error}
        </p>
      )}
    </div>
  )
}
