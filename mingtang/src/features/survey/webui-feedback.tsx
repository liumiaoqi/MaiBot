/**
 * WebUI 使用反馈问卷页面
 *
 * P2 清理：删除不可达的 if (!surveyConfig) 死分支——webuiFeedbackSurvey 是静态
 * import，useMemo 派生必然非空；页面壳抽到 SurveyPageShell；标题/描述接 i18n
 * survey.title / survey.description。
 */
import { useCallback, useMemo } from 'react'
import { useTranslation } from 'react-i18next'

import { SurveyRenderer } from '@/components/survey'
import { webuiFeedbackSurvey } from '@/config/surveys'
import { APP_VERSION } from '@/lib/version'
import type { QuestionAnswer, SurveyConfig } from '@/types/survey'

import { SurveyPageShell } from './survey-page-shell'

export function WebUIFeedbackSurveyPage() {
  const { t } = useTranslation()

  // 使用 useMemo 派生配置而不是 useState + useEffect（静态 import——挂载时派生一次）
  const surveyConfig = useMemo(
    () => JSON.parse(JSON.stringify(webuiFeedbackSurvey)) as SurveyConfig,
    [],
  )

  // 预填充的答案（版本号自动填写）
  const initialAnswers: QuestionAnswer[] = useMemo(
    () => [{ questionId: 'webui_version', value: `v${APP_VERSION}` }],
    [],
  )

  // 提交成功回调
  const handleSubmitSuccess = useCallback(() => {}, [])

  // 提交错误回调
  const handleSubmitError = useCallback((error: string) => {
    console.error('WebUI Survey submission error:', error)
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

export default WebUIFeedbackSurveyPage
