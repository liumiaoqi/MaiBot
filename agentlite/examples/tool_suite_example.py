"""Example demonstrating the configurable tool suite for AgentLite.

This example shows how to use the tool suite with configuration
to enable/disable specific tools.
"""

import asyncio
from pathlib import Path

from agentlite import Agent, OpenAIProvider
from agentlite.tools import (
    ConfigurableToolset,
    ToolSuiteConfig,
    FileToolsConfig,
    ShellToolsConfig,
)


async def main():
    """Demonstrate the configurable tool suite."""

    # Example 1: Default configuration (all tools enabled)
    print("=== Example 1: Default Configuration ===")
    config = ToolSuiteConfig()
    toolset = ConfigurableToolset(config)
    print(f"Enabled tools: {len(toolset.tools)}")
    for tool in toolset.tools:
        print(f"  - {tool.name}")

    # Example 2: Disable specific tools
    print("\n=== Example 2: Disable WriteFile ===")
    config = ToolSuiteConfig(
        file_tools=FileToolsConfig(
            tools={"WriteFile": False}  # Disable WriteFile
        )
    )
    toolset = ConfigurableToolset(config)
    print(f"Enabled tools: {len(toolset.tools)}")
    for tool in toolset.tools:
        print(f"  - {tool.name}")

    # Example 3: Disable entire tool groups
    print("\n=== Example 3: Disable Shell Tools ===")
    config = ToolSuiteConfig(shell_tools=ShellToolsConfig(enabled=False))
    toolset = ConfigurableToolset(config)
    print(f"Enabled tools: {len(toolset.tools)}")
    for tool in toolset.tools:
        print(f"  - {tool.name}")

    # Example 4: Custom file tool settings
    print("\n=== Example 4: Custom File Tool Settings ===")
    config = ToolSuiteConfig(
        file_tools=FileToolsConfig(
            max_lines=500,
            max_bytes=50 * 1024,  # 50KB
            allow_write_outside_work_dir=True,
        )
    )
    toolset = ConfigurableToolset(config)
    print(f"File tool settings:")
    print(f"  Max lines: {config.file_tools.max_lines}")
    print(f"  Max bytes: {config.file_tools.max_bytes}")
    print(f"  Allow outside work dir: {config.file_tools.allow_write_outside_work_dir}")

    # Example 5: Using with an Agent
    print("\n=== Example 5: Using with Agent ===")

    # Create a safe configuration (no shell, no write outside work dir)
    safe_config = ToolSuiteConfig(
        file_tools=FileToolsConfig(
            allow_write_outside_work_dir=False,
        ),
        shell_tools=ShellToolsConfig(enabled=False),
    )

    # This would require an API key to actually run
    # provider = OpenAIProvider(api_key="your-api-key", model="gpt-4")
    # agent = Agent(
    #     provider=provider,
    #     system_prompt="You are a helpful assistant with file access.",
    #     tools=ConfigurableToolset(safe_config).tools,
    # )

    print("Safe configuration created:")
    print("  - Shell tools: DISABLED")
    print("  - Write outside work dir: DISABLED")
    print("  - Read file: ENABLED")
    print("  - Glob/Grep: ENABLED")

    # Example 6: Dynamic configuration reload
    print("\n=== Example 6: Dynamic Reload ===")
    config = ToolSuiteConfig()
    toolset = ConfigurableToolset(config)
    print(f"Initial tools: {len(toolset.tools)}")

    # Disable some tools and reload
    config.file_tools.disable_tool("WriteFile")
    config.shell_tools.enabled = False
    toolset.reload()

    print(f"After reload: {len(toolset.tools)}")
    for tool in toolset.tools:
        print(f"  - {tool.name}")

    # Example 7: Using individual tools directly
    print("\n=== Example 7: Direct Tool Usage ===")

    from agentlite.tools.file import ReadFile, Glob

    # Create tools directly
    read_tool = ReadFile(work_dir=Path("."))
    glob_tool = Glob(work_dir=Path("."))

    # Use ReadFile
    result = await read_tool.read({"path": "README.md"})
    if not result.is_error:
        print(f"README.md: {len(result.output)} characters")
    else:
        print(f"Could not read README.md: {result.message}")

    # Use Glob
    result = await glob_tool.glob({"pattern": "*.py"})
    if not result.is_error:
        files = result.output.split("\n") if result.output else []
        print(f"Python files found: {len(files)}")
    else:
        print(f"Glob error: {result.message}")


if __name__ == "__main__":
    asyncio.run(main())
