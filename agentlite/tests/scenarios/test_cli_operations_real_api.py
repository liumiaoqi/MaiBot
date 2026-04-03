"""End-to-end test for complex CLI operations with real API.

This test simulates a realistic complex CLI task where an agent:
1. Explores project structure using shell commands
2. Searches for specific patterns using grep/glob
3. Reads relevant files
4. Creates analysis reports

Uses real SiliconFlow qwen3.5-397B API (requires SILICONFLOW_API_KEY env var).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from agentlite import Agent, OpenAIProvider
from agentlite.tools import (
    ConfigurableToolset,
    ToolSuiteConfig,
    Shell,
    ReadFile,
    WriteFile,
    Glob,
    Grep,
)

# =============================================================================
# Configuration from model_config.toml
# =============================================================================

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_MODEL = "Qwen/Qwen3.5-397B-A17B"


def get_siliconflow_provider() -> OpenAIProvider | None:
    """Create OpenAIProvider for SiliconFlow API."""
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        return None
    return OpenAIProvider(
        api_key=api_key,
        base_url=SILICONFLOW_BASE_URL,
        model=SILICONFLOW_MODEL,
    )


@pytest.fixture
def real_provider():
    """Create real SiliconFlow provider."""
    provider = get_siliconflow_provider()
    if provider is None:
        pytest.skip("SILICONFLOW_API_KEY not set")
    return provider


@pytest.fixture
def test_project():
    """Create a mock project structure for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "test_project"
        project_dir.mkdir()

        # Create project structure
        (project_dir / "src").mkdir()
        (project_dir / "src" / "utils").mkdir()
        (project_dir / "tests").mkdir()
        (project_dir / "docs").mkdir()

        # Create source files
        (project_dir / "src" / "main.py").write_text('''"""Main module."""
from src.utils.helper import process_data
from src.utils.logger import setup_logger

def main():
    """Main entry point."""
    logger = setup_logger()
    data = [1, 2, 3, 4, 5]
    result = process_data(data)
    logger.info(f"Result: {result}")
    return result

if __name__ == "__main__":
    main()
''')

        (project_dir / "src" / "__init__.py").write_text('"""Source package."""')

        (project_dir / "src" / "utils" / "helper.py").write_text('''"""Helper utilities."""
def process_data(data: list) -> list:
    """Process input data."""
    return [x * 2 for x in data]

def validate_data(data: list) -> bool:
    """Validate data format."""
    return all(isinstance(x, (int, float)) for x in data)
''')

        (project_dir / "src" / "utils" / "logger.py").write_text('''"""Logging utilities."""
import logging

def setup_logger(name: str = "app") -> logging.Logger:
    """Setup application logger."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    return logger
''')

        (project_dir / "src" / "utils" / "__init__.py").write_text('"""Utils package."""')

        # Create test files
        (project_dir / "tests" / "test_helper.py").write_text('''"""Tests for helper module."""
from src.utils.helper import process_data, validate_data

def test_process_data():
    assert process_data([1, 2, 3]) == [2, 4, 6]

def test_validate_data():
    assert validate_data([1, 2, 3]) == True
    assert validate_data(["a", "b"]) == False
''')

        # Create documentation
        (project_dir / "docs" / "README.md").write_text("""# Test Project

A sample project for testing CLI operations.

## Structure

- `src/` - Source code
- `tests/` - Unit tests
- `docs/` - Documentation
""")

        (project_dir / "README.md").write_text("""# Test Project

Simple data processing project.

## Usage

```bash
python -m src.main
```
""")

        yield project_dir


