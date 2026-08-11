/**
 * useFeatureStatus —— 功能启用状态领域 hook（页面逻辑下沉）。
 *
 * 通过 getBotConfigCached / getModelConfigCached 解析记忆（a_memorix.plugin.enabled）
 * 与视觉（model_task_config.vlm.model_list 是否含有效模型）开关。
 * Promise.allSettled 容错：bot 配置失败不更新；两者都失败 → featureStatus 全 false。
 */
import { useCallback, useState } from 'react'

import { getBotConfigCached, getModelConfigCached } from '@/lib/config-api'

import type { FeatureStatus } from '../types'

export function useFeatureStatus() {
  const [featureStatus, setFeatureStatus] = useState<FeatureStatus>({
    memoryEnabled: false,
    visualEnabled: false,
  })

  const fetchFeatureStatus = useCallback(async () => {
    try {
      // 用 allSettled：模型配置可独立失败而不影响主配置
      const [botConfigResult, modelConfigResult] = await Promise.allSettled([
        getBotConfigCached(),
        getModelConfigCached(),
      ])

      // bot 配置失败 → 不更新（保留原状态）
      if (botConfigResult.status !== 'fulfilled') return

      const botPayload = botConfigResult.value as { config?: Record<string, unknown> } & Record<string, unknown>
      const botConfig = (botPayload.config ?? botPayload) as Record<string, unknown>
      const memorixConfig = (botConfig.a_memorix ?? {}) as Record<string, unknown>
      const memorixPlugin = (memorixConfig.plugin ?? {}) as Record<string, unknown>

      const modelPayload = modelConfigResult.status === 'fulfilled'
        ? (modelConfigResult.value as { config?: Record<string, unknown> } & Record<string, unknown>)
        : {}
      const modelConfig = (modelPayload.config ?? modelPayload) as Record<string, unknown>
      const taskConfig = (modelConfig.model_task_config ?? {}) as Record<string, unknown>
      const vlmTask = (taskConfig.vlm ?? {}) as Record<string, unknown>
      const vlmModelList = Array.isArray(vlmTask.model_list) ? vlmTask.model_list : []
      const hasVlmModel = vlmModelList.some((modelName) => String(modelName ?? '').trim().length > 0)

      setFeatureStatus({
        memoryEnabled: memorixPlugin.enabled === true,
        visualEnabled: hasVlmModel,
      })
    } catch (error) {
      console.error('获取功能启用状态失败:', error)
      setFeatureStatus({
        memoryEnabled: false,
        visualEnabled: false,
      })
    }
  }, [])

  return {
    featureStatus,
    fetchFeatureStatus,
  }
}