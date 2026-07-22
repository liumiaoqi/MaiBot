"""Maisaka 历史消息轮次结束后处理。"""

from dataclasses import dataclass
from json import dumps, loads
from math import ceil

from .history import drop_leading_orphan_tool_results, normalize_tool_call_result_pairs
from .messages import (
    AssistantMessage,
    ComplexSessionMessage,
    FOCUS_WAKEUP_SOURCE_KINDS,
    LLMContextMessage,
    SessionBackedMessage,
    ToolResultMessage,
)
from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.maisaka.memory.mid_term import is_mid_term_memory_message

TRIM_TARGET_RATIO = 1.0
TRIM_THRESHOLD_RATIO = 2.0
ASSISTANT_OPTIMIZATION_KEEP_COUNT = 3
FOLDED_TOOL_COMPLEX_MESSAGE_THRESHOLD = 1024
TRIMMED_TOOL_CALL_DROP_NAMES = {"continue", "finish", "no_action", "reply", "wait"}


@dataclass(slots=True)

# ── process_llm_response 及相关辅助函数（从 src/chat/utils/utils.py 物理迁移）──
# 迁移时间：SSD-3
# 原位置：src/chat/utils/utils.py

def split_into_sentences_w_remove_punctuation(text: str) -> list[str]:
    """将文本分割成句子，并根据概率合并
    1. 识别分割点（, ， 。 ; 空格），但如果分割点左右都是英文字母则不分割。
    2. 将文本分割成 (内容, 分隔符) 的元组。
    3. 根据原始文本长度计算合并概率，概率性地合并相邻段落。
    注意：此函数假定颜文字已在上层被保护。
    Args:
        text: 要分割的文本字符串 (假定颜文字已被保护)
    Returns:
        List[str]: 分割和合并后的句子列表
    """
    # 预处理：处理多余的换行符
    # 1. 将连续的换行符替换为单个换行符（保留换行符用于分割）
    text = re.sub(r"\n\s*\n+", "\n", text)
    # 2. 处理换行符和其他分隔符的组合（保留换行符，删除其他分隔符）
    text = re.sub(r"\n\s*([，,。;\s])", r"\n\1", text)
    text = re.sub(r"([，,。;\s])\s*\n", r"\1\n", text)

    # 处理两个汉字中间的换行符（保留换行符，不替换为句号，让换行符强制分割）
    # text = re.sub(r"([\u4e00-\u9fff])\n([\u4e00-\u9fff])", r"\1。\2", text)  # 注释掉，保留换行符用于分割

    len_text = len(text)
    if len_text < 3:
        return list(text) if random.random() < 0.01 else [text]

    # 先标记哪些位置位于成对引号内部，避免在引号内部进行句子分割
    # 支持的引号包括：中英文单/双引号和常见中文书名号/引号
    quote_chars = {
        '"',
        "'",
        "“",
        "”",
        "‘",
        "’",
        "「",
        "」",
        "『",
        "』",
    }
    inside_quote = [False] * len_text
    in_quote = False
    current_quote_char = ""
    for idx, ch in enumerate(text):
        if ch in quote_chars:
            # 遇到引号时切换状态（英文引号本身开闭相同，用同一个字符表示）
            if not in_quote:
                in_quote = True
                current_quote_char = ch
                inside_quote[idx] = False
            else:
                # 只有遇到同一类引号才视为关闭
                if ch == current_quote_char or ch in {'"', "'"} and current_quote_char in {'"', "'"}:
                    in_quote = False
                    current_quote_char = ""
                inside_quote[idx] = False
        else:
            inside_quote[idx] = in_quote

    # 定义分隔符（包含换行符）
    separators = {"，", ",", " ", "。", ";", "\n"}
    segments = []
    current_segment = ""

    # 1. 分割成 (内容, 分隔符) 元组
    i = 0
    while i < len(text):
        char = text[i]
        if char in separators:
            # 引号内部一律不作为分割点（包括换行）
            if inside_quote[i]:
                can_split = False
            else:
                # 换行符在不在引号内时都强制分割
                if char == "\n":
                    can_split = True
                else:
                    # 检查分割条件
                    can_split = True
                    # 检查分隔符左右是否有冒号（中英文），如果有则不分割
                    if i > 0:
                        prev_char = text[i - 1]
                        if prev_char in {":", "："}:
                            can_split = False
                    if i < len(text) - 1:
                        next_char = text[i + 1]
                        if next_char in {":", "："}:
                            can_split = False

                    # 如果左右没有冒号，再检查空格的特殊情况
                    if can_split and char == " " and i > 0 and i < len(text) - 1:
                        prev_char = text[i - 1]
                        next_char = text[i + 1]
                        dash_chars = {"-", "—"}
                        if prev_char in dash_chars or next_char in dash_chars:
                            can_split = False
                        else:
                            # 不分割数字和数字、数字和英文、英文和数字、英文和英文之间的空格
                            prev_is_alnum = prev_char.isdigit() or is_english_letter(prev_char)
                            next_is_alnum = next_char.isdigit() or is_english_letter(next_char)
                            if prev_is_alnum and next_is_alnum:
                                can_split = False

            if can_split:
                # 只有当当前段不为空时才添加
                if current_segment:
                    segments.append((current_segment, char))
                # 如果当前段为空，但分隔符是空格或换行符，则也添加一个空段（保留分隔符）
                elif char in {" ", "\n"}:
                    segments.append(("", char))
                current_segment = ""
            else:
                # 不分割，将分隔符加入当前段
                current_segment += char
        else:
            current_segment += char
        i += 1

    # 添加最后一个段（没有后续分隔符）
    if current_segment:
        segments.append((current_segment, ""))

    # 过滤掉完全空的段（内容和分隔符都为空）
    segments = [(content, sep) for content, sep in segments if content or sep]

    # 如果分割后为空（例如，输入全是分隔符且不满足保留条件），恢复颜文字并返回
    if not segments:
        return [text] if text else []  # 如果原始文本非空，则返回原始文本（可能只包含未被分割的字符或颜文字占位符）

    # 2. 概率合并
    if len_text < 12:
        split_strength = 0.2
    elif len_text < 32:
        split_strength = 0.6
    else:
        split_strength = 0.7
    # 合并概率与分割强度相反
    merge_probability = 1.0 - split_strength

    merged_segments = []
    idx = 0
    while idx < len(segments):
        current_content, current_sep = segments[idx]

        # 检查是否可以与下一段合并
        # 条件：不是最后一段，且随机数小于合并概率，且当前段有内容（避免合并空段）
        if (
            idx + 1 < len(segments)
            and current_content
            and current_sep != "\n"
            and random.random() < merge_probability
        ):
            next_content, next_sep = segments[idx + 1]
            # 合并: (内容1 + 分隔符1 + 内容2, 分隔符2)
            # 只有当下一段也有内容时才合并文本，否则只传递分隔符
            if next_content:
                merged_content = current_content + current_sep + next_content
                merged_segments.append((merged_content, next_sep))
            else:  # 下一段内容为空，只保留当前内容和下一段的分隔符
                merged_segments.append((current_content, next_sep))

            idx += 2  # 跳过下一段，因为它已被合并
        else:
            # 不合并，直接添加当前段
            merged_segments.append((current_content, current_sep))
            idx += 1

    # 提取最终的句子内容
    final_sentences = [content for content, sep in merged_segments if content]  # 只保留有内容的段

    # 清理可能引入的空字符串和仅包含空白的字符串
    final_sentences = [
        s for s in final_sentences if s.strip()
    ]  # 过滤掉空字符串以及仅包含空白（如换行符、空格）的字符串
    final_sentences = [
        normalized_sentence
        for sentence in final_sentences
        if (normalized_sentence := re.sub(r"[^\S\r\n]*[\r\n]+[^\S\r\n]*", " ", sentence).strip())
    ]

    logger.debug(f"分割并合并后的句子: {final_sentences}")
    return final_sentences


