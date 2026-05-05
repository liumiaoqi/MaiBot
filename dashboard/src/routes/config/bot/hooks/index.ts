/**
 * Bot 配置页面相关 hooks
 */

export { useAutoSave, useAutoSaveGeneric, useConfigAutoSave } from './useAutoSave'
export type {
  UseAutoSaveOptions,
  UseAutoSaveReturn,
  AutoSaveState,
  UseAutoSaveConfig,
  UseAutoSaveReturnGeneric,
} from './useAutoSave'
export {
  BotPlatformsHook,
  ChatPromptsHook,
  ChatTalkValueRulesHook,
  ExpressionGroupsHook,
  ExpressionLearningListHook,
  KeywordRulesHook,
  MCPRootItemsHook,
  MCPServersHook,
  RegexRulesHook,
} from './complexFieldHooks'
export { ChatSectionHook } from './ChatSectionHook'
export { PersonalitySectionHook } from './PersonalitySectionHook'
export { DebugSectionHook } from './DebugSectionHook'
export { ExpressionSectionHook } from './ExpressionSectionHook'
export { BotInfoSectionHook } from './BotInfoSectionHook'
