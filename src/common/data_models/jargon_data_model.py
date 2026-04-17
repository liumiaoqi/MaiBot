from typing import Optional, Dict

import json

from src.common.database.database_model import Jargon
from src.common.logger import get_logger

from . import BaseDatabaseDataModel

logger = get_logger("jargon_data_model")


class MaiJargon(BaseDatabaseDataModel[Jargon]):
    """Jargon 数据模型，与数据库模型 Jargon 互转。"""

    def __init__(
        self,
        content: str,
        meaning: str,
        item_id: Optional[int] = None,
        raw_content: Optional[str] = None,
        session_id_list: Optional[Dict[str, int]] = None,
        count: int = 0,
        is_jargon: Optional[bool] = True,
        is_complete: bool = False,
        is_global: bool = False,
        last_inference_count: int = 0,
        inference_with_context: Optional[str] = None,
        inference_with_content_only: Optional[str] = None,
    ):
        self.item_id = item_id
        """自增主键ID"""
        self.content = content
        """黑话内容"""
        self.raw_content = raw_content
        """原始内容，未处理的黑话内容"""
        self.meaning = meaning
        """黑话含义"""
        self.session_id_list = session_id_list or {}
        """会话ID字典，区分是否为全局黑话，格式为{"session_id": session_count, ...}，如果为空表示全局黑话"""
        self.count = count
        """使用次数"""
        self.is_jargon = is_jargon
        """是否为黑话，False表示为白话"""
        self.is_complete = is_complete
        """是否为已经完成全部推断（count > 100后不再推断）"""
        self.is_global = is_global
        """是否为全局黑话（独立于session_id_dict）"""
        self.last_inference_count = last_inference_count
        """上一次进行推断时的count值，用于判断是否需要重新推断"""
        self.inference_with_context = inference_with_context
        """带上下文的推断结果，JSON格式"""
        self.inference_with_content_only = inference_with_content_only
        """只基于词条的推断结果，JSON格式"""

    @classmethod
    def from_db_instance(cls, db_record: Jargon) -> "MaiJargon":
        """从数据库模型创建 MaiJargon 实例。"""
        json_list: Dict[str, int] = {}
        try:
            # 解析存储的字符串为字典
            json_list = json.loads(db_record.session_id_dict)
        except Exception as e:
            logger.error(f"Error parsing session_id_list: {e}")
        return cls(
            item_id=db_record.id,
            content=db_record.content,
            meaning=db_record.meaning,
            raw_content=db_record.raw_content,
            session_id_list=json_list,
            count=db_record.count,
            is_jargon=db_record.is_jargon,
            is_complete=db_record.is_complete,
            is_global=db_record.is_global,
            last_inference_count=db_record.last_inference_count,
            inference_with_context=db_record.inference_with_context,
            inference_with_content_only=db_record.inference_with_content_only,
        )

    def to_db_instance(self) -> Jargon:
        """将 MaiJargon 转换为数据库模型 Jargon。"""
        dumped_session_id_list = json.dumps(self.session_id_list)
        return Jargon(
            content=self.content,
            raw_content=self.raw_content,
            meaning=self.meaning,
            session_id_dict=dumped_session_id_list,
            count=self.count,
            is_jargon=self.is_jargon,
            is_complete=self.is_complete,
            is_global=self.is_global,
            last_inference_count=self.last_inference_count,
            inference_with_context=self.inference_with_context,
            inference_with_content_only=self.inference_with_content_only,
        )
