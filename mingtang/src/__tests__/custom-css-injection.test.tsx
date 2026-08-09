import { describe, it, expect } from 'vitest'
import customCssContent from '../../public/custom.css?raw'

describe('TE-2-2：custom.css 空文件注入', () => {
  it('public/custom.css 存在且为空', () => {
    expect(customCssContent).toBeDefined()
    expect(customCssContent.trim()).toBe('')
  })
})
