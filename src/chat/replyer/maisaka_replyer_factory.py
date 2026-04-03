from typing import Type

from src.config.config import global_config


def get_maisaka_replyer_class() -> Type[object]:
    """根据配置返回 Maisaka replyer 类。"""
    generator_type = get_maisaka_replyer_generator_type()
    if generator_type == "multimodal":
        from .maisaka_generator_multi import MaisakaReplyGenerator

        return MaisakaReplyGenerator

    from .maisaka_generator import MaisakaReplyGenerator

    return MaisakaReplyGenerator


def get_maisaka_replyer_generator_type() -> str:
    """返回当前配置的 Maisaka replyer 生成器类型。"""
    return global_config.chat.replyer_generator_type
