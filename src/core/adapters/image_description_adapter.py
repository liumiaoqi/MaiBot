"""ImageDescriptionAdapter — 将 image_manager 包装为 ImageDescriptionPort 接口。"""

from typing import Any


class ImageDescriptionAdapter:
    def __init__(self, image_manager: Any) -> None:
        self._image_manager = image_manager

    async def get_image_description(
        self,
        image_hash: str,
        image_bytes: bytes,
        wait_for_build: bool = True,
    ) -> str:
        return await self._image_manager.get_image_description(
            image_hash=image_hash,
            image_bytes=image_bytes,
            wait_for_build=wait_for_build,
        )
