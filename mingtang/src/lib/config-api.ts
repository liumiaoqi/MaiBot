/**
 * 配置API客户端
 *
 * 请求样板（认证、解析、错误格式化）由 @/lib/http 的请求客户端承担；
 * 本文件只声明 endpoint、业务错误文案、响应解包规则与配置数据缓存。
 * 公开函数遵循 throw 契约：成功返回数据，失败抛 ApiError。
 */

import { ApiError, backendApi } from '@/lib/http'
import type { ConfigSchema } from '@/types/config-schema'

const API_BASE = '/api/webui/config'
export const BOT_CONFIG_UPDATED_EVENT = 'maibot:bot-config-updated'
const schemaRequestCache = new Map<string, Promise<ConfigSchema>>()
const configDataCache = new Map<string, { timestamp: number; request: Promise<Record<string, unknown>> }>()
const CONFIG_DATA_CACHE_TTL = 30_000

function unwrapConfigResponse(data: unknown): Record<string, unknown> {
  if (
    data &&
    typeof data === 'object' &&
    'config' in data &&
    (data as Record<string, unknown>).config &&
    typeof (data as Record<string, unknown>).config === 'object'
  ) {
    return (data as { config: Record<string, unknown> }).config
  }

  if (data && typeof data === 'object') {
    return data as Record<string, unknown>
  }

  return {}
}

function getCachedSchema(key: string, url: string): Promise<ConfigSchema> {
  const cachedRequest = schemaRequestCache.get(key)
  if (cachedRequest) {
    return cachedRequest
  }

  const request = backendApi
    .get<ConfigSchema>(url, { cache: 'no-store', errorMessage: '获取配置架构失败' })
    .catch((error: unknown) => {
      // HTTP 层失败（带 status 的 ApiError）保留被拒绝的 Promise 在缓存中，
      // 避免对失败的配置接口反复发起请求；请求未到达服务器等瞬时异常则剔除缓存后重抛
      if (!(error instanceof ApiError) || error.status === undefined) {
        schemaRequestCache.delete(key)
      }
      throw error
    })

  schemaRequestCache.set(key, request)
  return request
}

function getCachedConfigData(key: string, url: string): Promise<Record<string, unknown>> {
  const cachedRequest = configDataCache.get(key)
  if (cachedRequest && Date.now() - cachedRequest.timestamp < CONFIG_DATA_CACHE_TTL) {
    return cachedRequest.request
  }

  const request = backendApi
    .get<unknown>(url, { cache: 'no-store', errorMessage: '获取配置失败' })
    .then((data) => unwrapConfigResponse(data))
    .catch((error: unknown) => {
      // HTTP 层失败保留被拒绝的 Promise 在缓存中，避免反复请求失败接口；瞬时异常则剔除缓存后重抛
      if (!(error instanceof ApiError) || error.status === undefined) {
        configDataCache.delete(key)
      }
      throw error
    })

  configDataCache.set(key, { timestamp: Date.now(), request })
  return request
}

function invalidateConfigDataCache(key?: string): void {
  if (key) {
    configDataCache.delete(key)
    return
  }
  configDataCache.clear()
}

function notifyBotConfigUpdated(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(BOT_CONFIG_UPDATED_EVENT))
  }
}

/**
 * 获取麦麦主程序配置架构
 */
export async function getBotConfigSchema(): Promise<ConfigSchema> {
  return getCachedSchema('bot', `${API_BASE}/schema/bot`)
}

/**
 * 获取模型配置架构
 */
export async function getModelConfigSchema(): Promise<ConfigSchema> {
  return getCachedSchema('model', `${API_BASE}/schema/model`)
}

/**
 * 获取指定配置节的架构
 */
export async function getConfigSectionSchema(sectionName: string): Promise<ConfigSchema> {
  return getCachedSchema(`section:${sectionName}`, `${API_BASE}/schema/section/${sectionName}`)
}

/**
 * 获取麦麦主程序配置数据
 */
export async function getBotConfig(): Promise<Record<string, unknown>> {
  const data = await backendApi.get<unknown>(`${API_BASE}/bot`, {
    cache: 'no-store',
    errorMessage: '获取配置失败',
  })
  return unwrapConfigResponse(data)
}

/** Cached config data for lightweight status summaries. */
export async function getBotConfigCached(): Promise<Record<string, unknown>> {
  return getCachedConfigData('bot', `${API_BASE}/bot`)
}

/**
 * 获取模型配置数据
 */
export async function getModelConfig(): Promise<Record<string, unknown>> {
  const data = await backendApi.get<unknown>(`${API_BASE}/model`, {
    cache: 'no-store',
    errorMessage: '获取配置失败',
  })
  return unwrapConfigResponse(data)
}

