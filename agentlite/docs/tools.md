# AgentLite Tool Suite

A comprehensive tool suite for AgentLite, inspired by kimi-cli's tools, with configuration support for enabling/disabling individual tools.

## Overview

This tool suite provides:

- **File Operations**: Read, write, edit, search files
- **Shell Execution**: Execute shell commands
- **Web Access**: Fetch URLs and search the web
- **Multi-Agent**: Task delegation and subagent creation
- **Utilities**: Todo lists and thinking tools
- **Configuration**: Fine-grained control over which tools are available

## Installation

The tool suite is included with AgentLite. No additional installation required.

## Quick Start

```python
from agentlite.tools import ConfigurableToolset, ToolSuiteConfig
from agentlite import Agent, OpenAIProvider

# Create toolset with default config (all tools enabled)
toolset = ConfigurableToolset()

# Create agent with tools
provider = OpenAIProvider(api_key="your-key", model="gpt-4")
agent = Agent(
    provider=provider,
    system_prompt="You are a helpful assistant.",
    tools=toolset.tools,
)
```

## Configuration

### Basic Configuration

```python
from agentlite.tools import (
    ToolSuiteConfig,
    FileToolsConfig,
    ShellToolsConfig,
)

# Disable specific tools
config = ToolSuiteConfig(
    file_tools=FileToolsConfig(
        tools={"WriteFile": False, "StrReplaceFile": False}
    )
)
toolset = ConfigurableToolset(config)
```

### Disable Entire Tool Groups

```python
# Disable all shell tools
config = ToolSuiteConfig(
    shell_tools=ShellToolsConfig(enabled=False)
)
toolset = ConfigurableToolset(config)
```

### Custom Tool Settings

```python
config = ToolSuiteConfig(
    file_tools=FileToolsConfig(
        max_lines=500,
        max_bytes=50 * 1024,  # 50KB
        allow_write_outside_work_dir=False,
    ),
    shell_tools=ShellToolsConfig(
        timeout=60,
        blocked_commands=["rm -rf", "sudo"],
    ),
)
```

### Dynamic Configuration

```python
# Create toolset
config = ToolSuiteConfig()
toolset = ConfigurableToolset(config)

# Disable tools and reload
config.file_tools.disable_tool("WriteFile")
config.shell_tools.enabled = False
toolset.reload()
```

## Available Tools

### File Tools

| Tool | Description | Config Options |
|------|-------------|----------------|
| `ReadFile` | Read text files with line numbers | `max_lines`, `max_bytes` |
| `WriteFile` | Write or append to files | `allow_write_outside_work_dir` |
| `StrReplaceFile` | Edit files using string replacement | `allow_write_outside_work_dir` |
| `Glob` | Search files using glob patterns | `max_glob_matches` |
| `Grep` | Search file contents with regex | - |
| `ReadMediaFile` | Read images and videos | `max_size_mb` |

### Shell Tools

| Tool | Description | Config Options |
|------|-------------|----------------|
| `Shell` | Execute shell commands | `timeout`, `blocked_commands` |

### Web Tools

| Tool | Description | Config Options |
|------|-------------|----------------|
| `FetchURL` | Fetch web page content | `timeout`, `user_agent` |
| `SearchWeb` | Search the web | `timeout` |

### Multi-Agent Tools

| Tool | Description | Config Options |
|------|-------------|----------------|
| `Task` | Delegate tasks to subagents | `max_steps` |
| `CreateSubagent` | Create custom subagents | - |

### Utility Tools

| Tool | Description |
|------|-------------|
| `SetTodoList` | Manage todo lists |
| `Think` | Record thinking steps |

## Safety Features

### Path Security

- Files outside the working directory require absolute paths
- Optional restriction on writing outside working directory
- Path traversal protection

### Shell Security

- Configurable command timeout
- Blocked command list
- No shell injection (uses `execve` style execution)

### Resource Limits

- File size limits
- Line count limits
- Glob match limits
- HTTP content size limits

## Examples

### Safe Configuration for Untrusted Agents

```python
from agentlite.tools import ToolSuiteConfig, FileToolsConfig, ShellToolsConfig

# Safe config - read-only file access, no shell
safe_config = ToolSuiteConfig(
    file_tools=FileToolsConfig(
        allow_write_outside_work_dir=False,
    ),
    shell_tools=ShellToolsConfig(enabled=False),
)

toolset = ConfigurableToolset(safe_config)
```

### Using Individual Tools

```python
from agentlite.tools.file import ReadFile, Glob
from pathlib import Path

# Create tools directly
read_tool = ReadFile(work_dir=Path("."))
glob_tool = Glob(work_dir=Path("."))

# Use tools
result = await read_tool.read({"path": "README.md"})
if not result.is_error:
    print(result.output)

result = await glob_tool.glob({"pattern": "*.py"})
if not result.is_error:
    print(result.output)
```

### Configuration from File

```python
import json
from agentlite.tools import ToolSuiteConfig

# Load config from file
with open("tool_config.json") as f:
    config_dict = json.load(f)

config = ToolSuiteConfig.model_validate(config_dict)
toolset = ConfigurableToolset(config)
```

## API Reference

### Config Classes

#### `ToolSuiteConfig`

Main configuration class for all tools.

```python
class ToolSuiteConfig(BaseModel):
    file_tools: FileToolsConfig
    shell_tools: ShellToolsConfig
    web_tools: WebToolsConfig
    multiagent_tools: MultiAgentToolsConfig
    misc_tools: ToolGroupConfig
```

#### `FileToolsConfig`

```python
class FileToolsConfig(ToolGroupConfig):
    max_lines: int = 1000
    max_line_length: int = 2000
    max_bytes: int = 100 * 1024
    allow_write_outside_work_dir: bool = False
    max_glob_matches: int = 1000
```

#### `ShellToolsConfig`

```python
class ShellToolsConfig(ToolGroupConfig):
    timeout: int = 60
    max_timeout: int = 300
    blocked_commands: list[str] = []
```

#### `WebToolsConfig`

```python
class WebToolsConfig(ToolGroupConfig):
    timeout: int = 30
    user_agent: str = "Mozilla/5.0 ..."
    max_content_length: int = 1024 * 1024
```

### ConfigurableToolset

```python
class ConfigurableToolset(SimpleToolset):
    def __init__(
        self,
        config: ToolSuiteConfig | None = None,
        work_dir: str | None = None,
    )
    
    def reload(self, config: ToolSuiteConfig | None = None) -> None
```

## License

MIT License - same as AgentLite.
