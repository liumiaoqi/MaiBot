<a id="-双语--bilingual"></a>

<div align="center">

  <!-- Language Switcher -->
  <a href="#-双语--bilingual">双语 / Bilingual</a> | <a href="docs/README_CN.md">中文</a> | <a href="docs/README_EN.md">English</a>

  <br>
  <br>

  <h1>麦麦 MaiBot <sub><small>MaiSaka</small></sub></h1>
  <sub><sup>An interactive agent based on large language models.</sup></sub>

  <!-- Badges Row -->
  <p>
    <img src="https://img.shields.io/badge/Python-3.14+-blue" alt="Python Version">
    <img src="https://img.shields.io/github/license/liumiaoqi/MaiBot?label=License" alt="License">
    <img src="https://img.shields.io/badge/Status-In%20Development-yellow" alt="Status">
    <img src="https://img.shields.io/github/contributors/liumiaoqi/MaiBot.svg?style=flat&label=Contributors" alt="Contributors">
    <img src="https://img.shields.io/github/forks/liumiaoqi/MaiBot.svg?style=flat&label=Forks" alt="Forks">
    <img src="https://img.shields.io/github/stars/liumiaoqi/MaiBot?style=flat&label=Stars" alt="Stars">
    <a href="https://deepwiki.com/liumiaoqi/MaiBot"><img src="https://deepwiki.com/badge.svg" alt="Ask DeepWiki"></a>
  </p>
</div>

