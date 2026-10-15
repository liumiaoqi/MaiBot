import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ApiError } from '@/lib/http'

/**
 * 只替掉 `backendApi`，其余（尤其 `ApiError` 这个**真类**）保持原样：
 * `mutateConfig` 里判 `error instanceof ApiError`，拿假类替掉会让 409 分支静默失效
 * ——测试就变成"验了一个不存在的世界"。
 */
const { postMock } = vi.hoisted(() => ({ postMock: vi.fn() }))

vi.mock('@/lib/http', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/http')>()
  return {
    ...actual,
    backendApi: { get: vi.fn(), post: postMock },
  }
})

import {
  ConfigRevisionConflictError,
  mutateConfig,
  readConfigPaths,
} from '../config-api'

const API_BASE = '/api/webui/config'

beforeEach(() => {
  postMock.mockReset()
})

describe('B · 接缝 API 的线格式契约', () => {
  describe('readConfigPaths（POST /get）', () => {
    it('请求体与后端字段名逐字对齐（namespace + paths）', async () => {
      postMock.mockResolvedValue({ namespace: 'model', revision: 1, entries: [] })

      await readConfigPaths({ namespace: 'model', paths: ['api_providers[0].api_key'] })

      expect(postMock).toHaveBeenCalledWith(`${API_BASE}/get`, {
        body: { namespace: 'model', paths: ['api_providers[0].api_key'] },
        errorMessage: '读取配置失败',
      })
    })

    it('不给 paths ⇒ 发空数组（后端语义：空 = 该平面全部叶路径 + 已声明秘密）', async () => {
      postMock.mockResolvedValue({ namespace: 'bot', revision: 3, entries: [] })

      await readConfigPaths({ namespace: 'bot' })

      expect(postMock).toHaveBeenCalledWith(`${API_BASE}/get`, {
        body: { namespace: 'bot', paths: [] },
        errorMessage: '读取配置失败',
      })
    })

    it('响应原样透传：秘密叶是**三态标记**，不带真值', async () => {
      const entries = [
        { path: 'api_providers[0].name', value: 'DeepSeek', inherited: false, revision: 4 },
        {
          path: 'api_providers[0].api_key',
          value: { $secret: true, path: 'api_providers[0].api_key', set: true, kind: 'literal' },
          inherited: false,
          revision: 4,
        },
      ]
      postMock.mockResolvedValue({ namespace: 'model', revision: 4, entries })

      const result = await readConfigPaths({ namespace: 'model' })

      expect(result).toEqual({ namespace: 'model', revision: 4, entries })
      // 出站/入站两侧都不该出现"把标记换成真值"的行为
      expect(JSON.stringify(result)).not.toContain('sk-')
    })
  })

  describe('mutateConfig（POST /mutate）', () => {
    it('请求体：namespace + expectedRevision（驼峰别名）+ ops 逐字对齐', async () => {
      postMock.mockResolvedValue({
        namespace: 'model',
        revision: 5,
        applied: 1,
        message: "配置 'model' 已保存",
        needs_restart: true,
        restart_required_sections: ['model'],
        hot_reload: 'ok',
      })

      const ops = [{ op: 'set' as const, path: 'models[0].price_in', value: 99 }]
      const result = await mutateConfig({ namespace: 'model', expectedRevision: 4, ops })

      expect(postMock).toHaveBeenCalledWith(`${API_BASE}/mutate`, {
        body: { namespace: 'model', expectedRevision: 4, ops },
        errorMessage: '保存配置失败',
      })
      expect(result.revision).toBe(5)
      expect(result.needs_restart).toBe(true)
    })

    it('占位原样上行（前端不拿真值：发出去的是标记，不是密钥）', async () => {
      postMock.mockResolvedValue({
        namespace: 'model',
        revision: 6,
        applied: 1,
        message: 'ok',
        needs_restart: false,
        restart_required_sections: [],
        hot_reload: null,
      })
      const marker = {
        $secret: true as const,
        path: 'api_providers[0].api_key',
        set: true,
        kind: 'literal' as const,
        origin_name: 'DeepSeek',
      }

      await mutateConfig({
        namespace: 'model',
        expectedRevision: 5,
        ops: [{ op: 'set', path: 'api_providers[1].api_key', value: marker }],
      })

      const body = postMock.mock.calls[0][1].body as { ops: Array<{ value: unknown }> }
      expect(body.ops[0].value).toEqual(marker)
    })

    it('409 ⇒ ConfigRevisionConflictError 带双 revision，且**不重试**（只发一次）', async () => {
      postMock.mockRejectedValue(
        new ApiError('revision 冲突：期望 3，当前 5', {
          status: 409,
          errorCode: 'BIZ_STATE_CONFLICT',
          detail: {
            error_code: 'BIZ_STATE_CONFLICT',
            error_message: 'revision 冲突：期望 3，当前 5',
            details: { namespace: 'model', expected_revision: 3, current_revision: 5 },
          },
        }),
      )

      const promise = mutateConfig({
        namespace: 'model',
        expectedRevision: 3,
        ops: [{ op: 'set', path: 'models[0].price_in', value: 1 }],
      })

      await expect(promise).rejects.toBeInstanceOf(ConfigRevisionConflictError)
      await expect(promise).rejects.toMatchObject({
        namespace: 'model',
        expectedRevision: 3,
        currentRevision: 5,
      })
      // "不静默重试"在 API 层就是：409 之后没有第二次请求
      expect(postMock).toHaveBeenCalledTimes(1)
    })

    it('409 但错误体没有 details ⇒ 仍是冲突错误（revision 为 null，不假装知道）', async () => {
      postMock.mockRejectedValue(new ApiError('冲突', { status: 409, detail: undefined }))

      await expect(
        mutateConfig({ namespace: 'bot', expectedRevision: 1, ops: [{ op: 'unset', path: 'a' }] }),
      ).rejects.toMatchObject({
        name: 'ConfigRevisionConflictError',
        namespace: null,
        expectedRevision: null,
        currentRevision: null,
      })
    })

    it('400（认领被拒等）⇒ 原样抛 ApiError，文案不被吞掉', async () => {
      const refusal = '秘密占位认领失败：占位指向的位置没有值（set: false）'
      postMock.mockRejectedValue(
        new ApiError(refusal, {
          status: 400,
          errorCode: 'PARAM_INVALID',
          detail: { error_code: 'PARAM_INVALID', error_message: refusal },
        }),
      )

      await expect(
        mutateConfig({
          namespace: 'model',
          expectedRevision: 1,
          ops: [{ op: 'set', path: 'api_providers[0].api_key', value: { path: 'x', set: false } }],
        }),
      ).rejects.toThrow(refusal)
      expect(postMock).toHaveBeenCalledTimes(1)
    })

    it('非 409 的其它状态码不冒充冲突（404 配置文件缺失照旧是 ApiError）', async () => {
      postMock.mockRejectedValue(new ApiError('配置文件不存在', { status: 404 }))

      await expect(
        mutateConfig({ namespace: 'bot', expectedRevision: 1, ops: [{ op: 'unset', path: 'a' }] }),
      ).rejects.not.toBeInstanceOf(ConfigRevisionConflictError)
    })
  })
})
