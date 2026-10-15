# AGENTS.md（mingtang/）

> 前端主战场。版本基线警告 / 三绿 / WebUI 规范见根 `../AGENTS.md` §三/§四——不在此重复。

## 命令（本机必带 `NODE_OPTIONS=` 避环境 shim）

```sh
NODE_OPTIONS= pnpm run lint / test / build   # 三绿（当前基线 142 文件 / 1357 用例）
NODE_OPTIONS= pnpm run dev                    # 开发服务（7999 端口）
```

## 结构

- `src/features/` — 9 个功能域（config / chat / memory / resource / monitor / agent / plugin / home / survey）
- `src/settings-registry/` — 设置注册表（独立体系，非 features 成员）
- `src/app/` — 路由 / 主题 / query 基础设施
- `dist/` — 构建产物（容器挂载此处，**宿主机 build 后即时生效**）

## 专属规矩

1. **测试先行**（vitest）：每个实现任务先写配套测试，不凑绿
2. **改完不急着 build**——dev server 验证优先
3. **jsdom 环境**：`URL.createObjectURL` 等浏览器 API 在测试里要 mock（jsdom 30.1 起行为变化——先例 `anonymize.test.ts`）
4. 写新代码前看根 §三 的 **TS 双轨版本基线**（旧知识写新代码必爆红）

## 已知坑

- `vite build` 清 dist/assets 被环境 shim 拦（≥50 文件 ⇒ 抛错）——**"build 时好时坏"就是它**，必须 `NODE_OPTIONS=`
- 主题切换写配置：后端 `webui_style` 是 **int**（0=modern / 1=future-retro）——前端需转换（2026-10-15 修复先例 `theme-provider.tsx`）