def merge_sentences_to_max_count(sentences: list[str], max_count: int) -> list[str]:
    """按顺序将分句合并到指定条数以内。"""

    if len(sentences) <= max_count:
        return sentences

    merged_sentences: list[str] = []
    sentence_count = len(sentences)
    start_index = 0
    for group_index in range(max_count):
        remaining_sentences = sentence_count - start_index
        remaining_groups = max_count - group_index
        group_size = (remaining_sentences + remaining_groups - 1) // remaining_groups
        merged_sentences.append("".join(sentences[start_index : start_index + group_size]))
        start_index += group_size

    return merged_sentences


def random_remove_punctuation(text: str) -> str:
    """随机处理标点符号，模拟人类打字习惯

    Args:
        text: 要处理的文本

    Returns:
        str: 处理后的文本
    """
    result = ""
    text_len = len(text)

    for i, char in enumerate(text):
        if char == "。" and i == text_len - 1:  # 结尾的句号
            if random.random() > 0.1:  # 90%概率删除结尾句号
                continue
        elif char == "，":
            rand = random.random()
            if rand < 0.05:  # 5%概率删除逗号
                continue
            elif rand < 0.25:  # 20%概率把逗号变成空格
                result += " "
                continue
        result += char
    return result


def _get_random_default_reply() -> str:
    """获取随机默认回复"""
    default_replies = [
        f"{global_config.bot.nickname}不知道哦",
        f"{global_config.bot.nickname}不知道",
        "不知道哦",
        "不知道",
        "不晓得",
        "懒得说",
        "()",
    ]
    return random.choice(default_replies)


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


