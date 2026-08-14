/**
 * import-mode-schemas —— 导入表单「字段 schema 声明」（R4-2 最大债清理 · HA config flow 模式）。
 *
 * 背景：旧 useImportForm 平铺 65 个 useState + 7 个 submit 逐字重复骨架；旧 ImportTab 用
 * 7 个同构 TabsContent 块重复 Label+Input 样板（约 100-160 行/块）。
 *
 * 本文件把「一个字段是什么」全部声明化：key/type/label/description/default/validate/aliasKey。
 * - COMMON_IMPORT_SCHEMA：公共参数（可见 4 项 + 高级 8 项——聊天流选择器是富组件，见 common-params-form）；
 * - IMPORT_MODE_SCHEMAS：7 种导入模式各自专属字段（upload/paste/raw_scan/lpmm_openie/
 *   lpmm_convert/temporal_backfill/maibot_migration）；
 * - PATH_PRECHECK_SCHEMA：路径预检卡（Card2）字段，复用同一套 state 生成机制。
 *
 * 设计边界（schema 化到什么程度）：
 * - uploadFiles（File[]）不进 schema（schema 值类型只有 string|boolean）——文件是特殊输入，
 *   由 UploadForm 自行渲染，hook 显式持有 state；
 * - 聊天流选择器是自定义富组件，不按普通字段渲染，但 importCommonChatId 仍是 schema 字段
 *   （高级参数里还有它的手动输入框）；
 * - maibot 跨字段校验（起始/结束时间倒挂、起始/结束 ID 倒挂）不属于单字段 validate，
 *   留在 import-payloads.ts 的 payload 构建器里（与旧实现一致）；
 * - 动态 min/max（依赖 settings 的并发上限、分块上限）不进 schema，由表单组件渲染时覆盖。
 */
import type { MemoryImportTaskKind } from '@/lib/memory-api'

export type ImportFieldType = 'text' | 'number' | 'datetime' | 'select' | 'checkbox'

/** schema 字段运行时值：字符串输入与开关布尔（uploadFiles 等特殊输入不进 schema） */
export type ImportFieldValue = string | boolean

export interface ImportFieldOption {
  value: string
  label: string
}

export interface ModeFieldSchema {
  /** 字段键，同时是 useImportForm 返回值里的字段名（如 pasteName → setPasteName） */
  key: string
  type: ImportFieldType
  /** 中文标签（渲染与无障碍共用） */
  label: string
  /** 说明文案（渲染在控件下方/右侧） */
  description?: string
  /** 初始值（同时是 settings seed「是否仍为默认」与别名联动 preferred 的依据） */
  defaultValue: ImportFieldValue
  /** select 专属选项 */
  options?: ImportFieldOption[]
  placeholder?: string
  /** number/datetime 专属上下限（渲染提示；动态上下限由表单组件覆盖——datetime 是字符串） */
  min?: number | string
  max?: number | string
  /** 长文本用 textarea 渲染 */
  multiline?: boolean
  /** 参与别名联动的字段（raw/lpmm/plugin_data 等路径别名自动选中第一个可用项） */
  aliasKey?: boolean
  /** 单字段校验：返回错误文案或 null（仅 string 型字段使用；跨字段校验在 payload 构建器） */
  validate?: (value: string) => string | null
}

const DATE_TIME_LOCAL_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,3})?)?$/
const POSITIVE_INTEGER_PATTERN = /^[1-9]\d*$/

function validateDatetimeLocal(fieldName: string): (value: string) => string | null {
  return (value: string) => {
    const trimmed = value.trim()
    if (!trimmed) {
      return null
    }
    if (!DATE_TIME_LOCAL_PATTERN.test(trimmed)) {
      return `${fieldName}格式无效，请使用时间选择器填写`
    }
    if (!Number.isFinite(new Date(trimmed).getTime())) {
      return `${fieldName}不是有效时间`
    }
    return null
  }
}

function validatePositiveInt(fieldName: string): (value: string) => string | null {
  return (value: string) => {
    const trimmed = value.trim()
    if (!trimmed) {
      return null
    }
    if (!POSITIVE_INTEGER_PATTERN.test(trimmed)) {
      return `${fieldName} 必须填写正整数`
    }
    if (!Number.isSafeInteger(Number(trimmed))) {
      return `${fieldName} 超过可支持的整数范围`
    }
    return null
  }
}

