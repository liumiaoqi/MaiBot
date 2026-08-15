"""表情包 ASCII 预渲染缓存（内存 LRU）。

ZG16-4：无 vision 模型时用 ASCII 灰度文本替代图片，表情包预渲染缓存避免重复转换。
纯内存 OrderedDict 不落磁盘，key 用 emoji_hash（file_hash）禁止用文件路径。
"""

from collections import OrderedDict
from typing import Optional

import asyncio

from src.common.data_models.image_data_model import MaiEmoji
from src.common.logger import get_logger
from src.common.utils.utils_image import ImageUtils

logger = get_logger("ascii_image_cache")


class AsciiImageCache:
    """表情包 ASCII 预渲染缓存（内存 LRU）。"""

    def __init__(
        self,
        max_size: int = 256,
        column_width: int = 48,
        charset: str = "@%#*+=-:.",
        main_color_count: int = 2,
    ) -> None:
        """初始化 LRU 缓存 + 渲染配置。"""
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._max_size = max_size
        self._column_width = column_width
        self._charset = charset
        self._main_color_count = main_color_count
        self._hit_count = 0
        self._miss_count = 0

    def get(self, emoji_hash: str) -> Optional[str]:
        """查询缓存。命中则 move_to_end + 返回，未命中返回 None。"""
        if emoji_hash in self._cache:
            self._cache.move_to_end(emoji_hash)
            self._hit_count += 1
            return self._cache[emoji_hash]
        self._miss_count += 1
        return None

    def put(self, emoji_hash: str, ascii_text: str) -> None:
        """写入缓存。超限时 popitem(last=False) 淘汰最久未访问。"""
        self._cache[emoji_hash] = ascii_text
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def remove(self, emoji_hash: str) -> None:
        """表情包删除时从缓存移除。"""
        self._cache.pop(emoji_hash, None)

    async def pre_render_all(self, emojis: list[MaiEmoji]) -> None:
        """全量预渲染：遍历表情包 → 读 bytes → to_ascii → put。单个失败跳过+告警。"""
        for emoji in emojis:
            emoji_hash = emoji.file_hash
            if not emoji_hash:
                continue
            try:
                emoji_bytes = await asyncio.to_thread(emoji.full_path.read_bytes)
                ascii_text = ImageUtils.to_ascii(
                    emoji_bytes,
                    column_width=self._column_width,
                    charset=self._charset,
                    main_color_count=self._main_color_count,
                )
                if ascii_text is not None:
                    self.put(emoji_hash, ascii_text)
                else:
                    self._report_warning(f"表情 {emoji_hash} 预渲染失败（to_ascii 返回 None），跳过")
            except Exception as exc:
                self._report_warning(f"表情 {emoji_hash} 预渲染失败: {exc}，跳过")

    async def get_or_render(self, emoji_hash: str, image_bytes: bytes) -> Optional[str]:
        """查询或实时渲染：get 命中则返回，未命中则实时渲染 + put + 返回。"""
        cached = self.get(emoji_hash)
        if cached is not None:
            return cached
        ascii_text = ImageUtils.to_ascii(
            image_bytes,
            column_width=self._column_width,
            charset=self._charset,
            main_color_count=self._main_color_count,
        )
        if ascii_text is not None:
            self.put(emoji_hash, ascii_text)
        return ascii_text

    def stats(self) -> dict[str, int]:
        """返回缓存统计（命中数/未命中数/当前大小），供日志。"""
        return {
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "size": len(self._cache),
            "max_size": self._max_size,
        }

    async def on_emoji_added(self, emoji: MaiEmoji) -> None:
        """表情包新增时增量渲染入缓存。"""
        emoji_hash = emoji.file_hash
        if not emoji_hash:
            return
        try:
            emoji_bytes = await asyncio.to_thread(emoji.full_path.read_bytes)
            ascii_text = ImageUtils.to_ascii(
                emoji_bytes,
                column_width=self._column_width,
                charset=self._charset,
                main_color_count=self._main_color_count,
            )
            if ascii_text is not None:
                self.put(emoji_hash, ascii_text)
            else:
                self._report_warning(f"表情 {emoji_hash} 增量预渲染失败（to_ascii 返回 None），跳过")
        except Exception as exc:
            self._report_warning(f"表情 {emoji_hash} 增量预渲染失败: {exc}，跳过")

    def on_emoji_removed(self, emoji_hash: str) -> None:
        """表情包删除时从缓存移除。"""
        self.remove(emoji_hash)

    @staticmethod
    def _report_warning(message: str) -> None:
        """上报 WARNING 级别错误到 error_escalation 端口 + 记日志。"""
        from src.core.error_escalation.types import ErrorLevel
        from src.core.error_escalation_port_registry import get_error_escalation_port

        port = get_error_escalation_port()
        if port is not None:
            port.report(ErrorLevel.WARN, message)
        logger.warning(message)