from io import BytesIO

from PIL import Image

import hashlib

from src.chat.message_receive.image_receive_compressor import _process_image_components
from src.common.data_models.message_component_data_model import ImageComponent, TextComponent
from src.config.official_configs import VisualConfig


def _build_large_png() -> bytes:
    image = Image.effect_noise((1024, 1024), 100).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_receive_image_compression_updates_binary_and_hash() -> None:
    original_bytes = _build_large_png()
    target_size = 100 * 1024
    component = ImageComponent(binary_hash="original-hash", binary_data=original_bytes)

    report = _process_image_components([component], target_size, "compress")

    assert report.compressed_count == 1
    assert report.original_bytes == len(original_bytes)
    assert report.compressed_bytes == len(component.binary_data)
    assert len(component.binary_data) <= target_size
    assert component.binary_hash == hashlib.sha256(component.binary_data).hexdigest()

    Image.open(BytesIO(component.binary_data)).verify()


def test_receive_image_discard_removes_oversized_image() -> None:
    original_bytes = _build_large_png()
    target_size = 100 * 1024
    image_component = ImageComponent(binary_hash="original-hash", binary_data=original_bytes)
    text_component = TextComponent("保留文本")
    components = [text_component, image_component]

    report = _process_image_components(components, target_size, "discard")

    assert report.compressed_count == 0
    assert report.discarded_count == 1
    assert report.discarded_bytes == len(original_bytes)
    assert components == [text_component]


def test_visual_oversized_image_handling_defaults() -> None:
    visual_config = VisualConfig()

    assert visual_config.handle_oversized_images is True
    assert visual_config.max_image_size_mb == 30.0
    assert visual_config.oversized_image_handle_method == "compress"
