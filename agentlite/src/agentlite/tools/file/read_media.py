"""ReadMediaFile tool for AgentLite.

This module provides a tool for reading image and video files.
"""

from __future__ import annotations
from typing import Optional

import base64
from pathlib import Path

from pydantic import BaseModel, Field

from agentlite.tool import CallableTool2, ToolError, ToolOk, ToolResult


class Params(BaseModel):
    """Parameters for the ReadMediaFile tool."""

    path: str = Field(
        description=(
            "The path to the media file to read. "
            "Absolute paths are required when reading files outside the working directory."
        )
    )


class ReadMediaFile(CallableTool2[Params]):
    """Tool for reading image and video files.

    This tool reads media files and returns them as base64-encoded data URLs.
    Supports images (PNG, JPEG, GIF, etc.) and videos.

    Example:
        >>> tool = ReadMediaFile(work_dir=Path("/tmp"))
        >>> result = await tool({"path": "image.png"})
    """

    name: str = "ReadMediaFile"
    description: str = (
        "Read an image or video file and return it as a base64-encoded data URL. "
        "Supported formats: PNG, JPEG, GIF, WebP, MP4, WebM, and others. "
        "Maximum file size: 100MB."
    )
    params: type[Params] = Params

    # Supported media types
    IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
    VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv"}

    # MIME type mapping
    MIME_TYPES = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
        ".svg": "image/svg+xml",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
    }

    def __init__(
        self,
        work_dir: Path,
        max_size_mb: int = 100,
    ):
        """Initialize the ReadMediaFile tool.

        Args:
            work_dir: The working directory for relative paths
            max_size_mb: Maximum file size in MB
        """
        super().__init__()
        self._work_dir = work_dir
        self._max_size = max_size_mb * 1024 * 1024

    def _is_within_work_dir(self, path: Path) -> bool:
        """Check if a path is within the working directory."""
        try:
            path.relative_to(self._work_dir.resolve())
            return True
        except ValueError:
            return False

    def _get_mime_type(self, path: Path) -> Optional[str]:
        """Get MIME type for a file based on extension."""
        ext = path.suffix.lower()
        return self.MIME_TYPES.get(ext)

    def _is_media_file(self, path: Path) -> bool:
        """Check if a file is a supported media file."""
        ext = path.suffix.lower()
        return ext in self.IMAGE_EXTENSIONS or ext in self.VIDEO_EXTENSIONS
    async def __call__(self, params: Params) -> ToolResult:
        """Execute the read media operation.

        Args:
            params: The read parameters

        Returns:
            ToolResult with base64 data URL or error
        """
        if not params.path:
            return ToolError(
                message="File path cannot be empty.",
            )

        try:
            # Resolve path
            path = Path(params.path).expanduser()
            if not path.is_absolute():
                path = self._work_dir / path
            path = path.resolve()

            # Security check
            if not self._is_within_work_dir(path) and not Path(params.path).is_absolute():
                return ToolError(
                    message=(
                        f"`{params.path}` is not an absolute path. "
                        "You must provide an absolute path to read a file "
                        "outside the working directory."
                    ),
                )

            # Check file exists
            if not path.exists():
                return ToolError(
                    message=f"`{params.path}` does not exist.",
                )

            if not path.is_file():
                return ToolError(
                    message=f"`{params.path}` is not a file.",
                )

            # Check it's a media file
            if not self._is_media_file(path):
                return ToolError(
                    message=(
                        f"`{params.path}` is not a supported media file. "
                        f"Supported extensions: "
                        f"{', '.join(sorted(self.IMAGE_EXTENSIONS | self.VIDEO_EXTENSIONS))}"
                    ),
                )

            # Check file size
            file_size = path.stat().st_size
            if file_size > self._max_size:
                return ToolError(
                    message=(
                        f"`{params.path}` is too large ({file_size / 1024 / 1024:.1f}MB). "
                        f"Maximum size is {self._max_size / 1024 / 1024:.0f}MB."
                    ),
                )

            # Get MIME type
            mime_type = self._get_mime_type(path)
            if not mime_type:
                return ToolError(
                    message=f"Could not determine MIME type for `{params.path}`.",
                )

            # Read and encode file
            data = path.read_bytes()
            encoded = base64.b64encode(data).decode("ascii")
            data_url = f"data:{mime_type};base64,{encoded}"

            return ToolOk(
                output=data_url,
                message=(
                    f"Loaded {mime_type.split('/')[0]} file `{params.path}` ({file_size} bytes)."
                ),
            )

        except Exception as e:
            return ToolError(
                message=f"Failed to read {params.path}. Error: {e}",
            )
