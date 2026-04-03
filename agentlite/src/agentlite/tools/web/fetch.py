"""FetchURL tool for AgentLite.

This module provides a tool for fetching web page content.
"""

from __future__ import annotations

import urllib.request
import urllib.error
from pathlib import Path

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolOk, ToolResult


class Params(BaseModel):
    """Parameters for the FetchURL tool."""

    url: str = Field(description="The URL to fetch content from.")


class FetchURL(CallableTool2[Params]):
    """Tool for fetching web page content.

    This tool fetches the content of a web page and extracts the main text.
    Uses simple HTTP GET with configurable timeout.

    Example:
        >>> tool = FetchURL()
        >>> result = await tool({"url": "https://example.com"})
    """

    name: str = "FetchURL"
    description: str = (
        "Fetch the content of a web page. "
        "Returns the HTML content or extracts main text if possible. "
        "Useful for reading documentation, articles, or API responses."
    )
    params: type[Params] = Params

    def __init__(
        self,
        timeout: int = 30,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        ),
        max_content_length: int = 1024 * 1024,  # 1MB
    ):
        """Initialize the FetchURL tool.

        Args:
            timeout: Request timeout in seconds
            user_agent: User-Agent string
            max_content_length: Maximum content length to fetch
        """
        super().__init__()
        self._timeout = timeout
        self._user_agent = user_agent
        self._max_content_length = max_content_length

    def _extract_text(self, html: str) -> str:
        """Simple HTML to text extraction.

        Args:
            html: HTML content

        Returns:
            Extracted text
        """
        import re

        # Remove script and style elements
        html = re.sub(r"<script[^\u003e]*>.*?</script>", "", html, flags=re.DOTALL)
        html = re.sub(r"<style[^\u003e]*>.*?</style>", "", html, flags=re.DOTALL)

        # Remove HTML tags
        text = re.sub(r"<[^\u003e]+>", "", html)

        # Decode HTML entities
        import html as html_module

        text = html_module.unescape(text)

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)

        return text.strip()
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the URL fetch.

        Args:
            params: The fetch parameters

        Returns:
            ToolResult with page content or error
        """
        if not params.url:
            return ToolError(
                message="URL cannot be empty.",
            )

        try:
            # Create request with headers
            request = urllib.request.Request(
                params.url,
                headers={
                    "User-Agent": self._user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "identity",
                },
            )

            # Fetch URL
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                # Check content length
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > self._max_content_length:
                    return ToolError(
                        message=(
                            f"Content too large ({int(content_length)} bytes). "
                            f"Maximum is {self._max_content_length} bytes."
                        ),
                    )

                # Read content
                content = response.read()

                # Check size limit
                if len(content) > self._max_content_length:
                    return ToolError(
                        message=(
                            f"Content too large ({len(content)} bytes). "
                            f"Maximum is {self._max_content_length} bytes."
                        ),
                    )

                # Decode content
                try:
                    text = content.decode("utf-8")
                except UnicodeDecodeError:
                    try:
                        text = content.decode("latin-1")
                    except UnicodeDecodeError:
                        text = content.decode("utf-8", errors="replace")

                # Extract text if HTML
                content_type = response.headers.get("Content-Type", "")
                if "text/html" in content_type:
                    extracted = self._extract_text(text)
                    return ToolOk(
                        output=extracted,
                        message=f"Fetched and extracted content from {params.url}",
                    )
                else:
                    return ToolOk(
                        output=text,
                        message=f"Fetched content from {params.url}",
                    )

        except urllib.error.HTTPError as e:
            return ToolError(
                message=f"HTTP error {e.code}: {e.reason}",
            )
        except urllib.error.URLError as e:
            return ToolError(
                message=f"URL error: {e.reason}",
            )
        except Exception as e:
            return ToolError(
                message=f"Failed to fetch {params.url}. Error: {e}",
            )
