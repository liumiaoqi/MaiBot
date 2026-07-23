from datetime import datetime
from typing import List, Tuple

import ast
import json
import os
import random
import re
import time

from src.common.data_models.session_message_data_model import SessionMessage
from src.common.logger import get_logger
from src.config.config import global_config

from .typo_generator import ChineseTypoGenerator  # noqa: F401

# re-export: 函数定义已物理迁移到 src/core/identity.py
from src.core.identity import get_all_bot_accounts  # noqa: F401
from src.core.identity import get_bot_account  # noqa: F401
from src.core.identity import is_bot_self  # noqa: F401

logger = get_logger("chat.utils")


def _is_english_letter(char: str) -> bool:
    return ("\u0041" <= char <= "\u005a") or ("\u0061" <= char <= "\u007a")


_STAGE_DIRECTION_MAX_LEN = 10
_STAGE_DIRECTION_META_KEYWORDS = {"注意", "说明", "不要", "提醒", "备注", "注:", "参考", "提示", "重要", "警告"}
_STAGE_DIRECTION_NUMBERING = re.compile(r"^[\d①②③④⑤⑥⑦⑧⑨⑩]")


def _is_stage_direction(content: str) -> bool:
    """判断括号内容是否为舞台指示（动作/表情描写）。

    舞台指示特征：短小、描述动作/表情/语气、不含元语言。
    """
    stripped = content.strip()
    if not stripped:
        return False
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", stripped)
    if len(chinese_chars) > _STAGE_DIRECTION_MAX_LEN:
        return False
    for kw in _STAGE_DIRECTION_META_KEYWORDS:
        if kw in stripped:
            return False
    if _STAGE_DIRECTION_NUMBERING.match(stripped):
        return False
    if "：" in stripped or ": " in stripped:
        return False
    return True


def calculate_typing_time(
    input_string: str,
    chinese_time: float = 0.3,
    english_time: float = 0.15,
    is_emoji: bool = False,
) -> float:
    """
    计算输入字符串所需的时间，中文和英文字符有不同的输入时间
        input_string (str): 输入的字符串
        chinese_time (float): 中文字符的输入时间，默认为0.2秒
        english_time (float): 英文字符的输入时间，默认为0.1秒
        is_emoji (bool): 是否为emoji，默认为False

    特殊情况：
    - 如果只有一个中文字符，将使用3倍的中文输入时间
    - 在所有输入结束后，额外加上回车时间0.3秒
    - 如果is_emoji为True，将使用固定1秒的输入时间
    """
    chinese_chars = sum("\u4e00" <= char <= "\u9fff" for char in input_string)

    if chinese_chars == 1 and len(input_string.strip()) == 1:
        return chinese_time * 3 + 0.3

    total_time = 0.0
    for char in input_string:
        total_time += chinese_time if "\u4e00" <= char <= "\u9fff" else english_time
    if is_emoji:
        total_time = 1

    typing_speed = global_config.response_post_process.typing_speed
    if typing_speed <= 0:
        return 0
    total_time *= typing_speed

    return total_time


def truncate_message(message: str, max_length=20) -> str:
    """截断消息，使其不超过指定长度"""
    return f"{message[:max_length]}..." if len(message) > max_length else message


def get_western_ratio(paragraph):
    """计算段落中字母数字字符的西文比例
    原理：检查段落中字母数字字符的西文比例
    通过is_english_letter函数判断每个字符是否为西文
    只检查字母数字字符，忽略标点符号和空格等非字母数字字符

    Args:
        paragraph: 要检查的文本段落

    Returns:
        float: 西文字符比例(0.0-1.0)，如果没有字母数字字符则返回0.0
    """
    alnum_chars = [char for char in paragraph if char.isalnum()]
    if not alnum_chars:
        return 0.0

    western_count = sum(bool(_is_english_letter(char)) for char in alnum_chars)
    return western_count / len(alnum_chars)


def translate_timestamp_to_human_readable(timestamp: float, mode: str = "normal") -> str:
    # sourcery skip: merge-comparisons, merge-duplicate-blocks, switch
    """将时间戳转换为人类可读的时间格式

    Args:
        timestamp: 时间戳
        mode: 转换模式，"normal"为标准格式，"relative"为相对时间格式

    Returns:
        str: 格式化后的时间字符串
    """
    if mode == "normal":
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
    elif mode == "normal_no_YMD":
        return time.strftime("%H:%M:%S", time.localtime(timestamp))
    elif mode == "relative":
        now = time.time()
        diff = now - timestamp

        if diff < 20:
            return "刚刚"
        elif diff < 60:
            return f"{int(diff)}秒前"
        elif diff < 3600:
            return f"{int(diff / 60)}分钟前"
        elif diff < 86400:
            return f"{int(diff / 3600)}小时前"
        elif diff < 86400 * 2:
            return f"{int(diff / 86400)}天前"
        else:
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)) + ":"
    else:
        return time.strftime("%H:%M:%S", time.localtime(timestamp))


