from pathlib import Path

import hashlib
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.data_models.image_data_model import MaiEmoji  # noqa: E402


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
    b"\xff?\x00\x05\xfe\x02\xfeA\xe2!\xbc\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.asyncio
async def test_reuses_existing_formatted_file_when_tmp_was_consumed(tmp_path: Path) -> None:
    image_hash = hashlib.sha256(PNG_1X1).hexdigest()
    existing_file = tmp_path / f"{image_hash}.png"
    tmp_file = tmp_path / f"{image_hash}.tmp"
    existing_file.write_bytes(PNG_1X1)
    tmp_file.write_bytes(PNG_1X1)

    emoji = MaiEmoji(full_path=tmp_file, image_bytes=PNG_1X1)
    tmp_file.unlink()

    assert await emoji.calculate_hash_format() is True
    assert emoji.full_path == existing_file.resolve()
    assert emoji.file_name == existing_file.name
    assert not tmp_file.exists()
