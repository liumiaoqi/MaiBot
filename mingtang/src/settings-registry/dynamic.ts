import type { SettingsRegistryEntry } from './settings-registry'
import { settingsRegistry } from './settings-registry'

/** 动态登记结果 */
export interface DynamicRegistrationResult {
  errors: string[]
  count: number
}

/** Prompt 列表条目（模拟——实际由 config-api 加载） */
interface PromptListItem {
  name: string
  description?: string
}

/** Pack 市场条目（模拟——实际由 plugin-api 加载） */
interface PackListItem {
  id: string
  name: string
  description?: string
}

/** 从 Prompt 列表构建动态条目 */
function buildPromptEntries(prompts: PromptListItem[]): SettingsRegistryEntry[] {
  return prompts.map((prompt, index) => ({
    id: `dynamic:prompt:${prompt.name}`,
    title: prompt.name,
    category: 'prompt',
    group: 'files',
    keywords: [
      prompt.name,
      ...(prompt.description ? [prompt.description] : []),
    ],
    route: '/config/prompts',
    routeParams: { prompt: prompt.name },
    description: prompt.description,
    source: 'dynamic' as const,
    order: index,
  }))
}

/** 从 Pack 列表构建动态条目 */
function buildPackEntries(packs: PackListItem[]): SettingsRegistryEntry[] {
  return packs.map((pack, index) => ({
    id: `dynamic:pack:${pack.id}`,
    title: pack.name,
    category: 'plugin',
    group: 'market',
    keywords: [
      pack.name,
      ...(pack.description ? [pack.description] : []),
    ],
    route: '/config/pack-market/$packId',
    routeParams: { packId: pack.id },
    description: pack.description,
    source: 'dynamic' as const,
    order: index,
  }))
}

/**
 * 动态登记——Prompt 文件列表 + Pack 市场列表
 *
 * 加载前先清除旧的同前缀动态条目（unregisterByPrefix）
 * 错误不静默吞：console.error 并返回 { errors }
 */
export async function registerDynamicEntries(
  loadPrompts: () => Promise<PromptListItem[]>,
  loadPacks: () => Promise<PackListItem[]>
): Promise<DynamicRegistrationResult> {
  const errors: string[] = []
  const allEntries: SettingsRegistryEntry[] = []

  // 加载 Prompt 列表
  try {
    settingsRegistry.unregisterByPrefix('dynamic:prompt:')
    const prompts = await loadPrompts()
    const promptEntries = buildPromptEntries(prompts)
    allEntries.push(...promptEntries)
  } catch (e) {
    console.error('Prompt 列表加载失败:', e)
    errors.push('Prompt 列表加载失败')
  }

  // 加载 Pack 市场列表
  try {
    settingsRegistry.unregisterByPrefix('dynamic:pack:')
    const packs = await loadPacks()
    const packEntries = buildPackEntries(packs)
    allEntries.push(...packEntries)
  } catch (e) {
    console.error('Pack 市场加载失败:', e)
    errors.push('Pack 市场加载失败')
  }

  // 登记成功加载的条目
  settingsRegistry.registerAll(allEntries)

  return { errors, count: allEntries.length }
}