> **本仓库是 [刘妙奇 @liumiaoqi](https://github.com/liumiaoqi) 的独立分支** ——
> 基于 [Mai-with-u/MaiBot](https://github.com/Mai-with-u/MaiBot) 深度改造、独立维护。
> ☕ 如果这个方向对你有用，可以 [请麦麦喝杯奶茶](https://afdian.com/a/liumiaoqi)。

<br>

<!-- Mascot on the Right (Float) -->
<img src="depends-data/maimai-v2.png" align="right" width="40%" alt="MaiBot Character" style="margin-left: 20px; margin-bottom: 20px;">

<a id="english"></a>

## 介绍
<sub><sup>Introduction</sup></sub>

麦麦 MaiSaka 是一个基于大语言模型的可交互智能体。  
<sub><sup>MaiSaka is an interactive agent based on large language models.</sup></sub>

MaiSaka 不仅仅是一个机器人，不仅仅是一个可以帮你完成任务的“有帮助的助手”，她还是一个致力于了解你，并以真实人类的风格进行交互的数字生命。她不追求完美，不追求高效，但追求亲切和真实。  
<sub><sup>MaiSaka is more than just a bot, and more than a "helpful assistant" that completes tasks. She is a digital life form that tries to understand you and interact in a genuinely human style. She does not pursue perfection or efficiency above all else. She pursues warmth and authenticity.</sup></sub>

- 💭 **没有人喜欢 GPT 的语言风格**：麦麦使用了更加自然、贴合人类对话习惯的交互方式，不是长篇大论或者 markdown 格式的分点，而是或长或短的闲谈。  
  <sub><sup><strong>No one likes GPT-sounding dialogue</strong>: MaiSaka uses a more natural conversational style. Instead of long-winded markdown-heavy replies, she chats in a way that feels casual, varied, and human.</sup></sub>
- 🎭 **不再是傻乎乎的一问一答**：懂得在合适的时间说话，把握聊天中的气氛，在合适的时候开口，在合适的时候闭嘴。  
  <sub><sup><strong>No longer stuck in rigid Q&A</strong>: She knows when to speak, how to read the room, when to join a conversation, and when to stay quiet.</sup></sub>
- 🧠 **麦麦·成为人类**：在多人对话中，麦麦会模仿其他人的说话风格，还会自主理解新词或者小圈子里的黑话，不断进化。  
  <sub><sup><strong>MaiSaka becoming human</strong>: In group conversations, MaiSaka imitates how people around her speak, learns new slang and in-group language, and keeps evolving.</sup></sub>
- ❤️ **永远都在更加了解你**：基于心理学中人格理论，麦麦会不断积累对于你的了解，不论是你的信息、喜恶或是行为风格，她都记在心里。  
  <sub><sup><strong>Always learning more about you</strong>: Inspired by personality theory in psychology, MaiSaka gradually builds an understanding of your preferences, traits, habits, and behavior style.</sup></sub>
- 🔌 **插件系统**：提供强大的 API 和事件系统，拥有无限扩展可能。  
  <sub><sup><strong>Plugin system</strong>: Provides powerful APIs and an event system with virtually unlimited room for extension.</sup></sub>

### 快速导航
<sub><sup>Quick Navigation</sup></sub>

<p>
  <a href="https://www.bilibili.com/video/BV1amAneGE3P">🌟 演示视频（上游） <sub>Demo Video (upstream)</sub></a> &nbsp;|&nbsp;
  <a href="#-更新和安装--updates-and-installation">📦 快速入门 <sub>Quick Start</sub></a> &nbsp;|&nbsp;
  <a href="#-部署教程--deployment-guide">📃 核心文档 <sub>Core Documentation</sub></a> &nbsp;|&nbsp;
  <a href="#-讨论与社区--discussion-and-community">💬 加入社区 <sub>Join Community</sub></a>
</p>

<!-- Clear float to ensure subsequent content starts below the image area if text is short -->
<br clear="both">

<div align="center">
  <br>
  <a href="https://www.bilibili.com/video/BV1amAneGE3P" target="_blank">
    <picture>
      <source media="(max-width: 600px)" srcset="depends-data/video.png" width="100%">
      <img src="depends-data/video.png" width="60%" alt="麦麦演示视频" style="border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
    </picture>
    <br>
    <small>前往观看麦麦演示视频（由上游团队制作）/ Watch the MaiSaka demo video (made by the upstream team)</small>
  </a>
</div>

---

<a id="-更新和安装--updates-and-installation"></a>

## 🔥 更新和安装
<sub><sup>Updates and Installation</sup></sub>


> **最新版本: v0.x 筹备中（本分支版本线自 0.1.0 起）** ([📄 更新日志](changelogs/changelog.md))  
> <sub><sup><strong>Latest Version: v0.x in preparation (this branch's version line starts at 0.1.0)</strong> (<a href="changelogs/changelog.md">📄 Changelog</a>)</sup></sub>


- **下载**：前往 [上游 Release 页](https://github.com/MaiM-with-u/MaiBot/releases/) 下载最新版本（发布由上游维护）。  
  <sub><sup><strong>Download</strong>: Visit the <a href="https://github.com/MaiM-with-u/MaiBot/releases/">upstream Release page</a> to get the latest version (releases are maintained upstream).</sup></sub>

- **方便使用的 Windows 一键包 下载**：[Maibot-OK](https://github.com/Mai-with-u/MaiBotOneKey/releases/)（上游项目）  
  <sub><sup><strong>Launcher</strong>: <a href="https://github.com/Mai-with-u/MaiBotOneKey/releases/">Maibot OneKey</a> (upstream project)</sup></sub>


| 分支 / Branch | 说明 / Description |
| :--- | :--- |
| `main` | ✅ **稳定发布版本（推荐）**<br><sub><sup>Stable release (recommended)</sup></sub> |
| `dev` | 🚧 开发测试版本，包含新功能，可能不稳定<br><sub><sup>Development testing branch with new features, may be unstable</sup></sub> |

<a id="-部署教程--deployment-guide"></a>

### 📚 部署教程
<sub><sup>Deployment Guide</sup></sub>

👉 **[🚀 最新版本部署教程](https://docs.mai-mai.org/manual/deployment/)**  
<sub><sup>Latest Deployment Guide</sup></sub>

---

<a id="-讨论与社区--discussion-and-community"></a>

## 💬 讨论与社区
<sub><sup>Discussion and Community</sup></sub>

我们欢迎所有对 MaiBot 感兴趣的朋友加入！  
<sub><sup>We welcome everyone interested in MaiBot to join us.</sup></sub>

> ⚠️ 以下群组均为**上游社区**（本分支未另设社区；使用本分支遇到问题也欢迎提本仓 Issue）。  
> <sub><sup>The groups below belong to the **upstream community** (this branch has no separate community; issues in this repo are also welcome).</sup></sub>

| 类别 / Category | 群组 / Group | 说明 / Description |
| :--- | :--- | :--- |
| **技术交流**<br><sub><sup>Technical</sup></sub> | 麦麦脑电图:571780722<br><sub><sup>MaiBrain EEG</sup></sub> | 技术交流 / 答疑<br><sub><sup>Technical discussion / Q&A</sup></sub> |
| **技术交流**<br><sub><sup>Technical</sup></sub> | 麦麦大脑磁共振:766798517<br><sub><sup>MaiBrain MRI</sup></sub> | 技术交流 / 答疑<br><sub><sup>Technical discussion / Q&A</sup></sub> |
| **技术交流**<br><sub><sup>Technical</sup></sub> | [麦麦要当 VTB](https://qm.qq.com/q/wGePTl1UyY)<br><sub><sup>Mai Wants to Be a VTuber</sup></sub> | 技术交流 / 答疑<br><sub><sup>Technical discussion / Q&A</sup></sub> |
| **闲聊吹水**<br><sub><sup>Casual Chat</sup></sub> | [麦麦之闲聊群](https://qm.qq.com/q/JxvHZnxyec)<br><sub><sup>Mai Casual Chat Group</sup></sub> | 仅限闲聊，不答疑<br><sub><sup>Casual chat only, no support</sup></sub> |
| **插件开发**<br><sub><sup>Plugin Development</sup></sub> | 插件开发群:1036092828<br><sub><sup>Plugin Dev Group</sup></sub> | 进阶开发与测试<br><sub><sup>Advanced development and testing</sup></sub> |

---

## 📚 文档
<sub><sup>Documentation</sup></sub>

（本分支文档整理中。上游文档见 [docs.mai-mai.org](https://docs.mai-mai.org)——部分内容与本分支改造不完全同步，请以本仓实际代码为准。）  
<sub><sup>(Documentation for this branch is being organized. Upstream docs: <a href="https://docs.mai-mai.org">docs.mai-mai.org</a> — some content may not match this branch's modifications; the code in this repo prevails.)</sup></sub>

---

## 💡 设计理念
<sub><sup>Design Philosophy</sup></sub>

> **千石可乐说：**  
> <sub><sup><strong>SengokuCola says:</strong></sup></sub>
> - 这个项目最初只是为了给牛牛 bot 添加一点额外的功能，但是功能越写越多，最后决定重写。其目的是为了创造一个活跃在 QQ 群聊的“生命体”。目的并不是为了写一个功能齐全的机器人，而是一个尽可能让人感知到真实的类人存在。  
>   <sub><sup>This project originally started as a few extra features for the NiuNiu bot, but it kept growing until a full rewrite became inevitable. The goal was to create a "life form" active in QQ group chats, not a feature-complete bot, but something as human-like and real-feeling as possible.</sup></sub>
> - 程序的功能设计理念基于一个核心的原则：“最像而不是好”。  
>   <sub><sup>The core design principle is: "more lifelike, not merely better."</sup></sub>
> - 如果人类真的需要一个 AI 来陪伴自己，并不是所有人都需要一个完美的，能解决所有问题的“helpful assistant”，而是一个会犯错的，拥有自己感知和想法的“生命形式”。  
>   <sub><sup>If people truly want AI companionship, not everyone needs a perfect "helpful assistant" that solves every problem. Some people may want a life form that can make mistakes and has its own perceptions and thoughts.</sup></sub>

> **xxxxx 说：**  
> <sub><sup><strong>xxxxx says:</strong></sup></sub>  
> *Code is open, but the soul is yours.*

> **刘妙奇说：**  
> <sub><sup><strong>Liu Miaoqi says:</strong></sup></sub>  
> - 上游的麦麦追求"最像而不是好"——本分支继续这条线，往"记忆与连接"的方向走深一步。  
>   <sub><sup>The upstream MaiSaka pursues "more lifelike, not merely better". This branch carries that line further, toward memory-as-connection.</sup></sub>
> - 记忆不是存档，是连接：她记得住你，不在于存下了什么，而在于那些话之间亮起的灯。  
>   <sub><sup>Memory is not an archive but a web of connections — she remembers you not because something was stored, but because lights turn on between the words you said together.</sup></sub>
> - 不追完美，追真实——这一点上游说得很对，本分支只负责让它活得更久一点。  
>   <sub><sup>Not perfection, but authenticity — upstream got this right; this branch just tries to let it live a little longer.</sup></sub>

---

## 🙋 贡献和致谢
<sub><sup>Contributing and Acknowledgments</sup></sub>

欢迎参与贡献！请先阅读 [贡献指南](docs/CONTRIBUTE.md)。
<sub><sup>Contributions are welcome. Please read the <a href="docs/CONTRIBUTE.md">Contribution Guide</a> first.</sup></sub>

### 🌟 贡献者
<sub><sup>Contributors</sup></sub>

<a href="https://github.com/liumiaoqi/MaiBot/graphs/contributors">
  <img alt="contributors" src="https://contrib.rocks/image?repo=liumiaoqi/MaiBot" />
</a>

### ☕ 支持者鸣谢
<sub><sup>Supporters</sup></sub>

感谢每一位请麦麦喝奶茶的朋友（名单持续更新中）：

（虚位以待 —— 你会是第一位吗？）

### 🤝 开源项目友链
<sub><sup>Open Source Friends</sup></sub>

- **[AstrBot](https://github.com/AstrBotDevs/AstrBot)**: 优秀的LLM Agent项目

### ❤️ 特别致谢
<sub><sup>Special Thanks</sup></sub>

- **[萨卡班甲鱼](https://en.wikipedia.org/wiki/Sacabambaspis)**：千石可乐很喜欢的生物。  
  <sub><sup><strong><a href="https://en.wikipedia.org/wiki/Sacabambaspis">Sacabambaspis</a></strong>: SengokuCola's favorite creature.</sup></sub>
- **[略nd](https://space.bilibili.com/1344099355)**：为麦麦绘制早期的精美人设。  
  <sub><sup>Drew MaiSaka's beautiful early character design.</sup></sub>
- **[NapCat](https://github.com/NapNeko/NapCatQQ)**：现代化的基于 NTQQ 的 Bot 协议实现。  
  <sub><sup>A modern NTQQ-based bot protocol implementation.</sup></sub>

---

## 📊 仓库状态
<sub><sup>Repository Status</sup></sub>

<p>
  <img src="https://img.shields.io/github/stars/liumiaoqi/MaiBot?style=flat&label=Stars" alt="Stars">
  <img src="https://img.shields.io/github/forks/liumiaoqi/MaiBot?style=flat&label=Forks" alt="Forks">
  <img src="https://img.shields.io/github/issues/liumiaoqi/MaiBot?style=flat&label=Issues" alt="Issues">
  <img src="https://img.shields.io/github/last-commit/liumiaoqi/MaiBot?style=flat&label=Last%20Commit" alt="Last Commit">
  <img src="https://img.shields.io/github/repo-size/liumiaoqi/MaiBot?style=flat&label=Repo%20Size" alt="Repo Size">
</p>

### Star 趋势
<sub><sup>Star History</sup></sub>

[![Star 趋势](https://starchart.cc/liumiaoqi/MaiBot.svg?variant=adaptive)](https://starchart.cc/liumiaoqi/MaiBot)

---

## 📌 注意事项 & License
<sub><sup>Notice & License</sup></sub>

> [!IMPORTANT]
> 使用前请阅读 [用户协议 (EULA)](EULA.md) 和 [隐私协议](PRIVACY.md)。AI 生成内容请仔细甄别。  
> <sub><sup>Please read the <a href="EULA.md">End User License Agreement (EULA)</a> and <a href="PRIVACY.md">Privacy Policy</a> before use. Please evaluate AI-generated content carefully.</sup></sub>

**License**: GPL-3.0

---

[![](https://img.shields.io/badge/powered_by-dsh-4D6BFE?style=flat-square&logo=deepseek&logoColor=white)](https://github.com/deepseek-ai/deepseek-harness)
