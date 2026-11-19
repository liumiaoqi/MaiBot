/**
 * WebUI 契约层类型映射（仅类型，零运行时）
 *
 * 本文件是仓储中唯一允许出现 Omit / Required 变换的位置。
 * 未在映射表内的概念一律保持手写并登记契约缺口——不要在此处擅自扩展。
 */

import type { components } from './api-schema'

type Schemas = components['schemas']

// 来源：components['schemas']['PromptCatalogResponse']（信封 success 由 fetch 层剥离）
export type PromptCatalog = Omit<Required<Schemas['PromptCatalogResponse']>, 'success'>

// 来源：components['schemas']['PromptFileInfo']
export type PromptFileInfo = Required<Schemas['PromptFileInfo']>

// 来源：components['schemas']['PromptValidationResult']
export type PromptValidationResult = Required<Schemas['PromptValidationResult']>

// 来源：components['schemas']['PromptVersionInfo']
export type PromptVersionInfo = Required<Schemas['PromptVersionInfo']>

// 来源：components['schemas']['PromptFileResponse']（信封 success 由 fetch 层剥离）
export type PromptFileContent = Omit<Required<Schemas['PromptFileResponse']>, 'success'>

// 来源：components['schemas']['PromptGeneratorChatPrompt']
export type PromptGeneratorChatPrompt = Required<Schemas['PromptGeneratorChatPrompt']>

// 来源：components['schemas']['PromptGeneratorConfigBlock']（value 保持 unknown，不窄化）
export type PromptGeneratorConfigBlock = Required<Schemas['PromptGeneratorConfigBlock']>

// 来源：components['schemas']['PromptGeneratorParsedResult']
export type PromptGeneratorResult = Required<Schemas['PromptGeneratorParsedResult']>

// 来源：components['schemas']['PromptGeneratorResponse']（信封 success 由 fetch 层剥离）
export type PromptGeneratorResponse = Omit<Required<Schemas['PromptGeneratorResponse']>, 'success'>

// 来源：components['schemas']['PromptGeneratorApplyResponse']（信封 success 由 fetch 层剥离）
export type PromptGeneratorApplyResponse = Omit<
  Required<Schemas['PromptGeneratorApplyResponse']>,
  'success'
>

// 来源：components['schemas']['PromptGeneratorRequest']（请求方向保留可选性，不做 Required）
export type PromptGeneratorRequest = Schemas['PromptGeneratorRequest']

// 来源：components['schemas']['ModelTestResponse']（G1：success 为必填且前端手写类型已含，保留）
export type ModelTestResult = Required<Schemas['ModelTestResponse']>

// 来源：components['schemas']['ModelTestToolCall']
export type ModelTestToolCall = Required<Schemas['ModelTestToolCall']>