/** Cached model config data for lightweight status summaries. */
export async function getModelConfigCached(): Promise<Record<string, unknown>> {
  return getCachedConfigData('model', `${API_BASE}/model`)
}

/**
 * 配置保存响应（后端 ConfigSaveResponse）
 */
export interface ConfigSaveResult {
  success: boolean
  message: string
  needs_restart: boolean
  restart_required_sections: string[]
}

/**
 * 更新麦麦主程序配置
 */
export async function updateBotConfig(
  config: Record<string, unknown>
): Promise<ConfigSaveResult> {
  const result = await backendApi.post<ConfigSaveResult>(`${API_BASE}/bot`, {
    body: config,
    errorMessage: '更新配置失败',
  })
  invalidateConfigDataCache('bot')
  notifyBotConfigUpdated()
  return result
}

/**
 * 获取麦麦主程序配置的原始 TOML 内容
 */
export async function getBotConfigRaw(): Promise<string> {
  return backendApi.get<string>(`${API_BASE}/bot/raw`, {
    cache: 'no-store',
    errorMessage: '获取原始配置失败',
  })
}

/**
 * 更新麦麦主程序配置（原始 TOML 内容）
 */
export async function updateBotConfigRaw(rawContent: string): Promise<ConfigSaveResult> {
  const result = await backendApi.post<ConfigSaveResult>(`${API_BASE}/bot/raw`, {
    body: { raw_content: rawContent },
    errorMessage: '更新配置失败',
  })
  invalidateConfigDataCache('bot')
  notifyBotConfigUpdated()
  return result
}

/**
 * 更新模型配置
 */
export async function updateModelConfig(
  config: Record<string, unknown>
): Promise<ConfigSaveResult> {
  const result = await backendApi.post<ConfigSaveResult>(`${API_BASE}/model`, {
    body: config,
    errorMessage: '更新配置失败',
  })
  invalidateConfigDataCache('model')
  return result
}

/**
 * 更新麦麦主程序配置的指定节
 */
export async function updateBotConfigSection(
  sectionName: string,
  sectionData: unknown
): Promise<ConfigSaveResult> {
  const result = await backendApi.post<ConfigSaveResult>(`${API_BASE}/bot/section/${sectionName}`, {
    body: sectionData,
    errorMessage: '更新配置失败',
  })
  invalidateConfigDataCache('bot')
  notifyBotConfigUpdated()
  return result
}

/**
 * 更新模型配置的指定节
 */
export async function updateModelConfigSection(
  sectionName: string,
  sectionData: unknown
): Promise<ConfigSaveResult> {
  const result = await backendApi.post<ConfigSaveResult>(`${API_BASE}/model/section/${sectionName}`, {
    body: sectionData,
    errorMessage: '更新配置失败',
  })
  invalidateConfigDataCache('model')
  return result
}

/**
 * 模型信息
 */
export interface ModelListItem {
  id: string
  name: string
  owned_by?: string
}

/**
 * 获取模型列表响应
 */
export interface FetchModelsData {
  models: ModelListItem[]
  provider?: string
  count: number
}

/**
 * 已注册的模型客户端类型
 */
export interface ModelClientType {
  client_type: string
  owner_plugin_id: string | null
  version: string
  description: string
  builtin: boolean
}

/**
 * 获取当前主程序与插件已注册的模型客户端类型
 */
export async function fetchModelClientTypes(): Promise<ModelClientType[]> {
  const body = await backendApi.get<{ client_types?: ModelClientType[] } | ModelClientType[]>(
    '/api/webui/models/client-types',
    {
      errorMessage: '获取模型客户端类型失败',
    }
  )
  return Array.isArray(body) ? body : Array.isArray(body?.client_types) ? body.client_types : []
}

/**
 * 获取指定提供商的可用模型列表
 * @param providerName 提供商名称（在 model_config.toml 中配置的名称）
 * @param parser 响应解析器类型 ('openai' | 'gemini')
 * @param endpoint 获取模型列表的端点（默认 '/models'）
 */
export async function fetchProviderModels(
  providerName: string,
  parser: 'openai' | 'gemini' = 'openai',
  endpoint: string = '/models'
): Promise<ModelListItem[]> {
  // 后端返回 { models, provider, count }，请求客户端已自动解包 ApiResponse
  const body = await backendApi.get<{ models?: ModelListItem[] } | ModelListItem[]>(
    '/api/webui/models/list',
    {
      query: {
        provider_name: providerName,
        parser,
        endpoint,
      },
      errorMessage: '获取模型列表失败',
    }
  )
  return Array.isArray(body) ? body : Array.isArray(body?.models) ? body.models : []
}

/**
 * 测试提供商连接结果
 */
export interface TestConnectionResult {
  network_ok: boolean
  api_key_valid: boolean | null
  latency_ms: number | null
  error: string | null
  http_status: number | null
}

