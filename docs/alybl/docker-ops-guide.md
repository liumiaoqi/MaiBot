# MaiBot Docker 运维指南

## 目录结构

```
MaiBot/
├── src/                    # 源码（挂载到容器 /MaiMBot/src）
├── prompts/                # 提示词（挂载到容器 /MaiMBot/prompts）
├── bot.py                  # 主入口（挂载到容器 /MaiMBot/bot.py）
├── docker-compose.yml      # 编排配置
├── Dockerfile              # 镜像构建
├── docker-entrypoint.sh    # 容器入口脚本（镜像内）
├── docker-entrypoint-wrapper.sh  # 入口包装脚本（宿主机挂载）
├── docker-config/mmc/      # bot配置（挂载到容器 /MaiMBot/config）
├── data/MaiMBot/           # 数据目录（挂载到容器 /MaiMBot/data）
│   ├── plugins/            # 插件目录
│   ├── logs/               # 日志目录
│   └── emoji/              # 表情包
└── depends-data/           # 运行时资源文件
```

## 卷挂载说明

| 宿主机路径 | 容器路径 | 类型 | 说明 |
|-----------|---------|------|------|
| `./src` | `/MaiMBot/src` | 目录挂载 | 源码，修改即时生效 |
| `./prompts` | `/MaiMBot/prompts` | 目录挂载 | 提示词，修改即时生效 |
| `./bot.py` | `/MaiMBot/bot.py` | 文件挂载(只读) | 主入口脚本 |
| `./docker-config/mmc` | `/MaiMBot/config` | 目录挂载 | bot配置文件 |
| `./data/MaiMBot` | `/MaiMBot/data` | 目录挂载 | 数据共享目录 |
| `./data/MaiMBot/plugins` | `/MaiMBot/plugins` | 目录挂载 | 插件目录 |
| `./data/MaiMBot/logs` | `/MaiMBot/logs` | 目录挂载 | 日志目录 |
| `./depends-data` | `/MaiMBot/depends-data` | 目录挂载 | 运行时资源 |
| `site-packages` (命名卷) | `/MaiMBot/.venv` | 命名卷 | Python包，镜像更新不丢失 |
| `hf-cache` (命名卷) | `/root/.cache/huggingface` | 命名卷 | HuggingFace模型缓存 |

## 更新流程

### 日常更新（只改代码/提示词）

```bash
git pull                        # 拉取上游代码 → src/ prompts/ 自动更新
docker compose restart core     # 重启容器即生效
```

### 依赖变更（pyproject.toml/uv.lock 变了）

```bash
git pull
docker exec maim-bot-core uv sync --frozen --no-dev --no-install-project
docker compose restart core
```

### 大版本更新（系统依赖如 Playwright 变了）

```bash
git pull
docker build -t sengokucola/maibot:latest -f Dockerfile .
docker compose up -d core
docker exec maim-bot-core uv sync --frozen --no-dev --no-install-project
```

### 安装插件依赖

```bash
docker exec maim-bot-core uv pip install <package>
```

## 注意事项

- **不要用 `docker pull`** — 拉取官方镜像会覆盖本地修改，且 `.venv` 是命名卷不会自动更新
- **`git pull` 后检查冲突** — 如果上游改了我们修改过的文件，需手动解决
- **`.venv` 是命名卷** — 即使重建镜像，旧的包仍在卷中，需手动 `uv sync`
- **Windows CRLF 问题** — `.sh` 文件在 Windows 上可能有 CRLF 行尾符，Dockerfile 中已用 `sed -i 's/\r$//'` 修复 `docker-entrypoint.sh`，但 `docker-entrypoint-wrapper.sh` 从宿主机挂载，需确保宿主机文件为 LF 格式
- **重启 vs 重建** — 只改代码/配置用 `restart`，改了 Dockerfile 或 docker-compose.yml 用 `up -d`

## 已知定制修改

以下是对主程序的定制修改，`git pull` 合并上游时需关注这些文件：

| 文件 | 修改内容 |
|------|---------|
| `src/llm_models/payload_content/message.py` | Message 类添加 `reasoning_content` 字段 |
| `src/llm_models/model_client/openai_client.py` | `_convert_messages` 回传 reasoning_content；`_sanitize_messages_for_toolless_request` 保留 reasoning_content |
| `src/llm_models/utils.py` | `compress_messages` 重建 Message 时保留 reasoning_content |
| `src/maisaka/context/messages.py` | `AssistantMessage` 添加 `reasoning_content` 字段；`_build_message_from_sequence` 支持 reasoning_content |
| `src/maisaka/context/history.py` | 重建 `AssistantMessage` 时保留 reasoning_content |
| `src/maisaka/context/planner_messages.py` | 消息时间格式从 `HH:MM:SS` 改为 `MM-DD HH:MM:SS`，新增 `day` 属性显示星期几 |
| `src/maisaka/chat_loop_service.py` | 创建 `AssistantMessage` 时传入 reasoning_content；时间注入增加星期信息 |
| `src/maisaka/visual/message_limiter.py` | 重建 Message 时保留 reasoning_content |
| `src/maisaka/memory/mid_term.py` | 重建 Message 时保留 reasoning_content |
| `src/chat/replyer/maisaka_generator_base.py` | Replyer 时间注入增加星期信息 |
| `prompts/zh-CN/maisaka_chat.prompt` | Planner 时间感知指导 |
| `prompts/zh-CN/maisaka_chat_focus.prompt` | Focus Planner 时间感知指导 |
| `prompts/zh-CN/maisaka_replyer.prompt` | Replyer 时间感知指导 |
| `prompts/en-US/*.prompt` | 英文同步 |
| `prompts/ja-JP/*.prompt` | 日文同步 |
| `docker-entrypoint.sh` | 恢复 `exec python bot.py` 启动命令 |
| `Dockerfile` | 添加 CRLF 行尾符修复 |
| `docker-compose.yml` | 挂载 src/prompts/bot.py |

## 排障

### 容器反复重启

1. 检查日志：`docker logs maim-bot-core --tail 50`
2. 常见原因：
   - `docker-entrypoint.sh: not found` → CRLF 行尾符问题，检查宿主机 `.sh` 文件是否为 LF
   - `docker-entrypoint-wrapper.sh` 报错 → 宿主机挂载的 wrapper 脚本行尾符问题
   - Python 导入错误 → `.venv` 命名卷与镜像版本不匹配，尝试 `docker exec maim-bot-core uv sync`

### 插件加载失败

```bash
docker exec maim-bot-core uv pip install maibot-plugin-sdk --upgrade
docker exec maim-bot-core uv pip install <缺失的包>
docker compose restart core
```

### 查看容器内代码版本

```bash
docker exec maim-bot-core grep -n "reasoning_content" /MaiMBot/src/llm_models/payload_content/message.py
docker exec maim-bot-core grep -n "day=" /MaiMBot/src/maisaka/context/planner_messages.py
```