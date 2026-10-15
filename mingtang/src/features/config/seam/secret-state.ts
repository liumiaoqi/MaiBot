/**
 * 秘密三态（F2）在前端侧的判定与文案。
 *
 * **为什么单列一个模块**：这三态被两处同时需要——数据侧（hook 决定要不要发 `set`）
 * 与展示侧（组件决定怎么渲染）。口径只放一份，免得两处各判一次、迟早判得不一样。
 *
 * 三态（**必须可区分**，这就是 2 段修掉的那个洞的同族：状态丢失 ⇒ 用户以为"没配置"）：
 * - `configured-literal`：已配置，值是**字面量**（真值没出站，客户端只拿到标记）
 * - `configured-reference`：已配置，值是**整串 `${VAR}` 引用**（F4）
 * - `unset`：未配置（`set:false`）——这一态**连值都不存在**，不是"值为空串"
 */

import type { ConfigSecretMarker } from '@/lib/config-api'
import type { LocalizedText } from '@/types/config-schema'
import { formatConfigPath } from './config-paths'

export type SecretState = 'configured-literal' | 'configured-reference' | 'unset'

/** 三态文案——用 `LocalizedText`（`AGENTS.md §三`：多语言文本不写裸 string） */
export const SECRET_STATE_LABELS: Record<SecretState, LocalizedText> = {
  'configured-literal': {
    zh_CN: '已配置',
    en_US: 'Configured',
  },
  'configured-reference': {
    zh_CN: '已配置（环境变量引用）',
    en_US: 'Configured (env reference)',
  },
  unset: {
    zh_CN: '未设置',
    en_US: 'Not set',
  },
}

/** 三态补充说明（渲染在标签旁边，解释"为什么看不到值"） */
export const SECRET_STATE_HINTS: Record<SecretState, LocalizedText> = {
  'configured-literal': {
    zh_CN: '密钥已保存在服务端，出于安全不回显；留空表示不修改',
    en_US: 'Stored on the server and never sent back; leave blank to keep it',
  },
  'configured-reference': {
    zh_CN: '值是环境变量引用（${VAR}），解析发生在服务端',
    en_US: 'The value is an environment reference (${VAR}), resolved on the server',
  },
  unset: {
    zh_CN: '尚未配置：输入新值即可写入',
    en_US: 'Not configured yet — type a value to write it',
  },
}

/** 由读条目里的秘密标记判定三态（`undefined` = 该路径没有声明，也按"未设置"看） */
export function secretStateOf(marker: ConfigSecretMarker | undefined): SecretState {
  if (!marker || !marker.set) {
    return 'unset'
  }
  return marker.kind === 'reference' ? 'configured-reference' : 'configured-literal'
}

/**
 * 模型平面里第 `index` 个提供商的密钥路径。
 *
 * 走路径代数而不是拼字符串：拼错了不会报错，只会**写到别的键上**
 * （或让后端认领失败），而这类错误在页面上看起来只是"密钥没保存"。
 */
export function providerSecretPath(index: number): string {
  return formatConfigPath(['api_providers', index, 'api_key'])
}
