"""decode_metadata 读侧解码：只接受 JSON，旧 pickle 字节必须具名拒绝。"""

import pytest

from src.A_memorix.core.storage.stores._utils import MetadataDecodeError, decode_metadata


def test_decode_metadata_rejects_pickle_bytes():
    """旧 pickle 字节（0x80 开头）不得静默返回 {}：抛 MetadataDecodeError 并带首字节与原异常。"""
    with pytest.raises(MetadataDecodeError) as excinfo:
        decode_metadata(b"\x80\x04}\x94.")
    message = str(excinfo.value)
    assert "首字节=80" in message
    assert "UnicodeDecodeError" in message


def test_decode_metadata_accepts_json_str_and_dict():
    """JSON 字符串 / dict / None / 空串的行为保持不变。"""
    assert decode_metadata('{"a":1}') == {"a": 1}
    assert decode_metadata({"a": 1}) == {"a": 1}
    assert decode_metadata(None) == {}
    assert decode_metadata("") == {}
