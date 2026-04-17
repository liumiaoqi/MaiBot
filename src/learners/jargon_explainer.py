from typing import Optional, Dict, List
from sqlmodel import select, func as fn

import json

from src.common.database.database import get_db_session
from src.common.database.database_model import Jargon
from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("jargon_explainer")


def search_jargon(
    keyword: str,
    chat_id: Optional[str] = None,
    limit: int = 10,
    case_sensitive: bool = False,
    fuzzy: bool = True,
) -> List[Dict[str, str]]:
    """
    搜索 jargon，支持大小写不敏感和模糊搜索

    Args:
        keyword: 搜索关键词
        chat_id: 可选的聊天 ID（session_id）
            - 如果开启了 all_global：此参数被忽略，查询所有 is_global=True 的记录
            - 如果关闭了 all_global：如果提供则优先搜索该聊天或 global 的 jargon
        limit: 返回结果数量限制，默认 10
        case_sensitive: 是否大小写敏感，默认 False（不敏感）
        fuzzy: 是否模糊搜索，默认 True（使用 LIKE 匹配）

    Returns:
        List[Dict[str, str]]: 包含 content, meaning 的字典列表
    """
    if not keyword or not keyword.strip():
        return []

    keyword = keyword.strip()

    # 构建搜索条件
    if case_sensitive:  # 大小写敏感
        search_condition = Jargon.content.contains(keyword) if fuzzy else Jargon.content == keyword  # type: ignore
    else:
        keyword_lower = keyword.lower()
        search_condition = (
            fn.LOWER(Jargon.content).contains(keyword_lower) if fuzzy else fn.LOWER(Jargon.content) == keyword_lower
        )

    # 根据 all_global 配置决定查询逻辑同时，限制结果数量（先多取一些，因为后面可能过滤）
    if global_config.expression.all_global_jargon:
        # 开启 all_global：所有记录都是全局的，查询所有 is_global=True 的记录（无视 chat_id）
        query = select(Jargon).where(search_condition, Jargon.is_global).order_by(Jargon.count.desc()).limit(limit * 2)  # type: ignore
    else:
        # 关闭 all_global：查询所有记录，chat_id 过滤在 Python 层面进行
        query = select(Jargon).where(search_condition).order_by(Jargon.count.desc()).limit(limit * 2)  # type: ignore

    # 执行查询并返回结果
    results: List[Dict[str, str]] = []
    with get_db_session() as session:
        jargons = session.exec(query).all()

        for jargon in jargons:
            # 如果提供了 chat_id 且 all_global=False，需要检查 session_id_dict 是否包含目标 chat_id
            if chat_id and not global_config.expression.all_global_jargon and not jargon.is_global:
                try:  # 解析 session_id_dict
                    session_id_dict = json.loads(jargon.session_id_dict) if jargon.session_id_dict else {}
                except (json.JSONDecodeError, TypeError):
                    session_id_dict = {}
                    logger.warning(
                        f"解析 session_id_dict 失败，jargon_id={jargon.id}，原始数据：{jargon.session_id_dict}"
                    )

                # 检查是否包含目标 chat_id
                if chat_id not in session_id_dict:
                    continue
            # 只返回有 meaning 的记录
            if not jargon.meaning.strip():
                continue

            results.append({"content": jargon.content or "", "meaning": jargon.meaning or ""})
            # 达到限制数量后停止
            if len(results) >= limit:
                break

    return results
