# AGENTS.md（docker-config/）

> 部署配置区。配置修改纪律（只改模板+版本号）见根 `../AGENTS.md` §五——不在此重复。

## 改哪个生效（血泪表）

| 路径 | 角色 |
|---|---|
| **`mmc/`** | ✅ **运行时真源**——compose 挂载 `./docker-config/mmc:/MaiMBot/config`，**改这里才生效** |
| `napcat/` | NapCat 客户端配置（挂载 `/app/napcat/config`） |
| `old/` | ⚠️ 手拷贝历史（30+ 份）——**不生效、不编辑**（考古用） |
| `*.broken_*` | 事故残留备份——不生效 |

## 规矩

1. **改配置只改 `mmc/`**——改完 `docker compose restart core` 生效
2. 程序会自动回写配置（CONFIG_VERSION 升级链）——**"我没动它怎么变了"先看这里**（详见根 pitfalls 与 `docs/`）
3. `old/` 与 `broken` 是**冻结归档**——不清理、不引用、不新增
