/**
 * Model 配置页面 Tour 引导 Hook
 */
import { useEffect, useRef, useCallback } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useTour } from '@/components/tour'
import { MODEL_ASSIGNMENT_TOUR_ID, modelAssignmentTourSteps, STEP_ROUTE_MAP } from '@/components/tour/tours/model-assignment-tour'

interface UseModelTourOptions {
  /** 打开模型编辑对话框回调 */
  onOpenEditDialog?: () => void
  /** 关闭编辑对话框回调 */
  onCloseEditDialog?: () => void
}

interface UseModelTourReturn {
  /** 开始引导 */
  startTour: () => void
  /** Tour 是否正在运行 */
  isRunning: boolean
  /** 当前步骤索引 */
  stepIndex: number
}

/**
 * Model 配置页面 Tour 引导 Hook
 */
export function useModelTour(options: UseModelTourOptions = {}): UseModelTourReturn {
  const { onOpenEditDialog, onCloseEditDialog } = options
  const navigate = useNavigate()
  const { registerTour, startTour: startTourFn, state: tourState, goToStep } = useTour()

  // 用于追踪前一个步骤
  const prevTourStepRef = useRef(tourState.stepIndex)

  const didClickTourTarget = useCallback((event: MouseEvent, selector: string) => {
    const target = event.target instanceof Element ? event.target : null
    if (target?.closest(selector)) {
      return true
    }

    const element = document.querySelector(selector)
    if (!element) {
      return false
    }

    const rect = element.getBoundingClientRect()
    return (
      event.clientX >= rect.left &&
      event.clientX <= rect.right &&
      event.clientY >= rect.top &&
      event.clientY <= rect.bottom
    )
  }, [])

  // 注册 Tour
  useEffect(() => {
    registerTour(MODEL_ASSIGNMENT_TOUR_ID, modelAssignmentTourSteps)
  }, [registerTour])

  // 监听 Tour 步骤变化，处理页面导航
  useEffect(() => {
    if (tourState.activeTourId === MODEL_ASSIGNMENT_TOUR_ID && tourState.isRunning) {
      const targetRoute = STEP_ROUTE_MAP[tourState.stepIndex]
      if (targetRoute && !window.location.pathname.endsWith(targetRoute.replace('/config/', ''))) {
        navigate({ to: targetRoute })
      }
    }
  }, [tourState.stepIndex, tourState.activeTourId, tourState.isRunning, navigate])

  // 监听 Tour 步骤变化，当从弹窗内步骤回退到弹窗外步骤时，自动关闭弹窗
  // 模型弹窗步骤: 12-17 (index 12-17)，弹窗外步骤: 10-11 (index 10-11)
  useEffect(() => {
    if (tourState.activeTourId === MODEL_ASSIGNMENT_TOUR_ID && tourState.isRunning) {
      const prevStep = prevTourStepRef.current
      const currentStep = tourState.stepIndex
      
      // 如果从弹窗内步骤 (12-17) 回退到弹窗外步骤 (<=11)，关闭弹窗
      if (prevStep >= 12 && prevStep <= 17 && currentStep < 12) {
        onCloseEditDialog?.()
      }
      
      prevTourStepRef.current = currentStep
    }
  }, [tourState.stepIndex, tourState.activeTourId, tourState.isRunning, onCloseEditDialog])

  // 处理 Tour 中需要用户点击才能继续的步骤
  useEffect(() => {
    if (tourState.activeTourId !== MODEL_ASSIGNMENT_TOUR_ID || !tourState.isRunning) return

    const handleTourClick = (e: MouseEvent) => {
      const currentStep = tourState.stepIndex

      // Step 3 (index 2): 点击添加提供商按钮
      if (currentStep === 2 && didClickTourTarget(e, '[data-tour="add-provider-button"]')) {
        setTimeout(() => goToStep(3), 300)
      }
      // Step 10 (index 9): 点击取消按钮（关闭提供商弹窗）
      else if (currentStep === 9 && didClickTourTarget(e, '[data-tour="provider-cancel-button"]')) {
        setTimeout(() => goToStep(10), 300)
      }
      // Step 12 (index 11): 点击添加模型按钮
      else if (currentStep === 11 && didClickTourTarget(e, '[data-tour="add-model-button"]')) {
        onOpenEditDialog?.()
        setTimeout(() => goToStep(12), 300)
      }
      // Step 18 (index 17): 点击取消按钮（关闭模型弹窗）
      else if (currentStep === 17 && didClickTourTarget(e, '[data-tour="model-cancel-button"]')) {
        setTimeout(() => goToStep(18), 300)
      }
      // Step 19 (index 18): 点击为模型分配功能标签页
      else if (currentStep === 18 && didClickTourTarget(e, '[data-tour="tasks-tab-trigger"]')) {
        setTimeout(() => goToStep(19), 300)
      }
    }

    document.addEventListener('click', handleTourClick, true)
    return () => document.removeEventListener('click', handleTourClick, true)
  }, [tourState, goToStep, onOpenEditDialog, didClickTourTarget])

  // Step 12 的 spotlight 点击在部分浏览器/布局下会被 Joyride 遮罩截获。
  // 这里直接给目标按钮补一个原生监听，确保点中按钮时能打开模型弹窗。
  useEffect(() => {
    if (
      tourState.activeTourId !== MODEL_ASSIGNMENT_TOUR_ID ||
      !tourState.isRunning ||
      tourState.stepIndex !== 11
    ) {
      return
    }

    const addModelButton = document.querySelector('[data-tour="add-model-button"]')
    if (!addModelButton) {
      return
    }

    const handleAddModelButtonClick = () => {
      onOpenEditDialog?.()
      setTimeout(() => goToStep(12), 300)
    }

    addModelButton.addEventListener('click', handleAddModelButtonClick, true)
    return () => addModelButton.removeEventListener('click', handleAddModelButtonClick, true)
  }, [tourState.activeTourId, tourState.isRunning, tourState.stepIndex, goToStep, onOpenEditDialog])

  // 开始引导
  const handleStartTour = useCallback(() => {
    startTourFn(MODEL_ASSIGNMENT_TOUR_ID)
  }, [startTourFn])

  return {
    startTour: handleStartTour,
    isRunning: tourState.isRunning && tourState.activeTourId === MODEL_ASSIGNMENT_TOUR_ID,
    stepIndex: tourState.stepIndex,
  }
}
