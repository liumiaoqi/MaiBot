/**
 * 麦麦使用体验反馈问卷页面
 *
 * P2 清理：假 loading 三态删除——问卷配置是静态 import（maibotFeedbackSurvey），
 * 页面立即渲染（无 spinner / 无「无法加载问卷配置」分支）；版本号改为后台预填：
 * getMaiBotStatus 异步完成后更新 initialAnswers（失败降级为「获取失败」，不阻塞渲染）。
 * 页面壳抽到 SurveyPageShell；标题/描述接 i18n survey.title / survey.description。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SurveyRenderer } from '@/components/survey'
import { maibotFeedbackSurvey } from '@/config/surveys'
import { getMaiBotStatus } from '@/lib/system-api'
import type { QuestionAnswer, SurveyConfig } from '@/types/survey'

import { SurveyPageShell } from './survey-page-shell'

export function MaiBotFeedbackSurveyPage() {
  const { t } = useTranslation()
  const [maibotVersion, setMaibotVersion] = useState('未知版本')

  // 版本后台预填：页面立即渲染，版本异步获取后填入（组件卸载后不再 setState）
  useEffect(() => {
    let mounted = true

    const loadVersion = async () => {
      try {
        const status = await getMaiBotStatus()
        if (mounted) {
          setMaibotVersion(status.version || '未知版本')
        }
      } catch (error) {
        console.error('Failed to get MaiBot version:', error)
        if (mounted) {
          setMaibotVersion('获取失败')
        }
      }
    }

    void loadVersion()
    return () => {
      mounted = false
    }
  }, [])

  // 深拷贝配置以避免修改原始对象（静态 import——挂载时派生一次）
  const surveyConfig = useMemo(
    () => JSON.parse(JSON.stringify(maibotFeedbackSurvey)) as SurveyConfig,
    [],
  )

  // 预填充的答案（版本号自动填写——后台预填完成前为「未知版本」）
  const initialAnswers: QuestionAnswer[] = useMemo(
    () => [{ questionId: 'maibot_version', value: maibotVersion }],
    [maibotVersion],
  )

  // 提交成功回调
  const handleSubmitSuccess = useCallback(() => {}, [])

  // 提交错误回调
  const handleSubmitError = useCallback((error: string) => {
    console.error('MaiBot Survey submission error:', error)
  }, [])

  return (
    <SurveyPageShell title={t('survey.title')} description={t('survey.description')}>
      <SurveyRenderer
        config={surveyConfig}
        initialAnswers={initialAnswers}
        showProgress={true}
        paginateQuestions={false}
        onSubmitSuccess={handleSubmitSuccess}
        onSubmitError={handleSubmitError}
      />
    </SurveyPageShell>
  )
}

export default MaiBotFeedbackSurveyPage
