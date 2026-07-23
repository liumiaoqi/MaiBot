from typing import Callable, Optional

from src.core.protocols import LLMService

from src.core.types import SessionInfo
from src.common.prompt_i18n import load_prompt
from src.config.config import global_config
from src.core.adapters.llm_service_port import get_llm_service

from .generator_base import BaseMaisakaReplyGenerator


class MaisakaReplyGenerator(BaseMaisakaReplyGenerator):
    """Maisaka replyer。"""

    def __init__(
        self,
        chat_stream: Optional[SessionInfo] = None,
        request_type: str = "maisaka.replyer",
        llm_service: Optional[LLMService] = None,
        load_prompt_func: Optional[Callable[..., str]] = None,
        enable_visual_message: Optional[bool] = None,
    ) -> None:
        super().__init__(
            chat_stream=chat_stream,
            request_type=request_type,
            llm_service=llm_service or get_llm_service(),
            load_prompt_func=load_prompt_func or load_prompt,
            enable_visual_message=enable_visual_message,
            replyer_mode=global_config.visual.replyer_mode,
        )