/**
 * 单个模型测试返回的工具调用摘要
 */
export interface ModelTestToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

/**
 * 单个模型测试结果
 */
export interface ModelTestResult {
  success: boolean
  model_name: string
  visual_tested: boolean
  tool_call_ok: boolean
  response: string
  reasoning: string
  tool_calls: ModelTestToolCall[]
  latency_ms: number | null
  error: string | null
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

/**
 * 测试提供商连接状态（通过提供商名称）
 * @param providerName 提供商名称
 */
export async function testProviderConnection(
  providerName: string
): Promise<TestConnectionResult> {
  return backendApi.post<TestConnectionResult>('/api/webui/models/test-connection-by-name', {
    query: { provider_name: providerName },
    errorMessage: '测试提供商连接失败',
  })
}

/**
 * 测试单个模型的文本、tool call 与可选视觉能力
 * @param modelName 模型名称
 */
export async function testModelCapability(modelName: string): Promise<ModelTestResult> {
  return backendApi.post<ModelTestResult>('/api/webui/models/test-model', {
    body: { model_name: modelName },
    errorMessage: '测试模型能力失败',
  })
}

// ===== 2 段接缝（F1 路径操作 · F5 revision · F2 秘密三态）=====
//
// 与上面那些"整份 / 整节"端点并存：那些是**遗留入口**（5 段才拆），这里是写侧新接缝。
// 契约真源：`src/webui/routers/config.py::read_config_paths` / `mutate_config`，
// 请求体 `src/webui/schemas/config.py`，路径语法 `src/webui/config_paths.py`。
//
// 类型**放在这里**而不是 `features/config/seam/`：本仓的分层是 `lib → @/types`、
// `features → lib`（`lib/` 里没有一处 import `@/features/`），线格式类型跟 API 客户端同处一室
// 也正是本文件既有的做法（`ConfigSaveResult` / `TestConnectionResult` 都在这里）。

/** 路径 token：键是 `string`、数组下标是 `number`（镜像后端 `PathToken`） */
export type ConfigPathToken = string | number

/** 配置平面——后端 `config_store.namespace_spec` 只认这两个 */
export type ConfigNamespace = 'bot' | 'model'

/**
 * 秘密占位（F2 三键 `$secret`/`set`/`kind` + F3 的 `path`）。
 *
 * - `path` 是**来源路径**（不是提交位置）：写回时认领原值的依据（F3）。
 * - `set` 是**三态的中间态**：`true` = 已配置（真值没出站），`false` = 未配置。
 * - `kind` 只说"值放哪"：`literal` = 明文/字面量，`reference` = 整串 `${VAR}`（F4）；
 *   `set: false` 时后端**不带** `kind`（未配置的位置没有"值形态"可言）。
 * - `origin_name`：所属表项的 `name`，F3 规则①"按名认领"的依据。
 */
export interface ConfigSecretMarker {
  path: string
  $secret: true
  set: boolean
  kind?: 'literal' | 'reference'
  origin_name?: string
}

/** 读条目（`POST /get` 的 `entries[]` 项） */
export interface ConfigReadEntry {
  path: string
  /** 已存储的值；秘密路径是 `ConfigSecretMarker`（真值永不出站） */
  value: unknown
  /**
   * 该路径**有没有被覆盖**——判据是"文件里有没有这个键"，
   * **不是**"值等不等于 schema 默认值"（值恰好等于默认也可以是显式配的）。
   */
  inherited: boolean
  revision: number
}

/**
 * `POST /get` 的成功响应（`success` 前端不消费，故不声明）。
 */
export interface ConfigReadResult {
  namespace: ConfigNamespace
  /** 命名空间级单调版本号——写的时候**原样带回**（`expectedRevision`） */
  revision: number
  entries: ConfigReadEntry[]
}

/**
 * 一次路径操作（`POST /mutate` 的 `ops[]` 项）。
 *
 * ⚠️ **F8 约定**：`remove_at` 的 `path` 指**数组容器本身**、下标走 `index`
 * （`{op:'remove_at', path:'api_providers', index:1}`）——**不要**写成 `api_providers[1]`。
 * 读取路径里的下标则是正常语法（`api_providers[1].api_key` 合法），两处刻意不同。
 */
export interface ConfigMutateOp {
  op: 'set' | 'unset' | 'remove_at'
  path: string
  /** `set` 的新值；可以是原值，也可以是读回来的占位（后端按 F3 认领） */
  value?: unknown
  /** `remove_at` 要删的下标 */
  index?: number
}

/**
 * `POST /mutate` 的成功响应（字段名**照抄线格式**，与本文件的 `ConfigSaveResult` 同款口径——
 * 中间再套一层改名只会多一处漂移点）。
 */
export interface ConfigMutateResult {
  namespace: ConfigNamespace
  /** 写成功后的新版本号（失败时**不前进**：后端"校验不通过 ⇒ 文件一个字节不动、revision 也不前进"） */
  revision: number
  applied: number
  message: string
  needs_restart: boolean
  restart_required_sections: string[]
  /** `ok` / `refused_frozen`（**已落盘**但热重载被冻结态拒绝）/ `null`（该端点不触发热重载） */
  hot_reload: string | null
}

/**
 * 按路径读配置（`POST /get`）。
 *
 * `paths` 留空 ⇒ 该平面**已存储的全部叶路径 + 已声明的秘密路径**
 * （后者即使没配也回 `set: false`——"没配"本身就是要报告的状态）。
 * 秘密叶的 `value` 是**三态标记**，不是真值。
 */
export async function readConfigPaths(params: {
  namespace: ConfigNamespace
  paths?: string[]
}): Promise<ConfigReadResult> {
  return backendApi.post<ConfigReadResult>(`${API_BASE}/get`, {
    body: { namespace: params.namespace, paths: params.paths ?? [] },
    errorMessage: '读取配置失败',
  })
}

/**
 * 写配置的**版本冲突**（HTTP 409）。
 *
 * 语义（F5）：客户端读到的 `revision` 已经过期 ⇒ **不自动合并、不静默覆盖**。
 * 做成独立错误类型是为了让调用方**没法忽略**它：`catch` 拿到的不是一句泛泛的失败文案，
 * 而是一个必须显式处置的信号（提示用户"配置已被别处修改" + 提供重新加载）。
 */
export class ConfigRevisionConflictError extends Error {
  /** 冲突的命名空间 */
  readonly namespace: string | null
  /** 客户端以为的版本（请求里带上去的那个） */
  readonly expectedRevision: number | null
  /** 服务端当前版本 */
  readonly currentRevision: number | null