def process_llm_response(text: str, enable_splitter: bool = True, enable_chinese_typo: bool = True) -> list[str]:
    if not global_config.response_post_process.enable_response_post_process:
        return [text]

    # 先保护颜文字
    if global_config.response_splitter.enable_kaomoji_protection:
        protected_text, kaomoji_mapping = protect_kaomoji(text)
        logger.debug(f"保护颜文字后的文本: {protected_text}")
    else:
        protected_text = text
        kaomoji_mapping = {}
    # 提取被 () 或 [] 或 （）包裹且包含中文的内容
    pattern = re.compile(r"[(\[（](?=.*[一-鿿]).*?[)\]）]")
    _extracted_contents = pattern.findall(protected_text)  # 在保护后的文本上查找

    def _replace_bracket_content(match: re.Match) -> str:
        """保留舞台指示（短小动作/表情描写），删除多余说明。"""
        content = match.group(0)
        inner = content[1:-1].strip()
        if _is_stage_direction(inner):
            return content
        return ""

    cleaned_text = pattern.sub(_replace_bracket_content, protected_text)

    if cleaned_text == "":
        return ["呃呃"]

    logger.debug(f"{text}去除括号处理后的文本: {cleaned_text}")

    # 对清理后的文本进行进一步处理
    max_length = global_config.response_splitter.max_length * 2
    max_sentence_num = global_config.response_splitter.max_sentence_num
    max_split_num = global_config.response_splitter.max_split_num
    # 如果基本上是中文，则进行长度过滤
    if get_western_ratio(cleaned_text) < 0.1 and len(cleaned_text) > max_length:
        logger.warning(f"回复过长 ({len(cleaned_text)} 字符)，返回默认回复")
        return [_get_random_default_reply()]

    typo_generator = ChineseTypoGenerator(
        error_rate=global_config.chinese_typo.error_rate,
        min_freq=global_config.chinese_typo.min_freq,
        tone_error_rate=global_config.chinese_typo.tone_error_rate,
        word_replace_rate=global_config.chinese_typo.word_replace_rate,
    )

    if global_config.response_splitter.enable and enable_splitter:
        split_sentences = split_into_sentences_w_remove_punctuation(cleaned_text)
    else:
        split_sentences = [cleaned_text]

    sentences: List[str] = []
    for sentence in split_sentences:
        if global_config.chinese_typo.enable and enable_chinese_typo:
            typoed_text, typo_corrections = typo_generator.create_typo_sentence(sentence)
            if typo_corrections:
                # 50%概率新增正确字/词，50%概率用正确分句替换错别字分句
                if random.random() < 0.5:
                    sentences.append(typoed_text)
                    sentences.append(typo_corrections)
                else:
                    # 用正确的分句替换错别字分句
                    sentences.append(sentence)
            else:
                sentences.append(typoed_text)
        else:
            sentences.append(sentence)

    if len(sentences) > max_sentence_num:
        if global_config.response_splitter.enable_overflow_return_all:
            logger.warning(f"分割后消息数量过多 ({len(sentences)} 条)，直接返回原文")
            sentences = [cleaned_text]
        else:
            logger.warning(f"分割后消息数量过多 ({len(sentences)} 条)，返回默认回复")
            return [_get_random_default_reply()]

    sentences = merge_sentences_to_max_count(sentences, max_split_num)

    # if extracted_contents:
    #     for content in extracted_contents:
    #         sentences.append(content)

    # 在所有句子处理完毕后，对包含占位符的列表进行恢复
    if global_config.response_splitter.enable_kaomoji_protection:
        sentences = recover_kaomoji(sentences, kaomoji_mapping)

    return sentences


