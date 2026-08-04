from rich.traceback import install
from typing import Optional

import base64

from src.common.logger import get_logger
from src.core.app_config_port_registry import get_app_config_port
from src.core.adapters.llm_service_port import get_llm_service
from src.llm_models.model_requirement import model_requirement


install(extra_lines=3)

logger = get_logger("voice_utils")


@model_requirement(capabilities=["voice"], critical=False)
class VoiceAsr:
    """语音识别委派声明（ZG-12）：无 voice 模型时降级为不支持并告警。"""


async def get_voice_text(voice_bytes: bytes) -> Optional[str]:
    """
    获取音频文件转录文本

    Args:
        voice_bytes (bytes): 语音消息的字节数据
    Returns:
        return (Optional[str]): 转录后的文本描述，如果转录失败或未启用语音识别功能，则返回 None
    """
    if not get_app_config_port().get_voice_enable_asr():
        logger.warning("语音识别未启用，无法处理语音消息")
        return None
    try:
        voice_base64 = base64.b64encode(voice_bytes).decode("utf-8")
        transcription_result = await get_llm_service().transcribe_audio("voice", voice_base64)
        text = transcription_result.text
        if not text:
            logger.warning("语音转文字结果为空")

        # logger.debug(f"转录结果是是{text}")

        return text
    except Exception as e:
        logger.error(f"语音转文字失败: {str(e)}")
        return None