  constructor(
    message: string,
    details: {
      namespace?: string | null
      expectedRevision?: number | null
      currentRevision?: number | null
    } = {},
  ) {
    super(message)
    this.name = 'ConfigRevisionConflictError'
    this.namespace = details.namespace ?? null
    this.expectedRevision = details.expectedRevision ?? null
    this.currentRevision = details.currentRevision ?? null
  }
}

/** 从 409 的错误体里取双 revision（后端放在 `details` 里） */
function readConflictDetails(detail: unknown): {
  namespace: string | null
  expectedRevision: number | null
  currentRevision: number | null
} {
  const empty = { namespace: null, expectedRevision: null, currentRevision: null }
  if (detail === null || typeof detail !== 'object') {
    return empty
  }
  const raw = (detail as Record<string, unknown>).details
  if (raw === null || typeof raw !== 'object') {
    return empty
  }
  const details = raw as Record<string, unknown>
  return {
    namespace: typeof details.namespace === 'string' ? details.namespace : null,
    expectedRevision:
      typeof details.expected_revision === 'number' ? details.expected_revision : null,
    currentRevision: typeof details.current_revision === 'number' ? details.current_revision : null,
  }
}

/**
 * 按路径写配置（`POST /mutate`）。
 *
 * - **只发改动的点**：`ops` 由 `features/config/seam/config-adapter.ts` 的
 *   `diffToMutateOps` 从"基线 vs 当前草稿"算出；没被点名的路径根本不进写路径
 *   （页面上没有的字段不可能被整段 replace 吃掉）。
 * - `set` 的值可以是原值，也可以是**读回来的秘密占位**（后端按 F3 认领原值；
 *   认不到 ⇒ 400 并**拒绝整次写入**，绝不按位置猜）。
 * - `expectedRevision` 与当前不符 ⇒ 抛 `ConfigRevisionConflictError`（**不自动重试**）。
 *
 * @throws ConfigRevisionConflictError 版本冲突（409）
 * @throws ApiError 其余失败（400 路径/认领错误、404 配置文件缺失、5xx）
 */
export async function mutateConfig(params: {
  namespace: ConfigNamespace
  expectedRevision: number
  ops: ConfigMutateOp[]
}): Promise<ConfigMutateResult> {
  try {
    const result = await backendApi.post<ConfigMutateResult>(`${API_BASE}/mutate`, {
      body: {
        namespace: params.namespace,
        expectedRevision: params.expectedRevision,
        ops: params.ops,
      },
      errorMessage: '保存配置失败',
    })
    invalidateConfigDataCache(params.namespace)
    if (params.namespace === 'bot') {
      notifyBotConfigUpdated()
    }
    return result
  } catch (error: unknown) {
    if (error instanceof ApiError && error.status === 409) {
      throw new ConfigRevisionConflictError(error.message, readConflictDetails(error.detail))
    }
    throw error
  }
}