def calculate_typing_time(
    input_string: str,
    # thinking_start_time: float,
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
    # chinese_time *= 1 / typing_speed_multiplier
    # english_time *= 1 / typing_speed_multiplier
    # 计算中文字符数
    chinese_chars = sum("\u4e00" <= char <= "\u9fff" for char in input_string)

    # 如果只有一个中文字符，使用3倍时间
    if chinese_chars == 1 and len(input_string.strip()) == 1:
        return chinese_time * 3 + 0.3  # 加上回车时间

    # 正常计算所有字符的输入时间
    total_time = 0.0
    for char in input_string:
        total_time += chinese_time if "\u4e00" <= char <= "\u9fff" else english_time
    if is_emoji:
        total_time = 1

    typing_speed = global_config.response_post_process.typing_speed
    if typing_speed <= 0:
        return 0
    total_time *= typing_speed

    # if time.time() - thinking_start_time > 10:
    #     total_time = 1

    # print(f"thinking_start_time:{thinking_start_time}")
    # print(f"nowtime:{time.time()}")
    # print(f"nowtime - thinking_start_time:{time.time() - thinking_start_time}")
    # print(f"{total_time}")

    return total_time  # 加上回车时间


def truncate_message(message: str, max_length=20) -> str:
    """截断消息，使其不超过指定长度"""
    return f"{message[:max_length]}..." if len(message) > max_length else message


def protect_kaomoji(sentence):
    """ "
    识别并保护句子中的颜文字（含括号与无括号），将其替换为占位符，
    并返回替换后的句子和占位符到颜文字的映射表。
    Args:
        sentence (str): 输入的原始句子
    Returns:
        tuple: (处理后的句子, {占位符: 颜文字})
    """
    kaomoji_pattern = re.compile(
        r"("
        r"[(\[（【]"  # 左括号
        r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
        r"[^一-龥a-zA-Z0-9\s]"  # 非中文、非英文、非数字、非空格字符（必须包含至少一个）
        r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
        r"[)\]）】"  # 右括号
        r"]"
        r")"
        r"|"
        r"([▼▽・ᴥω･﹏^><≧≦￣｀´∀ヮДд︿﹀へ｡ﾟ╥╯╰︶︹•⁄]{2,15})"
    )

    kaomoji_matches = kaomoji_pattern.findall(sentence)
    placeholder_to_kaomoji = {}

    for match in kaomoji_matches:
        kaomoji = match[0] or match[1]
        if kaomoji.startswith("[表情包") and kaomoji.endswith("]"):
            continue
        idx = len(placeholder_to_kaomoji)
        placeholder = f"__KAOMOJI_{idx}__"
        sentence = sentence.replace(kaomoji, placeholder, 1)
        placeholder_to_kaomoji[placeholder] = kaomoji

    return sentence, placeholder_to_kaomoji


def recover_kaomoji(sentences, placeholder_to_kaomoji):
    """
    根据映射表恢复句子中的颜文字。
    Args:
        sentences (list): 含有占位符的句子列表
        placeholder_to_kaomoji (dict): 占位符到颜文字的映射表
    Returns:
        list: 恢复颜文字后的句子列表
    """
    recovered_sentences = []
    for sentence in sentences:
        for placeholder, kaomoji in placeholder_to_kaomoji.items():
            sentence = sentence.replace(placeholder, kaomoji)
        recovered_sentences.append(sentence)
    return recovered_sentences


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

    western_count = sum(bool(is_english_letter(char)) for char in alnum_chars)
    return western_count / len(alnum_chars)



class HistoryPostProcessResult:
    """历史后处理结果。"""

    history: list[LLMContextMessage]
    removed_messages: list[LLMContextMessage]
    removed_count: int
    changed_count: int
    remaining_context_count: int


def process_chat_history_after_cycle(
    chat_history: list[LLMContextMessage],
    *,
    max_context_size: int,
    enable_context_optimization: bool = False,
) -> HistoryPostProcessResult:
    """在每轮结束后统一执行历史裁切与清理。"""

    processed_history: list[LLMContextMessage] = []
    one_shot_removed_count = 0
    for message in chat_history:
        if message.source in FOCUS_WAKEUP_SOURCE_KINDS:
            one_shot_removed_count += 1
            continue
        if not message.consume_once():
            one_shot_removed_count += 1
            continue
        processed_history.append(message)
    processed_history, normalized_removed_count, moved_tool_result_count = _normalize_history_structure(
        processed_history
    )
    remaining_context_count = sum(1 for message in processed_history if message.count_in_context)

    optimized_removed_count = 0
    if enable_context_optimization:
        optimized_removed_messages = _trim_assistant_history_to_latest(
            processed_history,
            keep_count=ASSISTANT_OPTIMIZATION_KEEP_COUNT,
        )
        if optimized_removed_messages:
            processed_history, removed_after_optimize_count, moved_after_optimize_count = _normalize_history_structure(
                processed_history
            )
            optimized_removed_count = len(optimized_removed_messages) + removed_after_optimize_count
            moved_tool_result_count += moved_after_optimize_count
            remaining_context_count = sum(1 for message in processed_history if message.count_in_context)

    compact_removed_count = 0
    removed_messages: list[LLMContextMessage] = []
    trim_threshold = ceil(max_context_size * TRIM_THRESHOLD_RATIO)
    if remaining_context_count > trim_threshold:
        target_context_count = max(1, int(max_context_size * TRIM_TARGET_RATIO))
        removed_messages = _trim_history_to_context_target(
            processed_history,
            target_context_count=target_context_count,
        )
        processed_history, removed_after_trim_count, moved_after_trim_count = _normalize_history_structure(
            processed_history
        )
        compact_removed_count = len(removed_messages) + removed_after_trim_count
        moved_tool_result_count += moved_after_trim_count

    remaining_context_count = sum(1 for message in processed_history if message.count_in_context)
    removed_count = one_shot_removed_count + normalized_removed_count + optimized_removed_count + compact_removed_count
    changed_count = removed_count + moved_tool_result_count
    return HistoryPostProcessResult(
        history=processed_history,
        removed_messages=removed_messages,
        removed_count=removed_count,
        changed_count=changed_count,
        remaining_context_count=remaining_context_count,
    )


def _trim_assistant_history_to_latest(
    chat_history: list[LLMContextMessage],
    *,
    keep_count: int,
) -> list[LLMContextMessage]:
    """只保留最新的若干条 assistant 历史消息。"""

    normalized_keep_count = max(0, keep_count)
    assistant_indexes = [
        index
        for index, message in enumerate(chat_history)
        if isinstance(message, AssistantMessage)
    ]
    remove_count = len(assistant_indexes) - normalized_keep_count
    if remove_count <= 0:
        return []

    remove_indexes = set(assistant_indexes[:remove_count])
    removed_messages = [
        message
        for index, message in enumerate(chat_history)
        if index in remove_indexes
    ]
    tool_result_by_call_id = {
        message.tool_call_id: message
        for message in chat_history
        if isinstance(message, ToolResultMessage) and message.tool_call_id
    }
    preserved_tool_result_ids = {
        tool_call.call_id
        for message in removed_messages
        if isinstance(message, AssistantMessage)
        for tool_call in message.tool_calls
        if tool_call.call_id in tool_result_by_call_id
    }

    optimized_history: list[LLMContextMessage] = []
    for index, message in enumerate(chat_history):
        if index in remove_indexes:
            if isinstance(message, AssistantMessage):
                preserved_message = _build_trimmed_assistant_tool_user_message(
                    message,
                    tool_result_by_call_id=tool_result_by_call_id,
                )
                if preserved_message is not None:
                    optimized_history.append(preserved_message)
            continue
        if isinstance(message, ToolResultMessage) and message.tool_call_id in preserved_tool_result_ids:
            continue
        optimized_history.append(message)

    chat_history[:] = optimized_history
    return removed_messages


def _build_trimmed_assistant_tool_user_message(
    assistant_message: AssistantMessage,
    *,
    tool_result_by_call_id: dict[str, ToolResultMessage],
) -> SessionBackedMessage | None:
    """将被优化裁掉的 assistant 工具链折叠成普通 user 消息，避免破坏 tool 协议配对。"""

    if not assistant_message.tool_calls:
        return None

    tool_sections: list[str] = []
    for tool_call in assistant_message.tool_calls:
        if tool_call.func_name in TRIMMED_TOOL_CALL_DROP_NAMES:
            continue

        tool_result = tool_result_by_call_id.get(tool_call.call_id)
        if tool_call.func_name == "tool_search":
            tool_sections.append(_format_trimmed_tool_search_call(tool_call.args or {}, tool_result))
            continue

        args_text = dumps(tool_call.args or {}, ensure_ascii=False, sort_keys=True)
        section_lines = [
            f"- tool_call_id: {tool_call.call_id}",
            f"  tool_name: {tool_call.func_name}",
            f"  args: {args_text}",
        ]
        if tool_result is not None:
            result_status = "success" if tool_result.success else "failed"
            section_lines.extend(
                [
                    f"  result_status: {result_status}",
                    f"  result: {tool_result.content}",
                ]
            )
        tool_sections.append("\n".join(section_lines))

    if not tool_sections:
        return None

    folded_text = "[已折叠的历史工具调用]\n" + "\n".join(tool_sections)
    message_id = f"optimized_tool_history:{assistant_message.timestamp.timestamp()}"
    if len(folded_text) > FOLDED_TOOL_COMPLEX_MESSAGE_THRESHOLD:
        return ComplexSessionMessage(
            raw_message=MessageSequence([TextComponent(folded_text)]),
            visible_text=folded_text,
            timestamp=assistant_message.timestamp,
            message_id=message_id,
            source_kind="optimized_tool_history",
            prompt_text=folded_text,
            complex_message_type="tool_history",
        )

    return SessionBackedMessage(
        raw_message=MessageSequence([TextComponent(folded_text)]),
        visible_text=folded_text,
        timestamp=assistant_message.timestamp,
        message_id=message_id,
        source_kind="optimized_tool_history",
    )


def _format_trimmed_tool_search_call(
    args: dict,
    tool_result: ToolResultMessage | None,
) -> str:
    """以更短的形式保留 tool_search 结果，供后续恢复 deferred tool 激活状态。"""

    query = str(args.get("query", "")).strip()
    matched_tool_names = _parse_tool_search_result_tool_names(tool_result.content if tool_result is not None else "")
    matched_text = ", ".join(matched_tool_names) if matched_tool_names else "无"
    if query:
        return f"- tool_search: {matched_text} (query={query})"
    return f"- tool_search: {matched_text}"


def _parse_tool_search_result_tool_names(content: str) -> list[str]:
    """从 tool_search 的结果文本中提取工具名，折叠时只保留最关键的信息。"""

    try:
        structured_content = loads(content)
    except (TypeError, ValueError):
        structured_content = None

    if isinstance(structured_content, dict):
        raw_tool_names = structured_content.get("matched_tool_names")
        if isinstance(raw_tool_names, list):
            return [str(tool_name).strip() for tool_name in raw_tool_names if str(tool_name).strip()]

    matched_tool_names: list[str] = []
    for raw_line in content.splitlines():
        normalized_line = raw_line.strip()
        if not normalized_line.startswith("- "):
            continue
        normalized_name = normalized_line[2:].split("（", 1)[0].strip()
        if normalized_name:
            matched_tool_names.append(normalized_name)
    return matched_tool_names


def _normalize_history_structure(
    chat_history: list[LLMContextMessage],
) -> tuple[list[LLMContextMessage], int, int]:
    """规范化历史消息结构，保证工具调用链符合 LLM 消息协议。"""

    processed_history, normalize_stats = normalize_tool_call_result_pairs(chat_history)
    processed_history, leading_orphan_removed_count = drop_leading_orphan_tool_results(processed_history)
    removed_count = (
        normalize_stats["orphan_tool_results"]
        + normalize_stats["unanswered_tool_calls"]
        + leading_orphan_removed_count
    )
    return (
        processed_history,
        removed_count,
        normalize_stats["moved_tool_results"],
    )


def _trim_history_to_context_target(
    chat_history: list[LLMContextMessage],
    *,
    target_context_count: int,
) -> list[LLMContextMessage]:
    """移除最早的一段历史，直到普通上下文消息数量降到目标值以内。"""

    remaining_context_count = sum(1 for message in chat_history if message.count_in_context)
    if remaining_context_count <= target_context_count:
        return []

    remove_indexes: list[int] = []
    for index, message in enumerate(chat_history):
        if is_mid_term_memory_message(message):
            continue

        remove_indexes.append(index)
        if message.count_in_context:
            remaining_context_count -= 1
            if remaining_context_count <= target_context_count:
                break

    if not remove_indexes:
        return []

    removed_messages = [chat_history[index] for index in remove_indexes]
    for index in reversed(remove_indexes):
        del chat_history[index]
    return removed_messages


# =============================================================================
# 桥接 re-export — process_llm_response
# =============================================================================
# process_llm_response 当前定义在 src/chat/utils/utils.py，
# 但逻辑上属于 maisaka 回复后处理。此处 re-export 作为集中桥接点。
# 后续架构演进将把函数定义物理迁移到 maisaka 层。
