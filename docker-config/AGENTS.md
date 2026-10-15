# AGENTS.md（docker-config/）

> 部署配置区。配置修改纪律（只改模板+版本号）见根 `../AGENTS.md` §五——不在此重复。
> 层级语义见下节「配置的两层」；决策依据 `.shared/decisions/phase3_config_plan.md` **D3**（本文件不复述它的理由与翻案条件）。

## 配置的两层（单一真源 · 2026-10-15 立）

| 层 | 位置 | 定位 | 入库 |
|---|---|---|---|
| **模板层** | 仓根 `../config/` | **测试夹具 + 首启兜底**；只表达元数据与结构 | ❌ gitignored（`.gitignore` 的 `/config/*`）——**故永远不含真值** |
| **部署层** | 本目录 `mmc/` | **运行真值**（compose 挂载 `./docker-config/mmc:/MaiMBot/config`）——含 `${VAR}` 引用或本机明文 | ❌ 不入库（`.dockerignore` 覆盖） |

- **两层不合并**：生命周期不同——模板层随代码走（测试与首启就地生成），部署层随机器走（手工维护）。翻案条件见 D3。
- **容器内只有部署层**：容器看到的就是 `mmc/` 挂进去的那一份；仓根 `config/` 在容器里**不存在**，改它不影响运行中的 bot。
- **当前值只看 `mmc/` 根下**：`old/` 与 `broken` 只表达历史——"现在生效的是什么"，一律看 `mmc/bot_config.toml` 与 `mmc/model_config.toml`。
- ⚠️ **现状核对（2026-10-15）**：P2 密钥外部化**落地之前**，仓根 `config/model_config.toml` 的 `api_key` 实测仍是明文（非 `${VAR}`）⇒ 上表"永远不含真值"是**规范目标**（P2 上线后明文只应出现在部署层），不是当前实况。

## 改哪个生效（血泪表）

| 路径 | 角色 |
|---|---|
| **`mmc/`** | ✅ **运行时真源**——compose 挂载 `./docker-config/mmc:/MaiMBot/config`，**改这里才生效** |
| `napcat/` | NapCat 客户端配置（挂载 `/app/napcat/config`） |
| `mmc/old/` | ⚠️ 真配置历史（**34 份**，含密钥）——**不生效、不编辑、不清理**（去留待 lmq 拍板） |
| `*.broken_*` | 事故残留备份——不生效。已知 2 份（`bot_config.toml.broken_20260809/10`）已在**本批配置收口（2026-10-15/16）**清理；今后的同类残留同样**只归档、不编辑** |

## 规矩

1. **改配置只改 `mmc/`**——改完 `docker compose restart core` 生效
2. 程序会自动回写配置（CONFIG_VERSION 升级链）——**"我没动它怎么变了"先看这里**（详见根 pitfalls 与 `docs/`）
3. **`mmc/old/` 是冻结归档**——不清理、不引用、不新增；它由程序写出前的备份分支（`src/config/config.py` 的 `backup_root` 段）与手工拷贝共同累积，**只被写、不被读**
4. **绝不提交 `mmc/` 下的真配置内容**（含密钥）——`.gitignore` 覆盖整个 `docker-config/`，当前仅本文件被强制纳入版本库；**别对 `mmc/` 用 `git add -f`**
