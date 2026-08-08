import type { LocalizedText } from '@/types/config-schema'

/** 设置注册表条目——注册表的最小单元 */
export interface SettingsRegistryEntry {
  /** 唯一标识（如 `auto:bot:personality.nickname` / `manual:page:/config/bot` / `dynamic:prompt:chat`） */
  id: string
  /** 标题（多语言） */
  title: LocalizedText
  /** 功能域分类（如 bot / model / prompt / plugin） */
  category: string
  /** 分组（如 providers / models / files） */
  group?: string
  /** 搜索关键词（多语言数组——所有语言变体参与匹配） */
  keywords: LocalizedText[]
  /** 路由路径 */
  route: string
  /** 路由参数 */
  routeParams?: Record<string, string>
  /** 字段路径（如 `personality.nickname`——schema 自动登记才有） */
  fieldPath?: string
  /** schema 引用（如 `BotConfig`——schema 自动登记才有） */
  schemaRef?: string
  /** 描述（多语言——可选） */
  description?: LocalizedText
  /** 是否高级选项 */
  advanced?: boolean
  /** 自定义编辑器标识（fieldHooks replace/wrapper 标注） */
  customEditor?: string
  /** 来源：auto = schema 自动 / manual = 手动 / dynamic = 运行时动态 */
  source: 'auto' | 'manual' | 'dynamic'
  /** 排序权重 */
  order?: number
}

/** 设置注册表——管理所有设置条目的核心类 */
export class SettingsRegistry {
  private entries = new Map<string, SettingsRegistryEntry>()

  /** 注册单个条目（重复 id 覆盖） */
  register(entry: SettingsRegistryEntry): void {
    this.entries.set(entry.id, entry)
  }

  /** 批量注册 */
  registerAll(entries: SettingsRegistryEntry[]): void {
    for (const entry of entries) {
      this.register(entry)
    }
  }

  /** 注销单个条目（不存在 id 静默返回） */
  unregister(id: string): void {
    this.entries.delete(id)
  }

  /** 按来源注销条目 */
  unregisterBySource(source: 'auto' | 'manual' | 'dynamic'): void {
    for (const [id, entry] of this.entries) {
      if (entry.source === source) {
        this.entries.delete(id)
      }
    }
  }

  /** 按 id 前缀注销条目（如 `dynamic:prompt:` 清除所有 prompt 动态条目） */
  unregisterByPrefix(prefix: string): void {
    for (const id of this.entries.keys()) {
      if (id.startsWith(prefix)) {
        this.entries.delete(id)
      }
    }
  }

  /** 获取全部条目（按 order 排序） */
  getAll(): SettingsRegistryEntry[] {
    return Array.from(this.entries.values()).sort((a, b) => {
      const aOrder = a.order ?? Number.MAX_SAFE_INTEGER
      const bOrder = b.order ?? Number.MAX_SAFE_INTEGER
      return aOrder - bOrder
    })
  }

  /** 按分类获取条目 */
  getByCategory(category: string): SettingsRegistryEntry[] {
    return this.getAll().filter((e) => e.category === category)
  }

  /** 获取单个条目 */
  get(id: string): SettingsRegistryEntry | undefined {
    return this.entries.get(id)
  }

  /** 清空所有条目 */
  clear(): void {
    this.entries.clear()
  }

  /** 条目数量 */
  size(): number {
    return this.entries.size
  }
}

/** 全局单例 */
export const settingsRegistry = new SettingsRegistry()