import { fieldHooks } from '@/lib/field-hooks'

/**
 * fieldHooks 统一注册入口
 * 调用各 hook 文件 register 函数，在应用启动时一次性注册所有 config 域 fieldHook
 */

/** 注册列表富编辑器 hooks */
function registerListItemEditorHooks(): void {
  // R2-2-2 骨架——各 hook 按 dashboard 原版行为等价重写
  // 完整实现在后续迭代中补充
}

/** 注册字符串列表 hooks */
function registerStringListHooks(): void {
  // createStringListHook——别名/备用表达风格
}

/** 注册隐藏字段 hooks */
function registerHiddenFieldHooks(): void {
  // type: 'hidden' 跳过字段渲染
}

/** 注册 JSON 编辑器 hooks */
function registerJsonEditorHooks(): void {
  // JsonFieldHookFactory——MCPRoots/MCPServers 实时校验
}

/** 注册 chat 相关 hooks */
function registerChatHooks(): void {
  // chat-talk-value-rules / chat-prompts / chat-flow-selector
}

/** 注册学习规则 hooks */
function registerLearningRulesHooks(): void {
  // learning-rules / focus-whitelist / keyword-regex
}

/** 注册共享组编辑器 hooks */
function registerSharedGroupHooks(): void {
  // shared-group-editor
}

/** 注册平台账号编辑器 hooks */
function registerPlatformAccountsHooks(): void {
  // platform-accounts
}

/**
 * 统一注册所有 config 域 fieldHooks
 * 在应用启动时调用一次
 */
export function registerAllConfigHooks(): void {
  registerListItemEditorHooks()
  registerStringListHooks()
  registerHiddenFieldHooks()
  registerJsonEditorHooks()
  registerChatHooks()
  registerLearningRulesHooks()
  registerSharedGroupHooks()
  registerPlatformAccountsHooks()
}

/** 获取已注册的 fieldHooks 单例 */
export { fieldHooks }