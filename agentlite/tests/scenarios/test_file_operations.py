"""End-to-end scenario test for file operations.

This test simulates a realistic scenario where an agent:
1. Reads a file
2. Explains its content
3. Creates a new file with analysis results

This is a meaningful e2e test that demonstrates the agent's ability to
orchestrate multiple tool calls in sequence.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from agentlite import Agent, TextPart, tool


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
# E2E Test
# =============================================================================


@pytest.mark.scenario
class TestFileOperationsScenario:
    """End-to-end test for file read/write operations."""

    @pytest.mark.asyncio
    async def test_read_explain_and_write(self, mock_provider):
        """Test a complete workflow: read file -> explain -> write results."""
        # Setup: Create a temporary file with content
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a source file to read
            source_file = os.path.join(tmpdir, "source.txt")
            source_content = """Project Overview
================

This is a sample project document for testing.

Features:
- Feature A: Does something useful
- Feature B: Does something else
- Feature C: The most important feature

Conclusion: This project demonstrates file operations.
"""
            with open(source_file, "w") as f:
                f.write(source_content)

            # Configure mock provider responses
            # The agent should:
            # 1. Read the file
            # 2. Summarize it
            # 3. Write the summary to a new file
            mock_provider.add_text_response(
                f"I'll read the file at {source_file} and analyze it for you."
            )

            # Create agent with file tools
            tools = [read_file, write_file, list_files]
            agent = Agent(
                provider=mock_provider,
                tools=tools,
                system_prompt="You are a helpful file analysis assistant.",
            )

            # Step 1: Agent reads and analyzes the file
            mock_provider.clear_responses()
            mock_provider.add_tool_call(
                "read_file",
                {"file_path": source_file},
                source_content,
            )

            # Agent analyzes the content
            mock_provider.add_text_response(
                "I've read the file. It's a project overview document with 3 features. "
                "Let me create a summary file."
            )

            # Step 2: Agent writes summary to a new file
            summary_file = os.path.join(tmpdir, "summary.txt")
            expected_summary = """Project Summary
================

This is a sample project with 3 main features:
- Feature A, - Feature B, - Feature C

The most important feature is Feature C.
"""

            mock_provider.clear_responses()
            mock_provider.add_tool_call(
                "write_file",
                {
                    "file_path": summary_file,
                    "content": expected_summary,
                },
                f"File successfully written to {summary_file}",
            )
            mock_provider.add_text_response(f"I've created a summary at {summary_file}")

            # Execute the agent
            response = await agent.run(
                f"Please read {source_file}, analyze it, and create a summary file at {summary_file}"
            )

            # Verify the interaction
            assert "summary" in response.lower()

            # Verify the provider was called correctly
            assert len(mock_provider.calls) >= 1

    @pytest.mark.asyncio
    async def test_list_files_scenario(self, mock_provider):
        """Test listing files in a directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            for i in range(3):
                with open(os.path.join(tmpdir, f"file{i}.txt"), "w") as f:
                    f.write(f"Content {i}")

            # Configure agent to list files
            mock_provider.add_tool_call(
                "list_files",
                {"directory": tmpdir},
                "file0.txt\nfile1.txt\nfile2.txt",
            )
            mock_provider.add_text_response(
                f"I found 3 files in {tmpdir}: file0.txt, file1.txt, file2.txt"
            )

            agent = Agent(
                provider=mock_provider,
                tools=[list_files],
                system_prompt="You are a file system assistant.",
            )

            response = await agent.run(f"List all files in {tmpdir}")

            assert "3 files" in response

    @pytest.mark.asyncio
    async def test_multi_step_file_workflow(self, mock_provider):
        """Test a complex multi-step file workflow.

        Scenario:
        1. List files in directory
        2. Read each file
        3. Create a combined report
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            files_content = {
                "report1.txt": "Sales increased by 20%",
                "report2.txt": "Customer satisfaction at 85%",
                "report3.txt": "Bug fixes: 15 resolved",
            }

            for name, content in files_content.items():
                with open(os.path.join(tmpdir, name), "w") as f:
                    f.write(content)

            # Configure agent responses for multi-step workflow
            tools = [read_file, write_file, list_files]

            # Step 1: List files
            mock_provider.add_tool_call(
                "list_files",
                {"directory": tmpdir},
                "report1.txt\nreport2.txt\nreport3.txt",
            )

            # Step 2: Read all files
            mock_provider.add_tool_call(
                "read_file",
                {"file_path": os.path.join(tmpdir, "report1.txt")},
                "Sales increased by 20%",
            )
            mock_provider.add_tool_call(
                "read_file",
                {"file_path": os.path.join(tmpdir, "report2.txt")},
                "Customer satisfaction at 85%",
            )
            mock_provider.add_tool_call(
                "read_file",
                {"file_path": os.path.join(tmpdir, "report3.txt")},
                "Bug fixes: 15 resolved",
            )

            # Step 3: Write combined report
            combined_report = """Combined Report