@pytest.mark.scenario
@pytest.mark.slow
class TestComplexCLITasks:
    """End-to-end tests with complex CLI operations."""

    @pytest.mark.asyncio
    async def test_explore_project_structure(self, real_provider, test_project):
        """Test exploring project structure using CLI tools.

        Task: Use shell commands to explore the project structure,
        then summarize what files exist.
        """
        # Create toolset with Shell tool
        toolset = ConfigurableToolset(
            config=ToolSuiteConfig(
                shell_tools=ToolSuiteConfig().shell_tools,
            ),
            work_dir=str(test_project),
        )

        agent = Agent(
            provider=real_provider,
            tools=toolset.tools,
            system_prompt=(
                "你是一个项目分析助手。使用 Shell 工具执行命令来探索项目结构。"
                "请使用 find、ls、tree 等命令来了解项目。"
            ),
            max_iterations=5,  # Limit iterations to prevent hanging
        )

        # Add overall timeout to prevent infinite hanging
        try:
            response = await asyncio.wait_for(
                agent.run(
                    f"探索项目目录 {test_project} 的结构，列出所有文件和目录，并总结项目的组织方式。"
                ),
                timeout=120.0,  # 2 minute overall timeout
            )
        except asyncio.TimeoutError:
            pytest.fail("Agent timed out after 120 seconds - possible infinite loop")

        assert response, "Agent should return a response"
        print(f"\n[项目结构探索结果]:\n{response}\n")

        # Verify response mentions key files
        response_lower = response.lower()
        assert any(
            word in response_lower for word in ["src", "tests", "main.py", "helper", "logger"]
        ), "Response should mention project files"

    @pytest.mark.asyncio
    async def test_search_and_analyze_code(self, real_provider, test_project):
        """Test searching for patterns and analyzing code.

        Task: Use grep/glob to find specific patterns,
        read the files, and create an analysis report.
        """
        # Create toolset with all file tools
        toolset = ConfigurableToolset(
            config=ToolSuiteConfig(
                file_tools=ToolSuiteConfig().file_tools,
                shell_tools=ToolSuiteConfig().shell_tools,
            ),
            work_dir=str(test_project),
        )

        agent = Agent(
            provider=real_provider,
            tools=toolset.tools,
            system_prompt=(
                "你是一个代码分析助手。使用 Glob、Grep、ReadFile 等工具来搜索和分析代码。"
                "请使用 Shell 工具执行 grep、find 等命令。"
            ),
        )

        response = await agent.run(
            f"在项目 {test_project} 中搜索所有包含 'def ' 的 Python 文件，"
            f"列出找到的函数定义，并创建一个函数清单文件保存到 {test_project}/functions.txt。"
        )

        assert response, "Agent should return a response"
        print(f"\n[代码搜索分析结果]:\n{response}\n")

        # Check if analysis file was created
        functions_file = test_project / "functions.txt"
        if functions_file.exists():
            content = functions_file.read_text()
            print(f"\n[函数清单文件]:\n{content}\n")
            assert len(content) > 0, "Functions file should not be empty"

    @pytest.mark.asyncio
    async def test_complex_multi_step_task(self, real_provider, test_project):
        """Test a complex multi-step CLI task.

        Task:
        1. Find all Python files using shell
        2. Search for TODO comments using grep
        3. Read files with TODOs
        4. Create a summary report
        """
        # Add some TODO comments
        todo_file = test_project / "src" / "utils" / "todo_items.py"
        todo_file.write_text('''"""Module with TODO items."""

# TODO: Implement error handling
def risky_operation(data):
    """Perform a risky operation."""
    return data / 0  # This will fail

# TODO: Add caching mechanism
def expensive_computation(n):
    """Perform expensive computation."""
    return sum(range(n))

# FIXME: Memory leak in this function
def process_large_file(path):
    """Process a large file."""
    with open(path) as f:
        return f.read()
''')

        # Create comprehensive toolset
        toolset = ConfigurableToolset(
            config=ToolSuiteConfig(
                file_tools=ToolSuiteConfig().file_tools,
                shell_tools=ToolSuiteConfig().shell_tools,
            ),
            work_dir=str(test_project),
        )

        agent = Agent(
            provider=real_provider,
            tools=toolset.tools,
            system_prompt=(
                "你是一个项目维护助手。"
                "使用 Shell 工具执行命令（如 find、grep、ls 等）。"
                "使用 ReadFile 读取文件内容。"
                "使用 WriteFile 创建新文件。"
                "请一步一步完成任务。"
            ),
        )

        response = await agent.run(
            f"请完成以下任务：\n"
            f"1. 使用 'find' 命令找出项目 {test_project} 中所有的 .py 文件\n"
            f"2. 使用 'grep' 命令搜索所有包含 'TODO' 或 'FIXME' 的行\n"
            f"3. 读取包含 TODO 的文件内容\n"
            f"4. 创建一个 TODO 报告文件，保存到 {test_project}/todo_report.txt"
        )

        assert response, "Agent should return a response"
        print(f"\n[复杂任务结果]:\n{response}\n")

        # Verify report was created
        report_file = test_project / "todo_report.txt"
        if report_file.exists():
            content = report_file.read_text()
            print(f"\n[TODO 报告]:\n{content}\n")

    @pytest.mark.asyncio
    async def test_shell_pipes_and_chains(self, real_provider, test_project):
        """Test complex shell commands with pipes and chains.

        Task: Use shell pipes to perform complex data processing.
        """
        toolset = ConfigurableToolset(
            config=ToolSuiteConfig(
                shell_tools=ToolSuiteConfig().shell_tools,
            ),
            work_dir=str(test_project),
        )

        agent = Agent(
            provider=real_provider,
            tools=toolset.tools,
            system_prompt=(
                "你是一个 Shell 命令专家。"
                "使用复杂的 Shell 命令（管道、重定向、条件执行等）来完成任务。"
            ),
        )

        response = await agent.run(
            f"在项目目录 {test_project} 中执行以下操作：\n"
            f"1. 使用 'find . -name \"*.py\" | xargs wc -l' 统计所有 Python 文件的总行数\n"
            f'2. 使用 \'grep -r "def " --include="*.py" | wc -l\' 统计函数定义数量\n'
            f"3. 使用 'ls -la' 查看目录详情\n"
            f"报告你的发现。"
        )

        assert response, "Agent should return a response"
        print(f"\n[Shell 管道命令结果]:\n{response}\n")

        # Verify response contains relevant information
        response_lower = response.lower()
        assert any(
            word in response_lower for word in ["行", "line", "函数", "function", "文件", "file"]
        ), "Response should mention analysis results"
