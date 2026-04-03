# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-01-30

### Added

- Initial release of AgentLite
- Core Agent class with streaming and non-streaming interfaces
- OpenAI-compatible provider implementation
- Tool system with decorator and class-based tools
- MCP client for loading tools from MCP servers
- Pydantic-based configuration system
- Multi-agent support
- Full type hints and async/await throughout
- Comprehensive documentation and examples

### Features

- **Agent**: Main agent class with tool calling loop
- **OpenAIProvider**: OpenAI API integration with streaming support
- **MCPClient**: MCP server integration for external tools
- **Tool System**: Decorator (`@tool`) and class-based (`CallableTool`, `CallableTool2`) tools
- **Configuration**: Pydantic models for providers, models, and agent settings
- **Message Types**: ContentPart, Message, ToolCall with streaming merge support

[0.1.0]: https://github.com/yourusername/agentlite/releases/tag/v0.1.0