================

1. Sales: Increased by 20%
2. Customer Satisfaction: 85%
3. Development: 15 bugs resolved
"""
            mock_provider.add_tool_call(
                "write_file",
                {
                    "file_path": os.path.join(tmpdir, "combined_report.txt"),
                    "content": combined_report,
                },
                f"File successfully written to {os.path.join(tmpdir, 'combined_report.txt')}",
            )

            mock_provider.add_text_response(
                "I've created a combined report summarizing all three reports."
            )

            agent = Agent(
                provider=mock_provider,
                tools=tools,
                system_prompt="You are a report analyst assistant.",
            )

            response = await agent.run(
                f"List all files in {tmpdir}, read them all, and create a combined report at combined_report.txt"
            )

            assert "combined report" in response.lower()


# =============================================================================
# Additional Tools for Extended Scenarios
# =============================================================================


@tool()
async def count_words(file_path: str) -> str:
    """Count the number of words in a file.

    Args:
        file_path: Path to the file to analyze.

    Returns:
        The word count as a string.
    """
    with open(file_path) as f:
        content = f.read()
        word_count = len(content.split())
        return f"Word count: {word_count}"


@tool()
async def append_to_file(file_path: str, content: str) -> str:
    """Append content to an existing file.

    Args:
        file_path: Path to the file to append to.
        content: Content to append.

    Returns:
        Success message.
    """
    with open(file_path, "a") as f:
        f.write("\n" + content)
    return f"Content appended to {file_path}"


@pytest.mark.scenario
class TestExtendedFileOperations:
    """Extended scenarios with more file operations."""

    @pytest.mark.asyncio
    async def test_read_count_and_append(self, mock_provider):
        """Test reading a file, counting words, and appending a note."""
        with tempfile.TemporaryDirectory() as tmpdir:
            source_file = os.path.join(tmpdir, "document.txt")
            with open(source_file, "w") as f:
                f.write("This is a test document with several words in it.")

            tools = [read_file, write_file, count_words, append_to_file]

            # Step 1: Read file
            mock_provider.add_tool_call(
                "read_file",
                {"file_path": source_file},
                "This is a test document with several words in it.",
            )

            # Step 2: Count words
            mock_provider.add_tool_call(
                "count_words",
                {"file_path": source_file},
                "Word count: 10",
            )

            # Step 3: Append analysis
            mock_provider.add_tool_call(
                "append_to_file",
                {
                    "file_path": source_file,
                    "content": "\n\n[Analysis] This document contains 10 words.",
                },
                f"Content appended to {source_file}",
            )

            mock_provider.add_text_response(
                "I've analyzed the document and appended the word count analysis."
            )

            agent = Agent(
                provider=mock_provider,
                tools=tools,
                system_prompt="You are a document analysis assistant.",
            )

            response = await agent.run(
                f"Read {source_file}, count its words, and append the word count as an analysis note"
            )

            assert "analyzed" in response.lower()
