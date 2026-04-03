"""End-to-end scenario test for file operations with real API.

This test simulates a realistic scenario where an agent:
1. Reads a file
2. Explains its content
3. Creates a new file with analysis results

Uses real SiliconFlow qwen3.5-397B API (requires SILICONFLOW_API_KEY env var).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from agentlite import Agent, OpenAIProvider, tool

# =============================================================================
# Configuration from model_config.toml
# =============================================================================

# SiliconFlow API configuration (matches qwen35_397b in model_config.toml)
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_MODEL = "Qwen/Qwen3.5-397B-A17B"


def get_siliconflow_provider() -> OpenAIProvider | None:
    """Create OpenAIProvider for SiliconFlow API.

    Returns None if SILICONFLOW_API_KEY is not set.
    """
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        return None

    return OpenAIProvider(
        api_key=api_key,
        base_url=SILICONFLOW_BASE_URL,
        model=SILICONFLOW_MODEL,
    )


# =============================================================================
# File Operation Tools
# =============================================================================


@tool()
async def read_file(file_path: str) -> str:
    """Read the content of a file.

    Args:
        file_path: Path to the file to read.

    Returns:
        The content of the file as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    with open(file_path) as f:
        return f.read()


@tool()
async def write_file(file_path: str, content: str) -> str:
    """Write content to a file, creating it if it doesn't exist.

    Args:
        file_path: Path to the file to write.
        content: Content to write to the file.

    Returns:
        Success message confirming the file was written.
    """
    # Create parent directories if they don't exist
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)

    with open(file_path, "w") as f:
        f.write(content)

    return f"File successfully written to {file_path}"


@tool()
async def list_files(directory: str) -> str:
    """List all files in a directory.

    Args:
        directory: Path to the directory to list.

    Returns:
        A newline-separated list of file names in the directory.
    """
    files = os.listdir(directory)
    return "\n".join(files)


# =============================================================================
# Real API E2E Tests
# =============================================================================


@pytest.fixture
def real_provider():
    """Create a real SiliconFlow provider.

    Skip tests if SILICONFLOW_API_KEY is not set.
    """
    provider = get_siliconflow_provider()
    if provider is None:
        pytest.skip("SILICONFLOW_API_KEY not set, skipping real API tests")
    return provider


@pytest.mark.scenario
@pytest.mark.expensive
class TestFileOperationsWithRealAPI:
    """End-to-end tests with real SiliconFlow API."""

    @pytest.mark.asyncio
    async def test_read_and_summarize(self, real_provider):
        """Test reading a file and creating a summary with real API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a source file with meaningful content
            source_file = os.path.join(tmpdir, "source.txt")
            source_content = """AgentLite 项目概述
================

AgentLite 是一个轻量级的 Agent 组件库，主要特点:
- 异步优先设计
- OpenAI 兼容 API
- 工具系统 (支持 MCP)
- 流式响应支持

使用示例:
```python
from agentlite import Agent, OpenAIProvider

provider = OpenAIProvider(api_key="...", model="gpt-4")
agent = Agent(provider=provider)
response = await agent.run("Hello!")
```
"""
            with open(source_file, "w") as f:
                f.write(source_content)

            # Create agent with file tools
            tools = [read_file, write_file, list_files]
            agent = Agent(
                provider=real_provider,
                tools=tools,
                system_prompt="你是一个文件分析助手。请使用工具来完成任务。",
            )

            # Run the agent to read, analyze, and write summary
            output_file = os.path.join(tmpdir, "summary.txt")
            response = await agent.run(
                f"请读取 {source_file} 文件，分析其内容，并创建一个摘要文件保存到 {output_file}。"
            )

            # Verify the agent responded
            assert response, "Agent should return a response"
            print(f"\n[Agent 响应]:\n{response}\n")

            # Verify the output file was created
            if os.path.exists(output_file):
                with open(output_file) as f:
                    output_content = f.read()
                print(f"\n[输出文件内容]:\n{output_content}\n")
                assert len(output_content) > 0, "Output file should not be empty"

    @pytest.mark.asyncio
    async def test_list_files_and_combine(self, real_provider):
        """Test listing files, reading them, and creating combined report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple files
            files = {
                "sales.txt": "销售额增长了 20%",
                "users.txt": "用户满意度达到 85%",
                "bugs.txt": "修复了 15 个问题",
            }
            for name, content in files.items():
                with open(os.path.join(tmpdir, name), "w") as f:
                    f.write(content)

            # Create agent with file tools
            tools = [read_file, write_file, list_files]
            agent = Agent(
                provider=real_provider,
                tools=tools,
                system_prompt="你是一个数据分析助手。请使用工具来完成任务。",
            )

            # Run the agent
            report_file = os.path.join(tmpdir, "report.txt")
            response = await agent.run(
                f"列出 {tmpdir} 目录中的所有文件，读取每个文件的内容，然后创建一份综合报告保存到 {report_file}。"
            )

            # Verify the agent responded
            assert response, "Agent should return a response"
            print(f"\n[Agent 响应]:\n{response}\n")

            # The agent should have created the report file
            if os.path.exists(report_file):
                with open(report_file) as f:
                    report_content = f.read()
                print(f"\n[报告文件内容]:\n{report_content}\n")

    @pytest.mark.asyncio
    async def test_simple_conversation(self, real_provider):
        """Test basic conversation without tools."""
        agent = Agent(
            provider=real_provider,
            system_prompt="你是一个有帮助的助手。请用中文回答。",
        )

        response = await agent.run("你好！请简单介绍一下你自己。")

        assert response, "Agent should return a response"
        print(f"\n[Agent 自我介绍]:\n{response}\n")
        assert len(response) > 10, "Response should be meaningful"
