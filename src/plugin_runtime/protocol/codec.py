"""MsgPack 编解码器"""

from abc import ABC, abstractmethod
from typing import Any, Dict

import msgpack

from .envelope import Envelope


class Codec(ABC):
    """消息编解码器基类"""

    @abstractmethod
    def encode_envelope(self, envelope: Envelope) -> bytes: ...

    @abstractmethod
    def decode_envelope(self, data: bytes) -> Envelope: ...

    @abstractmethod
    def encode(self, obj: Dict[str, Any]) -> bytes: ...

    @abstractmethod
    def decode(self, data: bytes) -> Dict[str, Any]: ...


class MsgPackCodec(Codec):
    """MsgPack 编解码器"""

    def encode(self, obj: Dict[str, Any]) -> bytes:
        result = msgpack.packb(obj, use_bin_type=True)
        if result is None:
            raise ValueError("msgpack.packb returned None, expected bytes")
        return result

    def decode(self, data: bytes) -> Dict[str, Any]:
        result = msgpack.unpackb(data, raw=False)
        if not isinstance(result, dict):
            raise ValueError(f"期望解码为 dict，实际为 {type(result)}")
        return result

    def encode_envelope(self, envelope: Envelope) -> bytes:
        return self.encode(envelope.model_dump())

    def decode_envelope(self, data: bytes) -> Envelope:
        raw = self.decode(data)
        return Envelope.model_validate(raw)