/** 公共参数（可见 4 项 + 高级 8 项；聊天流选择器为富组件单独渲染） */
export const COMMON_IMPORT_SCHEMA: readonly ModeFieldSchema[] = [
  {
    key: 'importCommonFileConcurrency',
    type: 'number',
    label: '文件并发数',
    description: '同时处理多少个文件；文件很多时再适当调高。',
    defaultValue: '2',
    min: 1,
  },
  {
    key: 'importCommonChunkConcurrency',
    type: 'number',
    label: '分块并发数',
    description: '单个文件内并行处理多少个分块；过高会增加资源占用。',
    defaultValue: '4',
    min: 1,
  },
  {
    key: 'importCommonLlmEnabled',
    type: 'checkbox',
    label: '启用 LLM 抽取',
    description: '需要模型参与抽取，质量更高但耗时更长。',
    defaultValue: true,
  },
  {
    key: 'importCommonChatLog',
    type: 'checkbox',
    label: '按聊天日志解析',
    description: '适合导入聊天记录，会尽量保留时间和对话上下文。',
    defaultValue: false,
  },
  {
    key: 'importCommonNarrativeWindowSize',
    type: 'number',
    label: '叙事抽取窗口',
    description: '用于 narrative/聊天日志。',
    defaultValue: '1600',
    min: 200,
  },
  {
    key: 'importCommonNarrativeOverlap',
    type: 'number',
    label: '叙事重叠字符',
    description: '保留跨块上下文。',
    defaultValue: '400',
    min: 0,
  },
  {
    key: 'importCommonFactualTargetSize',
    type: 'number',
    label: '事实分块目标',
    description: '用于 factual 结构感知切分。',
    defaultValue: '1200',
    min: 200,
  },
  {
    key: 'importCommonStrategyOverride',
    type: 'text',
    label: '指定抽取策略',
    defaultValue: 'auto',
  },
  {
    key: 'importCommonDedupePolicy',
    type: 'text',
    label: '去重策略',
    defaultValue: 'content_hash',
  },
  {
    key: 'importCommonChatReferenceTime',
    type: 'text',
    label: '聊天参考时间',
    defaultValue: '',
  },
  {
    key: 'importCommonChatId',
    type: 'text',
    label: '聊天流 ID',
    description: '仅填写已存在的真实聊天流 ID；上方下拉无法覆盖时再手动填写。',
    defaultValue: '',
    placeholder: '留空表示不绑定',
  },
  {
    key: 'importCommonForce',
    type: 'checkbox',
    label: '强制导入',
    defaultValue: false,
  },
  {
    key: 'importCommonClearManifest',
    type: 'checkbox',
    label: '清空导入清单',
    defaultValue: false,
  },
]

const INPUT_MODE_OPTIONS: ImportFieldOption[] = [
  { value: 'text', label: '文本' },
  { value: 'json', label: '结构化 JSON' },
]

