from math import ceil
from pathlib import Path
from typing import Optional, Union

import base64
import io

from PIL import Image as PILImage, ImageOps as PILImageOps, ImageSequence
import numpy as np

from src.common.logger import get_logger

logger = get_logger("image_utils")

MODEL_MIN_IMAGE_SIDE = 64
MODEL_MAX_UPSCALED_IMAGE_SIDE = 2048


class ImageUtils:
    @staticmethod
    def normalize_image_base64_for_model(
        image_base64: str,
        image_format: str,
        *,
        min_side: int = MODEL_MIN_IMAGE_SIDE,
        max_upscaled_side: int = MODEL_MAX_UPSCALED_IMAGE_SIDE,
    ) -> tuple[str, str, bool]:
        """确保发给视觉模型的图片不低于常见最小识别尺寸。"""
        if min_side <= 0:
            raise ValueError("模型图片最小边长必须大于0")

        image_bytes = base64.b64decode(image_base64, validate=True)
        with PILImage.open(io.BytesIO(image_bytes)) as image:
            normalized_image = PILImageOps.exif_transpose(image)
            width, height = normalized_image.size
            if width <= 0 or height <= 0:
                raise ValueError("图片尺寸无效，无法发送给视觉模型")
            if width >= min_side and height >= min_side:
                return image_base64, image_format, False

            if normalized_image.mode in ("RGBA", "LA") or (
                normalized_image.mode == "P" and "transparency" in normalized_image.info
            ):
                working_image = normalized_image.convert("RGBA")
                canvas_mode = "RGBA"
                background_color = (255, 255, 255, 0)
            else:
                working_image = normalized_image.convert("RGB")
                canvas_mode = "RGB"
                background_color = (255, 255, 255)

            scale = max(1, ceil(min_side / min(width, height)))
            if max_upscaled_side > 0:
                max_scale = max(1, max_upscaled_side // max(width, height))
                scale = min(scale, max_scale)

            resized_width = max(1, width * scale)
            resized_height = max(1, height * scale)
            resized_image = working_image.resize((resized_width, resized_height), PILImage.Resampling.NEAREST)

            canvas_width = max(min_side, resized_width)
            canvas_height = max(min_side, resized_height)
            if (canvas_width, canvas_height) != resized_image.size:
                canvas = PILImage.new(canvas_mode, (canvas_width, canvas_height), background_color)
                paste_box = ((canvas_width - resized_width) // 2, (canvas_height - resized_height) // 2)
                if resized_image.mode == "RGBA":
                    canvas.paste(resized_image, paste_box, resized_image)
                else:
                    canvas.paste(resized_image, paste_box)
                resized_image = canvas

            output_buffer = io.BytesIO()
            resized_image.save(output_buffer, format="PNG")
            resized_base64 = base64.b64encode(output_buffer.getvalue()).decode("utf-8")
            return resized_base64, "png", True

    @staticmethod
    def gif_2_static_image(gif_bytes: bytes, similarity_threshold: float = 1000.0, max_frames: int = 15) -> bytes:
        """
        将GIF图片水平拼接为静态图像，跳过相似帧

        Args:
            gif_bytes (bytes): 输入的GIF图片字节数据
            similarity_threshold (float): 判定帧相似的阈值 (MSE)，越小表示要求差异越大才算不同帧，默认1000.0
            max_frames (int): 最大抽取的帧数，默认15
        Returns:
            bytes: 拼接后的静态图像字节数据，格式为JPEG
        Raises:
            ValueError: 如果输入的GIF无效或无法处理
            MemoryError: 如果处理过程中内存不足
            Exception: 其他异常
        """
        with PILImage.open(io.BytesIO(gif_bytes)) as gif_image:
            if not gif_image.format or gif_image.format.lower() != "gif":
                logger.error("输入的图片不是有效的GIF格式")
                raise ValueError("输入的图片不是有效的GIF格式")
            # --- 流式迭代并选择帧（避免一次性加载所有帧） ---
            selected_frames: list[PILImage.Image] = []
            last_selected_frame_np = None
            frame_index = 0

            for frame in ImageSequence.Iterator(gif_image):
                # 确保是RGB格式方便比较
                frame_rgb = frame.convert("RGB")
                frame_np = np.array(frame_rgb)

                if frame_index == 0:
                    selected_frames.append(frame_rgb.copy())
                    last_selected_frame_np = frame_np
                else:
                    # 计算和上一张选中帧的差异（均方误差 MSE）
                    mse = np.mean((frame_np - last_selected_frame_np) ** 2)
                    # logger.debug(f"帧 {frame_index} 与上一选中帧的 MSE: {mse}")
                    if mse > similarity_threshold:
                        selected_frames.append(frame_rgb.copy())
                        last_selected_frame_np = frame_np
                        if len(selected_frames) >= max_frames:
                            break
                frame_index += 1

        if not selected_frames:
            logger.error("未能抽取到任何有效帧")
            raise ValueError("未能抽取到任何有效帧")

        # 获取选中的第一帧的尺寸（假设所有帧尺寸一致）
        frame_width, frame_height = selected_frames[0].size
        # 防止除以零
        if frame_height == 0:
            raise ValueError("帧高度为0，无法计算缩放尺寸")

        # 计算目标尺寸，保持宽高比
        target_height = 200  # 固定高度
        target_width = int((target_height / frame_height) * frame_width)
        # 宽度也不能是0
        if target_width == 0:
            logger.warning(f"计算出的目标宽度为0 (原始尺寸 {frame_width}x{frame_height})，调整为1")
            target_width = 1
        # 调整所有选中帧的大小
        resized_frames = [
            frame.resize((target_width, target_height), PILImage.Resampling.LANCZOS) for frame in selected_frames
        ]

        # 创建拼接图像
        total_width = target_width * len(resized_frames)
        combined_image = PILImage.new("RGB", (total_width, target_height))
        # 水平拼接图像
        for idx, frame in enumerate(resized_frames):
            combined_image.paste(frame, (idx * target_width, 0))
        buffer = io.BytesIO()
        combined_image.save(buffer, format="JPEG", quality=85)  # 保存为JPEG
        return buffer.getvalue()

    @staticmethod
    def compress_image_to_size(image_bytes: bytes, target_size: int) -> bytes:
        """将图片压缩到目标大小以内，失败时保持原图数据。"""
        if not image_bytes:
            raise ValueError("输入的图片字节数据无效")
        if target_size <= 0 or len(image_bytes) <= target_size:
            return image_bytes

        try:
            with PILImage.open(io.BytesIO(image_bytes)) as image:
                image.seek(0)
                working_image = ImageUtils._prepare_image_for_receive_compression(image)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '接收图片压缩失败，无法识别图片格式', exception=exc)
            logger.warning(f"接收图片压缩失败，无法识别图片格式: {exc}")
            return image_bytes

        compressed = ImageUtils._compress_static_image_to_size(working_image, target_size)
        if len(compressed) < len(image_bytes):
            return compressed
        return image_bytes

    @staticmethod
    def _prepare_image_for_receive_compression(image: PILImage.Image) -> PILImage.Image:
        """将任意图片整理成适合接收链路压缩的 RGB 静态图。"""
        normalized_image = PILImageOps.exif_transpose(image)
        if normalized_image.mode in ("RGBA", "LA") or (
            normalized_image.mode == "P" and "transparency" in normalized_image.info
        ):
            alpha_image = normalized_image.convert("RGBA")
            background = PILImage.new("RGB", alpha_image.size, (255, 255, 255))
            background.paste(alpha_image, mask=alpha_image.getchannel("A"))
            return background
        return normalized_image.convert("RGB")

    @staticmethod
    def _compress_static_image_to_size(image: PILImage.Image, target_size: int) -> bytes:
        """通过降低质量和缩放尺寸压缩静态图片。"""
        working_image = image.copy()
        quality = 85
        last_output = b""

        for _ in range(16):
            output_buffer = io.BytesIO()
            working_image.save(output_buffer, format="JPEG", quality=quality, optimize=True)
            output_bytes = output_buffer.getvalue()
            last_output = output_bytes
            if len(output_bytes) <= target_size:
                return output_bytes

            if quality > 55:
                quality = max(55, quality - 10)
                continue

            scale = max(0.1, min(0.95, (target_size / len(output_bytes)) ** 0.5 * 0.95))
            new_width = max(1, int(working_image.width * scale))
            new_height = max(1, int(working_image.height * scale))
            if (new_width, new_height) == working_image.size:
                break
            working_image = working_image.resize((new_width, new_height), PILImage.Resampling.LANCZOS)

        return last_output

    @staticmethod
    def image_bytes_to_base64(image_bytes: bytes) -> str:
        """
        将图片字节数据转换为Base64编码字符串

        Args:
            image_bytes (bytes): 输入的图片字节数据
        Returns:
            str: Base64编码的图片字符串
        Raises:
            ValueError: 如果输入的图片字节数据无效
        """
        if not image_bytes:
            logger.error("输入的图片字节数据无效")
            raise ValueError("输入的图片字节数据无效")
        return base64.b64encode(image_bytes).decode("utf-8")

    @staticmethod
    def image_path_to_base64(image_path: Union[str, Path]) -> Optional[str]:
        """读取图片文件并转换为 Base64 编码字符串"""
        try:
            path = Path(image_path)
            if not path.exists():
                logger.error(f"图片文件不存在: {path}")
                return None
            image_bytes = path.read_bytes()
            return base64.b64encode(image_bytes).decode("utf-8")
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, '读取图片文件失败', exception=e)
            logger.error(f"读取图片文件失败: {e}")
            return None

    @staticmethod
    def base64_to_image(base64_str: str, save_path: Union[str, Path]) -> bool:
        """将 Base64 编码字符串解码并保存为图片文件"""
        try:
            image_bytes = base64.b64decode(base64_str)
            path = Path(save_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(image_bytes)
            return True
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, '保存图片文件失败', exception=e)
            logger.error(f"保存图片文件失败: {e}")
            return False

    # ── ZG16-4 ASCII 看图（无 vision 降级） ──────────────────────

    # 预定义颜色名表（HEX → 名称，spec 6.2.4）
    _COLOR_NAME_TABLE: dict[str, str] = {
        "#FF0000": "红", "#FFA500": "橙", "#FFFF00": "黄", "#00FF00": "绿",
        "#00FFFF": "青", "#0000FF": "蓝", "#800080": "紫", "#FFC0CB": "粉",
        "#FFFFFF": "白", "#808080": "灰", "#000000": "黑", "#A52A2A": "棕",
        "#F5F5DC": "米", "#87CEEB": "天蓝", "#006400": "墨绿", "#8B0000": "暗红",
    }

    @staticmethod
    def _luminance_to_char(luminance: int, charset: str) -> str:
        """亮度 → 字符。0=最暗→charset[0]，255=最亮→charset[-1]。"""
        index = min(int(luminance / 256 * len(charset)), len(charset) - 1)
        return charset[index]

    @staticmethod
    def _resize_to_column_width(image: PILImage.Image, column_width: int) -> PILImage.Image:
        """缩放到指定列宽，行数按字符纵横比 1:2 修正。"""
        if image.width <= 0:
            return image.resize((column_width, 1), PILImage.LANCZOS)
        row_count = max(1, round(column_width * image.height / image.width * 0.5))
        return image.resize((column_width, row_count), PILImage.LANCZOS)

    @staticmethod
    def _hex_to_color_name(hex_color: str) -> str:
        """HEX → 预定义颜色名表最近邻匹配（RGB 欧氏距离）。"""
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        best_name = ""
        best_dist = float("inf")
        for hex_key, name in ImageUtils._COLOR_NAME_TABLE.items():
            kr = int(hex_key[1:3], 16)
            kg = int(hex_key[3:5], 16)
            kb = int(hex_key[5:7], 16)
            dist = (r - kr) ** 2 + (g - kg) ** 2 + (b - kb) ** 2
            if dist < best_dist:
                best_dist = dist
                best_name = name
        return best_name

    @staticmethod
    def _extract_main_colors(image: PILImage.Image, count: int) -> list[str]:
        """提取主色块：quantize → 调色板 → HEX → 颜色名。失败返回空列表。"""
        if count <= 0:
            return []
        try:
            rgb_image = image.convert("RGB")
            quantized = rgb_image.quantize(colors=count, method=PILImage.MEDIANCUT)
            palette = quantized.getpalette()
            if palette is None:
                return []
            result: list[str] = []
            for i in range(count):
                r, g, b = palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]
                hex_color = f"#{r:02X}{g:02X}{b:02X}"
                result.append(ImageUtils._hex_to_color_name(hex_color))
            return result
        except Exception:
            return []

    @staticmethod
    def to_ascii(
        image_bytes: bytes,
        *,
        column_width: int = 48,
        charset: str = "@%#*+=-:.",
        main_color_count: int = 2,
    ) -> str | None:
        """将图片字节转换为 ASCII 灰度文本。

        Args:
            image_bytes: 图片字节（压缩后）。
            column_width: ASCII 文本列宽（默认 48）。
            charset: 亮度字符集（暗→亮，默认 8 档）。
            main_color_count: 主色块标注数量（0=不标注）。

        Returns:
            ASCII 文本（[主色：...]\n + 多行字符），渲染失败返回 None。
        """
        try:
            image = PILImage.open(io.BytesIO(image_bytes))
            image = PILImageOps.exif_transpose(image)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARN, f"ASCII 渲染打开图片失败: {exc}")
            logger.warning("ASCII 渲染打开图片失败: %s", exc)
            return None

        if image.width <= 0 or image.height <= 0:
            logger.warning("ASCII 渲染：图片尺寸为 0，跳过")
            return None

        # 主色块提取（用原始 RGB 图片）
        color_prefix = ""
        if main_color_count > 0:
            colors = ImageUtils._extract_main_colors(image, main_color_count)
            if colors:
                color_prefix = f"[主色：{'/'.join(colors)}]\n"

        # 缩放 + 转灰度
        resized = ImageUtils._resize_to_column_width(image, column_width)
        gray = resized.convert("L")

        # 逐像素亮度映射
        lines: list[str] = []
        for y in range(gray.height):
            row_chars: list[str] = []
            for x in range(gray.width):
                pixel = gray.getpixel((x, y))
                row_chars.append(ImageUtils._luminance_to_char(pixel, charset))
            lines.append("".join(row_chars))

        return color_prefix + "\n".join(lines)
