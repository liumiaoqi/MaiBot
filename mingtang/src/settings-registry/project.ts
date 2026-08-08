import type { SettingsRegistryEntry } from './settings-registry'
import type { SearchItem } from '@/types/search-item'
import { resolveLocalizedText, getAllLocalizedText } from '@/lib/config-label'

/** 将 SettingsRegistryEntry 投影为当前语言的 SearchItem */
export function projectToSearchItem(
  entry: SettingsRegistryEntry,
  language: string
): SearchItem {
  const title = resolveLocalizedText(entry.title, language)
  const description = resolveLocalizedText(entry.description, language)

  // keywords：所有语言变体全部参与匹配（跨语言匹配）
  const keywords = entry.keywords
    .flatMap((k) => getAllLocalizedText(k))
    .join(' ')

  return {
    id: entry.id,
    title,
    description,
    path: entry.route,
    category: entry.category,
    keywords,
  }
}

/** 批量投影 */
export function projectToSearchItems(
  entries: SettingsRegistryEntry[],
  language: string
): SearchItem[] {
  return entries.map((e) => projectToSearchItem(e, language))
}