/** 7 种导入模式的专属字段（uploadFiles File[] 不进 schema，由 UploadForm 自行渲染） */
export const IMPORT_MODE_SCHEMAS: Record<MemoryImportTaskKind, readonly ModeFieldSchema[]> = {
  upload: [
    {
      key: 'uploadInputMode',
      type: 'select',
      label: '输入模式',
      defaultValue: 'text',
      options: INPUT_MODE_OPTIONS,
    },
  ],
  paste: [
    { key: 'pasteName', type: 'text', label: '内容名称', defaultValue: '' },
    {
      key: 'pasteMode',
      type: 'select',
      label: '输入模式',
      defaultValue: 'text',
      options: INPUT_MODE_OPTIONS,
    },
    { key: 'pasteContent', type: 'text', label: '粘贴内容', defaultValue: '', multiline: true },
  ],
  raw_scan: [
    { key: 'rawAlias', type: 'text', label: '路径别名', defaultValue: 'raw', aliasKey: true },
    {
      key: 'rawInputMode',
      type: 'select',
      label: '输入模式',
      defaultValue: 'text',
      options: INPUT_MODE_OPTIONS,
    },
    { key: 'rawRelativePath', type: 'text', label: '相对路径', defaultValue: '' },
    { key: 'rawGlob', type: 'text', label: '匹配规则（Glob）', defaultValue: '*' },
    { key: 'rawRecursive', type: 'checkbox', label: '递归扫描', defaultValue: true },
  ],
  lpmm_openie: [
    { key: 'openieAlias', type: 'text', label: '路径别名', defaultValue: 'lpmm', aliasKey: true },
    { key: 'openieRelativePath', type: 'text', label: '相对路径', defaultValue: '' },
    { key: 'openieIncludeAllJson', type: 'checkbox', label: '包含全部 JSON 文件', defaultValue: false },
  ],
  lpmm_convert: [
    { key: 'convertAlias', type: 'text', label: '源路径别名', defaultValue: 'lpmm', aliasKey: true },
    {
      key: 'convertTargetAlias',
      type: 'text',
      label: '目标路径别名',
      defaultValue: 'plugin_data',
      aliasKey: true,
    },
    { key: 'convertRelativePath', type: 'text', label: '源相对路径', defaultValue: '' },
    { key: 'convertTargetRelativePath', type: 'text', label: '目标相对路径', defaultValue: '' },
    { key: 'convertDimension', type: 'number', label: '向量维度', defaultValue: '', min: 1 },
    { key: 'convertBatchSize', type: 'number', label: '批处理大小', defaultValue: '1024', min: 1 },
  ],
  temporal_backfill: [
    {
      key: 'backfillAlias',
      type: 'text',
      label: '路径别名',
      defaultValue: 'plugin_data',
      aliasKey: true,
    },
    { key: 'backfillLimit', type: 'number', label: '处理上限', defaultValue: '100000', min: 1 },
    { key: 'backfillRelativePath', type: 'text', label: '相对路径', defaultValue: '' },
    { key: 'backfillDryRun', type: 'checkbox', label: '只预演，不写入数据', defaultValue: false },
    { key: 'backfillNoCreatedFallback', type: 'checkbox', label: '禁用创建时间回退', defaultValue: false },
  ],
  maibot_migration: [
    {
      key: 'maibotSourceDb',
      type: 'text',
      label: '源数据库路径',
      defaultValue: '',
      placeholder: 'data/MaiBot.db',
      validate: (value) => (value.trim() ? null : '请填写源数据库路径'),
    },
    {
      key: 'maibotTimeFrom',
      type: 'datetime',
      label: '起始时间',
      defaultValue: '',
      validate: validateDatetimeLocal('起始时间'),
    },
    {
      key: 'maibotTimeTo',
      type: 'datetime',
      label: '结束时间',
      defaultValue: '',
      validate: validateDatetimeLocal('结束时间'),
    },
    {
      key: 'maibotStartId',
      type: 'number',
      label: '起始 ID',
      defaultValue: '',
      min: 1,
      validate: validatePositiveInt('起始 ID'),
    },
    {
      key: 'maibotEndId',
      type: 'number',
      label: '结束 ID',
      defaultValue: '',
      min: 1,
      validate: validatePositiveInt('结束 ID'),
    },
    { key: 'maibotStreamIds', type: 'text', label: '会话 ID 列表', defaultValue: '' },
    { key: 'maibotGroupIds', type: 'text', label: '群组 ID 列表', defaultValue: '' },
    { key: 'maibotUserIds', type: 'text', label: '用户 ID 列表', defaultValue: '' },
    {
      key: 'maibotReadBatchSize',
      type: 'number',
      label: '读取批大小',
      defaultValue: '2000',
      min: 1,
      validate: validatePositiveInt('读取批大小'),
    },
    {
      key: 'maibotCommitWindowRows',
      type: 'number',
      label: '提交窗口行数',
      defaultValue: '20000',
      min: 1,
      validate: validatePositiveInt('提交窗口行数'),
    },
    {
      key: 'maibotEmbedWorkers',
      type: 'number',
      label: '向量线程数',
      defaultValue: '',
      min: 1,
      validate: validatePositiveInt('向量线程数'),
    },
    { key: 'maibotNoResume', type: 'checkbox', label: '从头开始，不继续上次进度', defaultValue: false },
    { key: 'maibotResetState', type: 'checkbox', label: '重置迁移状态', defaultValue: false },
    { key: 'maibotDryRun', type: 'checkbox', label: '只预演，不写入数据', defaultValue: false },
    { key: 'maibotVerifyOnly', type: 'checkbox', label: '仅校验', defaultValue: false },
  ],
}

/** 路径预检卡（Card2）字段——复用同一套 schema state 生成，别名联动含 pathResolveAlias */
export const PATH_PRECHECK_SCHEMA: readonly ModeFieldSchema[] = [
  { key: 'pathResolveAlias', type: 'text', label: '路径别名', defaultValue: 'raw', aliasKey: true },
  {
    key: 'pathResolveRelativePath',
    type: 'text',
    label: '相对路径',
    defaultValue: '',
    placeholder: '例如 exports/weekly',
  },
  { key: 'pathResolveMustExist', type: 'checkbox', label: '要求路径已存在', defaultValue: true },
]

/** 全部表单字段（公共 + 7 模式 + 路径预检）——hook 一次生成全部 state */
export const ALL_IMPORT_FORM_FIELDS: readonly ModeFieldSchema[] = [
  ...COMMON_IMPORT_SCHEMA,
  ...Object.values(IMPORT_MODE_SCHEMAS).flat(),
  ...PATH_PRECHECK_SCHEMA,
]

/** 参与别名联动的字段（preferred 取各自 defaultValue） */
export const ALIAS_LINK_FIELDS: readonly ModeFieldSchema[] = ALL_IMPORT_FORM_FIELDS.filter(
  (field) => field.aliasKey,
)

/** 按 key 查找字段（缺字段即抛错——schema 声明与表单组件不同步时第一时间暴露） */
export function getImportField(schema: readonly ModeFieldSchema[], key: string): ModeFieldSchema {
  const field = schema.find((item) => item.key === key)
  if (!field) {
    throw new Error(`导入表单 schema 缺少字段: ${key}`)
  }
  return field
}

/** 构建 key → 字段 的映射，供表单组件按 key 取 label/description 渲染 */
export function buildImportFieldMap(schema: readonly ModeFieldSchema[]): Record<string, ModeFieldSchema> {
  const map: Record<string, ModeFieldSchema> = {}
  for (const field of schema) {
    map[field.key] = field
  }
  return map
}
