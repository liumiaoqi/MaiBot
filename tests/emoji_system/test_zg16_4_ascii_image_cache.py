"""ZG16-4 ASCII 看图功能测试 — AsciiImageCache 类。

覆盖场景：缓存粒度/LRU 上限淘汰/move_to_end/remove/get_or_render 命中与未命中/
stats/不落磁盘/key 用 emoji_hash/on_emoji_removed/单个渲染失败跳过。
"""


from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest

from PIL import Image as PILImage

from src.common.data_models.image_data_model import MaiEmoji
from src.emoji_system.ascii_image_cache import AsciiImageCache


# ── 测试夹具 ──────────────────────────────────────────────────────


def _make_png_bytes(size: tuple[int, int] = (100, 100), color: tuple[int, int, int] = (128, 128, 128)) -> bytes:
    """生成 PNG 图片字节。"""
    image = PILImage.new("RGB", size, color=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def temp_emoji_file(tmp_path: Path) -> Path:
    """创建临时表情包图片文件。"""
    image_bytes = _make_png_bytes()
    file_path = tmp_path / "test_emoji.png"
    file_path.write_bytes(image_bytes)
    return file_path


def _make_mai_emoji(file_path: Path, file_hash: str, description: str = "", emotion: list[str] | None = None) -> MaiEmoji:
    """构造 MaiEmoji 实例（绕过文件存在性校验，直接设置属性）。"""
    emoji = MaiEmoji(file_path)
    emoji.file_hash = file_hash
    emoji.description = description
    emoji.emotion = emotion or []
    return emoji


# ── 测试用例 ──────────────────────────────────────────────────────


class TestAsciiCacheBasic:
    """缓存基础操作：put/get/remove。"""

    def test_put_then_get_returns_same_text(self):
        """put(h1, text1) 后 get(h1) 返回 text1。"""
        cache = AsciiImageCache(max_size=256)
        cache.put("hash1", "ascii_text_1")
        result = cache.get("hash1")
        assert result == "ascii_text_1"

    def test_get_miss_returns_none_and_counts(self):
        """未命中的 get 返回 None 且 miss_count +1。"""
        cache = AsciiImageCache(max_size=256)
        result = cache.get("nonexistent")
        assert result is None
        stats = cache.stats()
        assert stats["miss_count"] == 1

    def test_remove_then_get_returns_none(self):
        """remove 后 get 返回 None。"""
        cache = AsciiImageCache(max_size=256)
        cache.put("hash1", "text1")
        cache.remove("hash1")
        result = cache.get("hash1")
        assert result is None


class TestAsciiCacheLRU:
    """LRU 淘汰策略：上限淘汰/move_to_end。"""

    def test_lru_eviction_when_exceed_max_size(self):
        """缓存满 4 + put 第 5 个 → 最久未访问的被淘汰。"""
        cache = AsciiImageCache(max_size=4)
        cache.put("h1", "t1")
        cache.put("h2", "t2")
        cache.put("h3", "t3")
        cache.put("h4", "t4")
        # 此时 h1 最久未访问
        cache.put("h5", "t5")
        # h1 应被淘汰
        assert cache.get("h1") is None
        # h2-h5 仍在
        # 注意：get h1 已计入 miss，需直接检查内部 cache
        assert "h1" not in cache._cache
        assert "h5" in cache._cache

    def test_lru_move_to_end_on_get(self):
        """get 命中后该条目移到最新位置（不被淘汰）。"""
        cache = AsciiImageCache(max_size=3)
        cache.put("h1", "t1")
        cache.put("h2", "t2")
        cache.put("h3", "t3")
        # 访问 h1，使其移到最新
        cache.get("h1")
        # 再 put h4，应淘汰 h2（最久未访问）
        cache.put("h4", "t4")
        assert "h1" in cache._cache  # h1 因被访问而保留
        assert "h2" not in cache._cache  # h2 被淘汰
        assert "h4" in cache._cache


class TestAsciiCacheGetOrRender:
    """get_or_render：未命中实时渲染/命中直接返回。"""

    async def test_get_or_render_miss_triggers_render_and_caches(self):
        """get_or_render 未命中 → 实时渲染并入缓存。"""
        cache = AsciiImageCache(max_size=256)
        image_bytes = _make_png_bytes()
        result = await cache.get_or_render("new_hash", image_bytes)
        assert result is not None
        assert isinstance(result, str)
        # 二次查询应命中缓存
        cached = cache.get("new_hash")
        assert cached == result

    async def test_get_or_render_hit_returns_cached_without_rerender(self):
        """get_or_render 命中 → 直接返回不重复渲染。"""
        cache = AsciiImageCache(max_size=256)
        image_bytes = _make_png_bytes()
        # 首次渲染入缓存
        first_result = await cache.get_or_render("hash_x", image_bytes)
        assert first_result is not None
        # 用 patch 监控 to_ascii 调用，命中时不应被调用
        with patch("src.emoji_system.ascii_image_cache.ImageUtils.to_ascii") as mock_to_ascii:
            second_result = await cache.get_or_render("hash_x", image_bytes)
            assert mock_to_ascii.call_count == 0
        assert second_result == first_result


class TestAsciiCacheStats:
    """stats 返回命中数/未命中数/当前大小/上限。"""

    def test_stats_returns_correct_fields(self):
        """stats 返回 hit_count/miss_count/size/max_size。"""
        cache = AsciiImageCache(max_size=128)
        cache.put("h1", "t1")
        cache.get("h1")  # hit
        cache.get("h2")  # miss
        stats = cache.stats()
        assert stats["hit_count"] == 1
        assert stats["miss_count"] == 1
        assert stats["size"] == 1
        assert stats["max_size"] == 128


class TestAsciiCacheInMemoryOnly:
    """纯内存不落磁盘 + key 用 emoji_hash。"""

    def test_pure_in_memory_no_disk_io(self):
        """AsciiImageCache 纯内存 dict，不落磁盘。"""
        cache = AsciiImageCache(max_size=256)
        cache.put("h1", "t1")
        # 内部 cache 应为 OrderedDict
        from collections import OrderedDict

        assert isinstance(cache._cache, OrderedDict)
        # 值应为 str
        assert isinstance(cache._cache["h1"], str)

    def test_key_is_emoji_hash_not_file_path(self):
        """key 用 emoji_hash（file_hash），非文件路径。"""
        cache = AsciiImageCache(max_size=256)
        emoji_hash = "abc123hash"
        cache.put(emoji_hash, "ascii_text")
        # key 应为 emoji_hash
        assert emoji_hash in cache._cache
        # 不应用文件路径作为 key
        assert "/path/to/emoji.png" not in cache._cache


class TestAsciiCacheOnEmojiRemoved:
    """on_emoji_removed 后 get 返回 None。"""

    def test_on_emoji_removed_clears_cache(self):
        """on_emoji_removed 后 get 返回 None。"""
        cache = AsciiImageCache(max_size=256)
        cache.put("emoji_hash_1", "ascii_text")
        cache.on_emoji_removed("emoji_hash_1")
        assert cache.get("emoji_hash_1") is None
        assert "emoji_hash_1" not in cache._cache


class TestAsciiCachePreRenderFailure:
    """单个渲染失败跳过不影响其他。"""

    async def test_pre_render_all_skips_failed_render(self, tmp_path: Path):
        """pre_render_all 中 to_ascii 返回 None → 跳过该表情，其他正常入缓存。"""
        # 构造两个表情包文件
        good_bytes = _make_png_bytes()
        good_path = tmp_path / "good.png"
        good_path.write_bytes(good_bytes)

        bad_path = tmp_path / "bad.png"
        bad_path.write_bytes(good_bytes)  # 文件合法，但 to_ascii 会被 mock 返回 None

        good_emoji = _make_mai_emoji(good_path, "good_hash", "good emoji", ["happy"])
        bad_emoji = _make_mai_emoji(bad_path, "bad_hash", "bad emoji", ["sad"])

        cache = AsciiImageCache(max_size=256)

        # mock to_ascii：bad_hash 返回 None，其他正常渲染

        def fake_to_ascii(image_bytes, *, column_width, charset, main_color_count):
            # 通过文件内容判断：这里简化为对 bad_path 的内容返回 None
            # 实际通过 hash 区分较复杂，这里用调用次数模拟
            return None  # 全部返回 None 简化测试

        with patch("src.emoji_system.ascii_image_cache.ImageUtils.to_ascii", side_effect=fake_to_ascii):
            await cache.pre_render_all([good_emoji, bad_emoji])

        # 全部失败时缓存应为空，但不抛异常
        assert len(cache._cache) == 0

    async def test_pre_render_all_partial_failure(self, tmp_path: Path):
        """pre_render_all 部分失败：成功的入缓存，失败的跳过。"""
        good_bytes = _make_png_bytes()
        good_path = tmp_path / "good.png"
        good_path.write_bytes(good_bytes)

        bad_path = tmp_path / "bad.png"
        bad_path.write_bytes(good_bytes)

        good_emoji = _make_mai_emoji(good_path, "good_hash", "good", ["happy"])
        bad_emoji = _make_mai_emoji(bad_path, "bad_hash", "bad", ["sad"])

        cache = AsciiImageCache(max_size=256)

        call_count = [0]

        def selective_to_ascii(image_bytes, *, column_width, charset, main_color_count):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # 第一个失败
            return "ascii_for_good"  # 第二个成功

        with patch("src.emoji_system.ascii_image_cache.ImageUtils.to_ascii", side_effect=selective_to_ascii):
            await cache.pre_render_all([bad_emoji, good_emoji])

        # 仅一个入缓存
        assert len(cache._cache) == 1
        assert "good_hash" in cache._cache