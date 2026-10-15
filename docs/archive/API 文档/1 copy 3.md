> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Plan 概要

> Token Plan 的订阅和使用概要

<img src="https://filecdn.minimax.chat/public/token-plan-hero-v4.png" alt="Token Plan" style={{ display: "block", margin: "0 auto", maxWidth: "100%", borderRadius: "12px" }} />

## 欢迎使用 Token Plan！

MiniMax 在语言、视频、语音、音乐和图像等方向研发模型。[Token Plan](https://platform.minimaxi.com/subscribe/token-plan) 通过订阅 Key 提供套餐内 Token Plan 用量额度，覆盖语言模型之外的更多资源。

## 核心优势

<CardGroup cols={3}>
  <Card title="全模态覆盖" icon="layers">
    一个订阅通过统一的用量进度条覆盖可用的 MiniMax 资源。
  </Card>

  <Card title="面向 Agent 工作流" icon="zap">
    套餐面向长上下文 Agent、编程和多模态工作流设计。
  </Card>

  <Card title="极具性价比" icon="piggy-bank">
    固定订阅费提供更广的资源覆盖，并让用量规则更清晰。
  </Card>
</CardGroup>

## 订阅 Key

每位用户在所属的每个团队中都有一把专属的 **订阅 Key**。这把 Key 可以在团队尚未购买 Token Plan 席位或积分时就存在。如果用户当前没有可用资源，这把 Key 暂时没有可用的付费资源。当用户被分配 Token Plan 席位，或获得积分使用权限后，同一把订阅 Key 即可使用这些资源。

订阅和积分规则请参考 [Token Plan 定价](/docs/guides/pricing-token-plan)。团队版请参考 [Token Plan 团队版](/docs/guides/pricing-token-plan-team)。

## 用量额度

[Token Plan](https://platform.minimaxi.com/subscribe/token-plan) 的用量额度在控制台以用量进度条展示。对于已有按量计费价格的 API 端点，用量会按对应按量计费价格扣减套餐内 Token Plan 额度。

|              | **Plus**     | **Max**           | **Ultra**           |
| :----------- | :----------- | :---------------- | :------------------ |
| **价格**       | **¥49 /月**   | **¥119 /月**       | **¥469 /月**         |
| **适合场景**     | 轻量个人开发与日常试用  | 高频编程 Agent 与多模态调用 | 重度 Agent 工作流与更长时间使用 |
| **额度窗口**     | 5 小时固定窗口和周窗口 | 5 小时固定窗口和周窗口      | 5 小时固定窗口和周窗口        |
| **Agent 用量** | 3-4 个 Agent  | 4-5 个 Agent       | 6-7 个 Agent         |

<div style={{ fontSize: "11px", color: "#6b7280", lineHeight: 1.35, marginTop: "-16px", marginBottom: "12px" }}>可用模型覆盖 MiniMax 全系模型（M3 / M2.7 / 图像 / 语音 / 音乐），少量特殊模型（MiniMax H3、音色设计、快速复刻等）暂不支持。</div>

<Tip>
  如需通过订阅 Key 调用支持的多模态资源，请参考 [MiniMax CLI 指南](https://platform.minimaxi.com/docs/token-plan/minimax-cli)。
</Tip>

## 快速指南

<Steps>
  <Step title="订阅或获得资源分配">
    访问 [Token Plan](https://platform.minimaxi.com/subscribe/token-plan) 订阅页面，在默认团队中购买个人订阅或积分；也可以加入团队，并使用团队分配的 Token Plan 席位或共享积分。
  </Step>

  <Step title="获取订阅 Key">
    前往 [账户管理 / Token Plan](https://platform.minimaxi.com/user-center/payment/token-plan) 页面，查看您的可用资源并获取 **订阅 Key**。
  </Step>
</Steps>

<Info>
  **重要提示**

  * 订阅 Key 用于 Token Plan 订阅套餐和已购积分。
  * 订阅 Key 与按量计费 API Key 不可互换。
  * 订阅 Key 可以在付费资源可用之前就存在；当用户拥有 Token Plan 席位或积分权限后才可实际使用资源。
  * 请妥善保管您的 API Key，防止资源损失。
</Info>

## 在 AI Agent 与编程工具中使用

挑选你常用的工具，按对应教程接入：

<CardGroup cols={3}>
  <Card title="OpenClaw" icon="bot" href="/docs/token-plan/openclaw" />

  <Card title="Claude Code" icon="terminal" href="/docs/token-plan/claude-code" />

  <Card title="Cursor" icon="square-code" href="/docs/token-plan/cursor" />

  <Card title="TRAE" icon="code" href="/docs/token-plan/trae" />

  <Card title="Hermes Agent" icon="sparkles" href="/docs/token-plan/hermes-agent" />
</CardGroup>

其他工具的接入方式见 [其他工具](/docs/token-plan/other-tools)。

## 达到用量上限后

当您达到 5 小时固定窗口额度或周窗口额度后，可选择以下方式：

1. **使用已购积分**：
   如果已购积分可用，Token Plan 资源覆盖范围内的用量可由已购积分自动补充支付。
2. **升级或获得新的分配**：
   升级订阅，或请团队 Owner / Admin 分配更高额度的可用套餐。
3. **切换至按量计费**：
   如需继续使用且不受限制，您可将订阅 Key 替换为您的[按量计费 API Key](https://platform.minimaxi.com/user-center/basic-information/interface-key)，切换至按实际 Token 用量计费模式，费用将从您的 API 账户余额中扣除。
4. **等待额度窗口重置**：
   套餐内 Token Plan 额度按 5 小时固定窗口和周窗口控制；未使用完的订阅额度不会结转到下一个计费周期。

## 下一步

<CardGroup cols={3}>
  <Card title="快速开始" icon="rocket" href="/docs/token-plan/quickstart">
    用 5 分钟跑通你的第一次 MiniMax API 调用。
  </Card>

  <Card title="常见问题" icon="info" href="/docs/token-plan/faq">
    用量、计费、切换、退款等高频问题集合。
  </Card>

  <Card title="活动 & 优惠" icon="gift" href="/docs/token-plan/promotion">
    查看当前进行中的优惠活动。
  </Card>
</CardGroup>
> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Token Plan 概要

> Token Plan 的订阅和使用概要

<img src="https://filecdn.minimax.chat/public/token-plan-hero-v4.png" alt="Token Plan" style={{ display: "block", margin: "0 auto", maxWidth: "100%", borderRadius: "12px" }} />

## 欢迎使用 Token Plan！

MiniMax 在语言、视频、语音、音乐和图像等方向研发模型。[Token Plan](https://platform.minimaxi.com/subscribe/token-plan) 通过订阅 Key 提供套餐内 Token Plan 用量额度，覆盖语言模型之外的更多资源。

## 核心优势

<CardGroup cols={3}>
  <Card title="全模态覆盖" icon="layers">
    一个订阅通过统一的用量进度条覆盖可用的 MiniMax 资源。
  </Card>

  <Card title="面向 Agent 工作流" icon="zap">
    套餐面向长上下文 Agent、编程和多模态工作流设计。
  </Card>

  <Card title="极具性价比" icon="piggy-bank">
    固定订阅费提供更广的资源覆盖，并让用量规则更清晰。
  </Card>
</CardGroup>

## 订阅 Key

每位用户在所属的每个团队中都有一把专属的 **订阅 Key**。这把 Key 可以在团队尚未购买 Token Plan 席位或积分时就存在。如果用户当前没有可用资源，这把 Key 暂时没有可用的付费资源。当用户被分配 Token Plan 席位，或获得积分使用权限后，同一把订阅 Key 即可使用这些资源。

订阅和积分规则请参考 [Token Plan 定价](/docs/guides/pricing-token-plan)。团队版请参考 [Token Plan 团队版](/docs/guides/pricing-token-plan-team)。

## 用量额度

[Token Plan](https://platform.minimaxi.com/subscribe/token-plan) 的用量额度在控制台以用量进度条展示。对于已有按量计费价格的 API 端点，用量会按对应按量计费价格扣减套餐内 Token Plan 额度。

|              | **Plus**     | **Max**           | **Ultra**           |
| :----------- | :----------- | :---------------- | :------------------ |
| **价格**       | **¥49 /月**   | **¥119 /月**       | **¥469 /月**         |
| **适合场景**     | 轻量个人开发与日常试用  | 高频编程 Agent 与多模态调用 | 重度 Agent 工作流与更长时间使用 |
| **额度窗口**     | 5 小时固定窗口和周窗口 | 5 小时固定窗口和周窗口      | 5 小时固定窗口和周窗口        |
| **Agent 用量** | 3-4 个 Agent  | 4-5 个 Agent       | 6-7 个 Agent         |

<div style={{ fontSize: "11px", color: "#6b7280", lineHeight: 1.35, marginTop: "-16px", marginBottom: "12px" }}>可用模型覆盖 MiniMax 全系模型（M3 / M2.7 / 图像 / 语音 / 音乐），少量特殊模型（MiniMax H3、音色设计、快速复刻等）暂不支持。</div>

<Tip>
  如需通过订阅 Key 调用支持的多模态资源，请参考 [MiniMax CLI 指南](https://platform.minimaxi.com/docs/token-plan/minimax-cli)。
</Tip>

## 快速指南

<Steps>
  <Step title="订阅或获得资源分配">
    访问 [Token Plan](https://platform.minimaxi.com/subscribe/token-plan) 订阅页面，在默认团队中购买个人订阅或积分；也可以加入团队，并使用团队分配的 Token Plan 席位或共享积分。
  </Step>

  <Step title="获取订阅 Key">
    前往 [账户管理 / Token Plan](https://platform.minimaxi.com/user-center/payment/token-plan) 页面，查看您的可用资源并获取 **订阅 Key**。
  </Step>
</Steps>

<Info>
  **重要提示**

  * 订阅 Key 用于 Token Plan 订阅套餐和已购积分。
  * 订阅 Key 与按量计费 API Key 不可互换。
  * 订阅 Key 可以在付费资源可用之前就存在；当用户拥有 Token Plan 席位或积分权限后才可实际使用资源。
  * 请妥善保管您的 API Key，防止资源损失。
</Info>

## 在 AI Agent 与编程工具中使用

挑选你常用的工具，按对应教程接入：

<CardGroup cols={3}>
  <Card title="OpenClaw" icon="bot" href="/docs/token-plan/openclaw" />

  <Card title="Claude Code" icon="terminal" href="/docs/token-plan/claude-code" />

  <Card title="Cursor" icon="square-code" href="/docs/token-plan/cursor" />

  <Card title="TRAE" icon="code" href="/docs/token-plan/trae" />

  <Card title="Hermes Agent" icon="sparkles" href="/docs/token-plan/hermes-agent" />
</CardGroup>

其他工具的接入方式见 [其他工具](/docs/token-plan/other-tools)。

## 达到用量上限后

当您达到 5 小时固定窗口额度或周窗口额度后，可选择以下方式：

1. **使用已购积分**：
   如果已购积分可用，Token Plan 资源覆盖范围内的用量可由已购积分自动补充支付。
2. **升级或获得新的分配**：
   升级订阅，或请团队 Owner / Admin 分配更高额度的可用套餐。
3. **切换至按量计费**：
   如需继续使用且不受限制，您可将订阅 Key 替换为您的[按量计费 API Key](https://platform.minimaxi.com/user-center/basic-information/interface-key)，切换至按实际 Token 用量计费模式，费用将从您的 API 账户余额中扣除。
4. **等待额度窗口重置**：
   套餐内 Token Plan 额度按 5 小时固定窗口和周窗口控制；未使用完的订阅额度不会结转到下一个计费周期。

## 下一步

<CardGroup cols={3}>
  <Card title="快速开始" icon="rocket" href="/docs/token-plan/quickstart">
    用 5 分钟跑通你的第一次 MiniMax API 调用。
  </Card>

  <Card title="常见问题" icon="info" href="/docs/token-plan/faq">
    用量、计费、切换、退款等高频问题集合。
  </Card>

  <Card title="活动 & 优惠" icon="gift" href="/docs/token-plan/promotion">
    查看当前进行中的优惠活动。
  </Card>
</CardGroup>
> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimaxi.com/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# OpenClaw

> 在 OpenClaw 中使用最新的 MiniMax M 系列模型。

<div style={{background:"#fffbeb",borderLeft:"4px solid #d97706",padding:"12px 16px",borderRadius:"6px",margin:"16px 0"}}>[**OpenClaw**](https://github.com/openclaw/openclaw) 是本地运行的个人 AI 助手，可与多种通讯平台集成实现远程操控。</div>

## 安装 OpenClaw

在终端中运行以下命令安装（老用户同样可以用此命令更新）：

<Tabs>
  <Tab title="macOS / Linux">
    ```bash theme={null}
    curl -fsSL https://openclaw.bot/install.sh | bash
    ```
  </Tab>

  <Tab title="Windows">
    ```powershell theme={null}
    iwr -useb https://openclaw.ai/install.ps1 | iex
    ```
  </Tab>
</Tabs>

***

## 配置 MiniMax 模型

安装完成后会自动进入配置引导。若没有自动开始，运行：

```bash theme={null}
openclaw configure
```

选择认证方式开始配置：

<Tabs>
  <Tab title="OAuth 登录（推荐）">
    <Steps>
      <Step title="选择 Gateway 和模块">
        * Where will the Gateway run? → 选择 **Local (this machine)**
        * Select sections to configure → 选择 **Model**
        * Model/auth provider → 选择 **MiniMax**
        * MiniMax auth method → 选择 **MiniMax CN — OAuth (minimaxi.com)**

        <img src="https://filecdn.minimax.chat/public/31b13265-79e4-4162-8985-de00fbfe2b87.png" style={{borderRadius: '8px', marginTop: '12px', maxWidth: '100%'}} />
      </Step>

      <Step title="登录授权">
        自动弹出登录页，登录并授权。

        <img src="https://filecdn.minimax.chat/public/809a685b-8fca-4aa5-bdbf-4d2536f8f8fb.jpeg" style={{borderRadius: '8px', marginTop: '12px', maxWidth: '60%'}} />
      </Step>

      <Step title="确认模型">
        系统默认勾选 `MiniMax-M2.7` 和 `MiniMax-M3`，并将 M3 设为默认，直接回车确认即可。
      </Step>

      <Step title="验证">
        输入 `openclaw tui`，能正常对话即配置成功。

        <img src="https://filecdn.minimax.chat/public/3e6484e6-b944-4cb3-9fb0-70caa04d5c48.jpg" style={{borderRadius: '8px', marginTop: '12px', maxWidth: '100%'}} />
      </Step>
    </Steps>
  </Tab>

  <Tab title="API Key 手动配置">
    <Steps>
      <Step title="选择认证方式">
        * Where will the Gateway run? → 选择 **Local (this machine)**
        * Select sections to configure → 选择 **Model**
        * Model/auth provider → 选择 **MiniMax**
        * MiniMax auth method：
          * 中国大陆用户 → **MiniMax CN — API Key (minimaxi.com)**
          * 海外用户 → **MiniMax Global — API Key (minimax.io)**

        <img src="https://mintcdn.com/minimax-zh/kpwl9avqkcFIxqOO/images/openclaw-auth-method-apikey.png?fit=max&auto=format&n=kpwl9avqkcFIxqOO&q=85&s=afb339d8649cdc393dff2c9286569454" style={{borderRadius: '8px', marginTop: '12px', maxWidth: '100%'}} width="1594" height="418" data-path="images/openclaw-auth-method-apikey.png" />
      </Step>

      <Step title="填写 API Key">
        填入你的 MiniMax API Key，然后回车使用默认模型选项。
      </Step>

      <Step title="完成功能配置">
        按需配置以下选项：

        * **Channel**：选择在哪个 App 中对话
        * **Skill**：按需安装技能
        * **Hooks**（可选）：
          * 💾 `session-memory`：执行 `/new` 时自动保存会话上下文
          * 📝 `command-logger`：记录所有命令到日志文件
          * 🚀 `boot-md`：网关启动时运行 BOOT.md
      </Step>

      <Step title="验证">
        输入 `openclaw tui`，能正常对话即配置成功。

        <img src="https://filecdn.minimax.chat/public/f2775a9a-e0b8-4eef-b2f7-2440cc6e622d.png" style={{borderRadius: '8px', marginTop: '12px', maxWidth: '100%'}} />
      </Step>
    </Steps>
  </Tab>
</Tabs>

***

## 开关思考

运行时用 `/think` 开关思考：`off` 关闭，`adaptive`（默认）让 M3 自行决定何时思考。

***

## 进阶能力配置方法

### 识图能力

<Warning>
  OAuth 登录方式会**自动接入** MiniMax [图像理解 MCP 服务](/docs/token-plan/mcp-guide)，OpenClaw 的 `image` 工具开箱即用，无需额外配置。

  若使用 **API Key 手动配置**，或 OpenClaw 不是官方最新版（图像理解工具未自动接入），需通过下列方式之一为 Agent 补上识图能力。
</Warning>

<Tabs>
  <Tab title="方式 1（推荐）：MiniMax CLI">
    [MiniMax CLI](https://github.com/MiniMax-AI/cli)（命令名 `mmx`）是官方多模态命令行工具，装好后可让 OpenClaw 通过 `mmx vision` 实现图像理解，**同时复用文本/图像/视频/语音/音乐/搜索等 7 类多模态能力**。

    <Steps>
      <Step title="环境准备">
        确保 Node.js 18+ 已就绪：

        ```bash theme={null}
        # 检查 Node.js 版本（应 >= 18）
        node -v

        # 如未安装，推荐通过 nvm 安装 LTS 版本
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
        nvm install --lts
        ```
      </Step>

      <Step title="安装 MiniMax CLI">
        在终端运行以下命令完成全局安装：

        ```bash theme={null}
        npm install -g mmx-cli
        ```

        ⭐️ 或让 OpenClaw 一次性完成安装、登录与 SKILL 接入，提示词（请将 `sk-xxxxx` 替换为你的实际密钥）：

        ```plaintext theme={null}
        请帮我接入 MiniMax CLI（https://github.com/MiniMax-AI/cli），按以下三步完成安装与配置：

        1. 全局安装 CLI：执行 `npm install -g mmx-cli`，完成后用 `mmx --version` 验证
        2. 登录并配置 API Key：执行 `mmx auth login --api-key sk-xxxxx`
        3. 安装官方 SKILL：执行 `npx skills add MiniMax-AI/cli -y -g`

        完成后请执行 `mmx quota` 查看我的 Token Plan 余额，确认整体配置生效。
        ```
      </Step>

      <Step title="登录 API Key">
        使用 API Key 完成鉴权（请将 `sk-xxxxx` 替换为你的 Key）：

        ```bash theme={null}
        mmx auth login --api-key sk-xxxxx
        ```

        最新版 mmx-cli 会根据 Key 自动检测服务区域，通常无需手动配置 region。

        <Note>
          服务区域根据所使用的 API 服务是在国内平台（`cn`，[MiniMax 国内版订阅](https://platform.minimaxi.com/subscribe/token-plan)）还是在海外平台（`global`，[MiniMax 国际版订阅](https://platform.minimax.io/subscribe/token-plan)）上购买所决定。
        </Note>

        <Warning>
          若登录后调用接口报 401，大概率是 region 未自动匹配成功。可手动指定：

          ```bash theme={null}
          mmx config set --key region --value cn       # 国内 API 服务
          mmx config set --key region --value global   # 海外 API 服务
          ```

          执行 `mmx auth status` 确认当前 region 与所购买服务来源平台一致。
        </Warning>

        登录完成后，可执行 `mmx quota` 查看 Token Plan 套餐额度，确认整体配置生效。
      </Step>

      <Step title="安装 SKILL（可选，推荐 Agent 用户）">
        若你要在 OpenClaw 中调用 mmx 命令，建议加装官方 SKILL.md，Agent 调用时决策更准、无需临时翻 `--help`：

        ```bash theme={null}
        npx skills add MiniMax-AI/cli -y -g
        ```

        <Tip>
          SKILL 会自动 symlink 到 `~/.openclaw/skills/`，OpenClaw 下次启动即可识别。
        </Tip>
      </Step>

      <Step title="引导 OpenClaw 调用 mmx vision">
        告知 OpenClaw 后续识图需求优先走 `mmx vision`：

        ```plaintext theme={null}
        记住，之后要进行图像理解时优先使用 mmx vision 工具，
        通过 `mmx vision describe --image <图片路径或URL>` 调用并解析返回结果。
        ```
      </Step>

      <Step title="验证">
        在 OpenClaw 中发送图片，检查 OpenClaw 是否会自动调用 `mmx vision describe --image <路径>` 并返回正确的图像描述。
      </Step>
    </Steps>
  </Tab>

  <Tab title="方式 2：Token Plan MCP">
    通过 [Token Plan MCP](/docs/token-plan/mcp-guide) 接入 `understand_image` 工具。

    <Steps>
      <Step title="环境准备">
        确保 uv（Python 包管理器）已就绪：

        ```bash theme={null}
        # 检查是否已安装
        which uv

        # 如未安装，通过 pip 安装
        pip install uv

        # 或通过 curl 安装
        curl -LsSf https://astral.sh/uv/install.sh | sh

        # 若上述安装失败或速度很慢，可使用国内镜像加速：
        export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```
      </Step>

      <Step title="安装并配置 MCP">
        手动配置请参考 [Token Plan MCP 接入指南](/docs/token-plan/mcp-guide)，核心步骤：

        1. 安装 `mcporter` skill（MCP server 管理工具）
        2. 按照官方文档配置 `minimax-coding-plan-mcp`
        3. 设置 `MINIMAX_API_KEY` 环境变量（Token Plan API Key 以 `sk-cp` 开头）：

        ```bash theme={null}
        export MINIMAX_API_KEY="sk-..."
        ```

        ⭐️ 或让 OpenClaw 一次性完成，提示词（**把 `sk-xxxxxxx` 替换为你的实际 API Key**）：

        ```plaintext theme={null}
        先安装 mcporter skill，再按照 https://platform.minimaxi.com/docs/token-plan/mcp-guide 安装和配置 MCP，我的 MiniMax API Key 是 sk-xxxxxxx，最后再通过 mcporter skill 将其接入使用。
        ```
      </Step>

      <Step title="引导 OpenClaw 使用 understand_image">
        告知 OpenClaw 后续识图需求优先走 `understand_image`：

        ```plaintext theme={null}
        记住，之后要进行图像理解时需使用 minimax-coding-plan-mcp 的 understand_image 工具。
        ```
      </Step>

      <Step title="验证">
        在 OpenClaw 中发送图片，检查 OpenClaw 是否会自动调用 `understand_image` 工具并返回正确的图像描述。
      </Step>
    </Steps>
  </Tab>
</Tabs>

***

### 网络搜索

OpenClaw 默认不带网络搜索能力，可通过下列方式之一为 Agent 补上（适用于 Token Plan 订阅用户，API Key 以 `sk-cp` 开头）。

<Tabs>
  <Tab title="方法 1（推荐）：MiniMax CLI">
    `mmx search` 是 MiniMax CLI 提供的网络检索命令，无需额外 MCP server 进程，直接通过 Bash 调用即可。

    <Steps>
      <Step title="环境准备">
        确保 Node.js 18+ 已就绪：

        ```bash theme={null}
        # 检查 Node.js 版本（应 >= 18）
        node -v

        # 如未安装，推荐通过 nvm 安装 LTS 版本
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
        nvm install --lts
        ```
      </Step>

      <Step title="安装 MiniMax CLI">
        在终端运行以下命令完成全局安装：

        ```bash theme={null}
        npm install -g mmx-cli
        ```

        ⭐️ 或让 OpenClaw 一次性完成安装、登录与 SKILL 接入，提示词（请将 `sk-xxxxx` 替换为你的实际密钥）：

        ```plaintext theme={null}
        请帮我接入 MiniMax CLI（https://github.com/MiniMax-AI/cli），按以下三步完成安装与配置：

        1. 全局安装 CLI：执行 `npm install -g mmx-cli`，完成后用 `mmx --version` 验证
        2. 登录并配置 API Key：执行 `mmx auth login --api-key sk-xxxxx`
        3. 安装官方 SKILL：执行 `npx skills add MiniMax-AI/cli -y -g`

        完成后请执行 `mmx quota` 查看我的 Token Plan 余额，确认整体配置生效。
        ```
      </Step>

      <Step title="登录 API Key">
        使用 API Key 完成鉴权（请将 `sk-xxxxx` 替换为你的 Key）：

        ```bash theme={null}
        mmx auth login --api-key sk-xxxxx
        ```

        最新版 mmx-cli 会根据 Key 自动检测服务区域，通常无需手动配置 region。

        <Note>
          服务区域根据所使用的 API 服务是在国内平台（`cn`，[MiniMax 国内版订阅](https://platform.minimaxi.com/subscribe/token-plan)）还是在海外平台（`global`，[MiniMax 国际版订阅](https://platform.minimax.io/subscribe/token-plan)）上购买所决定。
        </Note>

        <Warning>
          若登录后调用接口报 401，大概率是 region 未自动匹配成功。可手动指定：

          ```bash theme={null}
          mmx config set --key region --value cn       # 国内 API 服务
          mmx config set --key region --value global   # 海外 API 服务
          ```

          执行 `mmx auth status` 确认当前 region 与所购买服务来源平台一致。
        </Warning>

        登录完成后，可执行 `mmx quota` 查看 Token Plan 套餐额度，确认整体配置生效。
      </Step>

      <Step title="安装 SKILL（可选，推荐 Agent 用户）">
        若你要在 OpenClaw 中调用 mmx 命令，建议加装官方 SKILL.md，Agent 调用时决策更准、无需临时翻 `--help`：

        ```bash theme={null}
        npx skills add MiniMax-AI/cli -y -g
        ```

        <Tip>
          SKILL 会自动 symlink 到 `~/.openclaw/skills/`，OpenClaw 下次启动即可识别。
        </Tip>
      </Step>

      <Step title="引导 OpenClaw 使用 mmx search">
        `mmx search` 提供两种调用形态：

        ```bash theme={null}
        # 简单调用（适合人类使用，输出可读文本）
        mmx search "MiniMax AI 最新进展"

        # 结构化调用（适合 Agent 解析）
        mmx search query --q "MiniMax M3 release" --output json
        ```

        让 OpenClaw 调用的提示词示例：

        ```plaintext theme={null}
        使用 mmx search 工具搜索“OpenClaw 多 Agent 编排”，
        以 `mmx search query --q "..." --output json` 形式拿到结构化结果后，
        总结排名前 3 条的标题、链接、关键摘要。
        ```

        OpenClaw 会通过 Bash 工具执行 `mmx search query --q "..." --output json`，把 stdout 的 JSON 直接交给模型解析，无需额外的 MCP server 进程。
      </Step>

      <Step title="记忆存储">
        ```plaintext theme={null}
        记住，之后要进行网络搜索时优先使用 mmx search 工具，
        通过 `mmx search query --q "..." --output json` 调用并解析返回的 JSON 结果。
        ```
      </Step>
    </Steps>
  </Tab>

  <Tab title="方法 2：Token Plan MCP">
    通过 [Token Plan MCP](/docs/token-plan/mcp-guide) 接入 `web_search` 工具。

    <Steps>
      <Step title="环境准备">
        确保 uv（Python 包管理器）已就绪：

        ```bash theme={null}
        # 检查是否已安装
        which uv

        # 如未安装，通过 pip 安装
        pip install uv

        # 或通过 curl 安装
        curl -LsSf https://astral.sh/uv/install.sh | sh

        # 若上述安装失败或速度很慢，可使用国内镜像加速：
        export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```
      </Step>

      <Step title="安装并配置 MCP">
        手动配置请参考 [Token Plan MCP 接入指南](/docs/token-plan/mcp-guide)，核心步骤：

        1. 安装 `mcporter` skill（MCP server 管理工具）
        2. 按照官方文档配置 `minimax-coding-plan-mcp`
        3. 设置 `MINIMAX_API_KEY` 环境变量（Token Plan API Key 以 `sk-cp` 开头）：

        ```bash theme={null}
        export MINIMAX_API_KEY="sk-..."
        ```

        ⭐️ 或让 OpenClaw 一次性完成，提示词（**把 `sk-xxxxxxx` 替换为你的实际 API Key**）：

        ```plaintext theme={null}
        先安装 mcporter skill，再按照 https://platform.minimaxi.com/docs/token-plan/mcp-guide 安装和配置 MCP，我的 MiniMax API Key 是 sk-xxxxxxx，最后再通过 mcporter skill 将其接入使用。
        ```
      </Step>

      <Step title="引导 OpenClaw 使用 web_search">
        告知 OpenClaw 后续搜索需求优先走 `web_search`：

        ```plaintext theme={null}
        记住，之后要进行网络搜索时需使用 minimax-coding-plan-mcp 的 web_search 工具。
        ```
      </Step>

      <Step title="验证">
        在 OpenClaw 中给出一个需要联网的问题，检查 OpenClaw 是否会自动调用 `web_search` 工具并返回搜索结果。
      </Step>
    </Steps>
  </Tab>
</Tabs>
