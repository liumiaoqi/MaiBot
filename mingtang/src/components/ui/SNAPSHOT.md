# shadcn/ui 组件版本快照（mingtang components/ui——2026-08-24 立）

> 背景：WB 调研建议 2——shadcn 是"复制源码"模式（非 npm 包），上游 bug 修复需手动合入——登记版本快照便于追踪/升级
> 快照规则：每批复制记录当时 snapshot 版本（组件文件头注释标注）；本文件只登记批次与时间，不改组件代码

## 快照历史

| 批次 | 时间 | 说明 | 组件数 |
|------|------|------|:---:|
| 初始版 | 2026-08-24 | mingtang R1-R4 复制基础（29 组件）——R1 前 shadcn 最新版 | 29 |
| 本次 | 2026-08-24 | 依赖更新后快照登记——katex 0.18 / vite 8.2.2 / eslint 10.9 | 29 |

## 组件清单（29）

> 组件名（目录见 src/components/ui/——各文件头注释含 shadcn 标准描述）

button / badge / card / dialog / input / label / select / textarea / tabs / dropdown-menu / popover / tooltip / avatar / scroll-area / checkbox / radio-group / switch / table / toast / separator / skeleton / alert-dialog / sheet / progress / slider / calendar / command / sonner / form

## 更新流程（上游 shadcn 更新时）

1. 对比上游 registry.json 变更（`pnpm dlx shadcn@latest diff`——若 CLI 支持）
2. 手动合入变更到对应组件（diff 应用）
3. 本快照追加一行（新日期 + 说明 + 组件数）
4. 跑三绿（test + lint + build）验证

> 为什么这样做：shadcn 复制源码 = 无版本锁定——不登记快照，上游升级后无法追溯"组件来自哪版"——bug 修复无从合入