def record_replyer_action_temp(chat_id: str, reason: str, think_level: int) -> None:
    """
    临时记录replyer动作被选择的信息（仅群聊）

    Args:
        chat_id: 聊天ID
        reason: 选择理由
        think_level: 思考深度等级
    """
    try:
        temp_dir = "data/temp"
        os.makedirs(temp_dir, exist_ok=True)

        record_data = {
            "chat_id": chat_id,
            "reason": reason,
            "think_level": think_level,
            "timestamp": datetime.now().isoformat(),
        }

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"replyer_action_{timestamp_str}.json"
        filepath = os.path.join(temp_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record_data, f, ensure_ascii=False, indent=2)

        logger.debug(f"已记录replyer动作选择: chat_id={chat_id}, think_level={think_level}")
    except Exception as e:
        logger.warning(f"记录replyer动作选择失败: {e}")


def assign_message_ids(messages: List[SessionMessage]) -> List[Tuple[str, SessionMessage]]:
    """
    为消息列表中的每个消息分配唯一的简短随机ID

    Args:
        messages: 消息列表

    Returns:
        List[SessionMessage]: 分配了唯一ID的消息列表
    """
    result: List[Tuple[str, SessionMessage]] = []
    used_ids = set()
    len_i = len(messages)
    if len_i > 100:
        a = 10
        b = 99
    else:
        a = 1
        b = 9

    for i, message in enumerate(messages):
        while True:
            random_suffix = random.randint(a, b)
            message_id = f"m{i + 1}{random_suffix}"

            if message_id not in used_ids:
                used_ids.add(message_id)
                break
        result.append((message_id, message))

    return result


def parse_keywords_string(keywords_input) -> list[str]:
    # sourcery skip: use-contextlib-suppress
    """
    统一的关键词解析函数，支持多种格式的关键词字符串解析

    支持的格式：
    1. 字符串列表格式：'["utils.py", "修改", "代码", "动作"]'
    2. 斜杠分隔格式：'utils.py/修改/代码/动作'
    3. 逗号分隔格式：'utils.py,修改,代码,动作'
    4. 空格分隔格式：'utils.py 修改 代码 动作'
    5. 已经是列表的情况：["utils.py", "修改", "代码", "动作"]
    6. JSON格式字符串：'{"keywords": ["utils.py", "修改", "代码", "动作"]}'

    Args:
        keywords_input: 关键词输入，可以是字符串或列表

    Returns:
        list[str]: 解析后的关键词列表，去除空白项
    """
    if not keywords_input:
        return []

    if isinstance(keywords_input, list):
        return [str(k).strip() for k in keywords_input if str(k).strip()]

    keywords_str = str(keywords_input).strip()
    if not keywords_str:
        return []

    try:
        json_data = json.loads(keywords_str)
        if isinstance(json_data, dict) and "keywords" in json_data:
            keywords_list = json_data["keywords"]
            if isinstance(keywords_list, list):
                return [str(k).strip() for k in keywords_list if str(k).strip()]
        elif isinstance(json_data, list):
            return [str(k).strip() for k in json_data if str(k).strip()]
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        parsed = ast.literal_eval(keywords_str)
        if isinstance(parsed, list):
            return [str(k).strip() for k in parsed if str(k).strip()]
    except (ValueError, SyntaxError):
        pass

    separators = ["/", ",", " ", "|", ";"]

    for separator in separators:
        if separator in keywords_str:
            keywords_list = [k.strip() for k in keywords_str.split(separator) if k.strip()]
            if len(keywords_list) > 1:
                return keywords_list

    return [keywords_str] if keywords_str else []


# ── SSD-3 re-export（实际定义已迁移到 src/maisaka/context/post_processor.py）──
from src.maisaka.context.post_processor import process_llm_response  # noqa: F401
from src.maisaka.context.post_processor import protect_kaomoji, recover_kaomoji  # noqa: F401
from src.maisaka.context.post_processor import split_into_sentences_w_remove_punctuation  # noqa: F401


# ── SSD-4 T2.3 re-export（实际定义已迁移到 src/core/message_utils.py）──
from src.core.message_utils import is_mentioned_bot_in_message  # noqa: F401
from src.core.message_utils import get_chat_type_and_target_info  # noqa: F401
from src.core.message_utils import _has_at_component_targeting_bot  # noqa: F401
